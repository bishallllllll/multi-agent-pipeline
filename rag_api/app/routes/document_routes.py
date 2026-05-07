# app/routes/document_routes.py
import os
import uuid
from pathlib import Path
import hashlib
import traceback
import aiofiles
import aiofiles.os
from shutil import copyfileobj
from typing import List, Iterable, Optional, Union, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor
from fastapi import (
    APIRouter,
    Request,
    UploadFile,
    HTTPException,
    File,
    Form,
    Body,
    Query,
    status,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from functools import lru_cache
import asyncio

from app.config import (
    logger,
    vector_store,
    VECTOR_DB_TYPE,
    VectorDBType,
    RAG_UPLOAD_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_QUEUE_SIZE,
    RAG_DISTANCE_THRESHOLD,
)

if (
    VECTOR_DB_TYPE == VectorDBType.ATLAS_MONGO
    and os.getenv("RAG_DISTANCE_THRESHOLD") not in (None, "")
):
    logger.warning(
        "RAG_DISTANCE_THRESHOLD is set but VECTOR_DB_TYPE=atlas-mongo; "
        "Atlas returns similarity scores (higher = better) which would "
        "invert the filter semantics, so the threshold will be ignored."
    )


def _apply_distance_threshold(documents):
    if RAG_DISTANCE_THRESHOLD is None:
        return documents
    if VECTOR_DB_TYPE == VectorDBType.ATLAS_MONGO:
        return documents
    return [(doc, score) for doc, score in documents if score <= RAG_DISTANCE_THRESHOLD]

from app.constants import ERROR_MESSAGES
from app.models import (
    StoreDocument,
    QueryRequestBody,
    DocumentResponse,
    QueryMultipleBody,
)
from app.utils.document_loader import (
    get_loader,
    clean_text,
    process_documents,
    cleanup_temp_encoding_file,
)
from app.utils.health import is_health_ok

router = APIRouter()


def calculate_num_batches(total: int, batch_size: int) -> int:
    if batch_size <= 0:
        return 1
    return (total + batch_size - 1) // batch_size


def get_user_id(request: Request, entity_id: str = None) -> str:
    if not hasattr(request.state, "user"):
        return entity_id if entity_id else "public"
    else:
        return entity_id if entity_id else request.state.user.get("id")


async def save_upload_file_async(file: UploadFile, temp_file_path: str) -> None:
    try:
        async with aiofiles.open(temp_file_path, "wb") as temp_file:
            chunk_size = 64 * 1024  # 64 KB
            while content := await file.read(chunk_size):
                await temp_file.write(content)
    except Exception as e:
        logger.error(
            "Failed to save uploaded file | Path: %s | Error: %s | Traceback: %s",
            temp_file_path,
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save the uploaded file. Error: {str(e)}",
        )


def validate_file_path(base_dir: str, file_path: str) -> Optional[str]:
    if not file_path or not file_path.strip():
        return None
    try:
        allowed = Path(base_dir).resolve()
        requested = Path(os.path.join(base_dir, file_path)).resolve()
        requested.relative_to(allowed)
        return str(requested)
    except (ValueError, RuntimeError, TypeError, OSError):
        return None


def _make_unique_temp_path(user_id: str, filename: str) -> Optional[str]:
    if validate_file_path(RAG_UPLOAD_DIR, os.path.join(user_id, filename)) is None:
        return None
    p = Path(filename)
    unique_name = f"{p.stem}_{uuid.uuid4().hex}{p.suffix}"
    return str(Path(RAG_UPLOAD_DIR, user_id, unique_name).resolve())


async def load_file_content(
    filename: str,
    content_type: str,
    file_path: str,
    executor,
    raw_text: bool = False,
) -> tuple:
    loader = None
    try:
        loader, known_type, file_ext = get_loader(
            filename, content_type, file_path, raw_text=raw_text
        )
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(executor, lambda: list(loader.lazy_load()))
        return data, known_type, file_ext
    finally:
        if loader is not None:
            cleanup_temp_encoding_file(loader)


def extract_text_from_documents(documents: List[Document], file_ext: str) -> str:
    text_content = ""
    if documents:
        for doc in documents:
            if hasattr(doc, "page_content"):
                if file_ext == "pdf":
                    text_content += clean_text(doc.page_content) + "\n"
                else:
                    text_content += doc.page_content + "\n"
    return text_content.rstrip("\n")


async def cleanup_temp_file_async(file_path: str) -> None:
    try:
        await aiofiles.os.remove(file_path)
    except Exception as e:
        logger.error(
            "Failed to remove temporary file | Path: %s | Error: %s | Traceback: %s",
            file_path,
            str(e),
            traceback.format_exc(),
        )


@router.get("/ids")
async def get_all_ids(request: Request):
    try:
        # All vector stores now support async get_all_ids
        ids = await vector_store.get_all_ids(executor=request.app.state.thread_pool)
        return list(set(ids))
    except HTTPException as http_exc:
        logger.error(
            "HTTP Exception in get_all_ids | Status: %d | Detail: %s",
            http_exc.status_code,
            http_exc.detail,
        )
        raise http_exc
    except Exception as e:
        logger.error(
            "Failed to get all IDs | Error: %s | Traceback: %s",
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    try:
        if await is_health_ok():
            return {"status": "UP"}
        else:
            logger.error("Health check failed")
            return {"status": "DOWN"}, 503
    except Exception as e:
        logger.error(
            "Error during health check | Error: %s | Traceback: %s",
            str(e),
            traceback.format_exc(),
        )
        return {"status": "DOWN", "error": str(e)}, 503


@router.get("/documents", response_model=list[DocumentResponse])
async def get_documents_by_ids(request: Request, ids: list[str] = Query(...)):
    try:
        executor = request.app.state.thread_pool
        existing_ids = await vector_store.get_filtered_ids(ids, executor=executor)
        documents = await vector_store.get_documents_by_ids(ids, executor=executor)

        if not all(id in existing_ids for id in ids):
            raise HTTPException(status_code=404, detail="One or more IDs not found")

        if not documents:
            raise HTTPException(
                status_code=404, detail="No documents found for the given IDs"
            )

        return documents
    except HTTPException as http_exc:
        logger.error(
            "HTTP Exception in get_documents_by_ids | Status: %d | Detail: %s",
            http_exc.status_code,
            http_exc.detail,
        )
        raise http_exc
    except Exception as e:
        logger.error(
            "Error getting documents by IDs | IDs: %s | Error: %s | Traceback: %s",
            ids,
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents")
async def delete_documents(request: Request, document_ids: List[str] = Body(...)):
    try:
        executor = request.app.state.thread_pool
        existing_ids = await vector_store.get_filtered_ids(document_ids, executor=executor)
        await vector_store.delete(ids=document_ids, executor=executor)

        if not all(id in existing_ids for id in document_ids):
            raise HTTPException(status_code=404, detail="One or more IDs not found")

        file_count = len(document_ids)
        return {
            "message": f"Documents for {file_count} file{'s' if file_count > 1 else ''} deleted successfully"
        }
    except HTTPException as http_exc:
        logger.error(
            "HTTP Exception in delete_documents | Status: %d | Detail: %s",
            http_exc.status_code,
            http_exc.detail,
        )
        raise http_exc
    except Exception as e:
        logger.error(
            "Failed to delete documents | IDs: %s | Error: %s | Traceback: %s",
            document_ids,
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e))


@lru_cache(maxsize=128)
def get_cached_query_embedding(query: str):
    # This might still block if not careful, but embed_query is usually fast or has its own thread handling
    return vector_store.embedding_function.embed_query(query)


@router.post("/query")
async def query_embeddings_by_file_id(
    body: QueryRequestBody,
    request: Request,
):
    if not hasattr(request.state, "user"):
        user_authorized = body.entity_id if body.entity_id else "public"
    else:
        user_authorized = (
            body.entity_id if body.entity_id else request.state.user.get("id")
        )

    authorized_documents = []

    try:
        embedding = get_cached_query_embedding(body.query)

        documents = await vector_store.asimilarity_search_with_score_by_vector(
            embedding,
            k=body.k,
            filter={"file_id": {"$eq": body.file_id}},
            executor=request.app.state.thread_pool,
        )

        documents = _apply_distance_threshold(documents)

        if not documents:
            return authorized_documents

        document, score = documents[0]
        doc_metadata = document.metadata
        doc_user_id = doc_metadata.get("user_id")

        if doc_user_id is None or doc_user_id == user_authorized:
            authorized_documents = documents
        else:
            if body.entity_id and hasattr(request.state, "user"):
                user_authorized = request.state.user.get("id")
                if doc_user_id == user_authorized:
                    authorized_documents = documents
                else:
                    logger.warning(
                        f"Access denied for user {user_authorized} to document with user_id {doc_user_id}"
                    )
            else:
                logger.warning(
                    f"Unauthorized access attempt by user {user_authorized} to a document with user_id {doc_user_id}"
                )

        return authorized_documents

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            "Error in query embeddings | File ID: %s | Query: %s | Error: %s | Traceback: %s",
            body.file_id,
            body.query,
            str(e),
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e))


async def _process_documents_async_pipeline(
    documents: List[Document],
    file_id: str,
    vector_store_inst: any,
    executor: "ThreadPoolExecutor",
) -> List[str]:
    total_chunks = len(documents)
    if total_chunks == 0:
        return []

    embedding_queue = asyncio.Queue(maxsize=EMBEDDING_MAX_QUEUE_SIZE)
    results_queue = asyncio.Queue()
    all_ids = []

    num_batches = calculate_num_batches(total_chunks, EMBEDDING_BATCH_SIZE)

    async def batch_producer():
        try:
            for batch_idx in range(num_batches):
                start_idx = batch_idx * EMBEDDING_BATCH_SIZE
                end_idx = min(start_idx + EMBEDDING_BATCH_SIZE, total_chunks)
                batch_documents = documents[start_idx:end_idx]
                batch_ids = [f"{file_id}_{start_idx + i}" for i in range(len(batch_documents))]

                await embedding_queue.put(
                    (batch_documents, batch_ids, batch_idx + 1, num_batches)
                )
        except Exception as e:
            logger.error("Error in batch producer: %s", e)
            raise
        finally:
            await embedding_queue.put(None)

    async def embedding_consumer():
        try:
            while True:
                item = await embedding_queue.get()
                if item is None:
                    embedding_queue.task_done()
                    break

                batch_documents, batch_ids, batch_num, total_batches = item
                try:
                    batch_result_ids = await vector_store_inst.aadd_documents(
                        batch_documents, ids=batch_ids, executor=executor
                    )
                    await results_queue.put(batch_result_ids)
                except Exception as e:
                    logger.error("Error processing batch %d/%d: %s", batch_num, total_batches, e)
                    await results_queue.put(e)
                finally:
                    embedding_queue.task_done()
        except Exception as e:
            logger.error("Fatal error in embedding consumer: %s", e)
            await results_queue.put(e)
            raise

    try:
        producer_task = asyncio.create_task(batch_producer())
        consumer_task = asyncio.create_task(embedding_consumer())
        await asyncio.gather(producer_task, consumer_task, return_exceptions=False)

        for _ in range(num_batches):
            result = await results_queue.get()
            if isinstance(result, Exception):
                raise result
            all_ids.extend(result)

        return all_ids
    except Exception as e:
        logger.error("Pipeline failed for file %s: %s", file_id, e)
        if all_ids:
            try:
                await vector_store_inst.delete(ids=[file_id], executor=executor)
            except Exception:
                pass
        raise


def generate_digest(page_content: str) -> str:
    return hashlib.md5(page_content.encode("utf-8", "ignore")).hexdigest()


def _prepare_documents_sync(
    data: Iterable[Document],
    file_id: str,
    user_id: str,
    clean_content: bool,
) -> List[Document]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    documents = text_splitter.split_documents(data)

    if clean_content:
        for doc in documents:
            doc.page_content = clean_text(doc.page_content)

    return [
        Document(
            page_content=doc.page_content,
            metadata={
                "file_id": file_id,
                "user_id": user_id,
                "digest": generate_digest(doc.page_content),
                **(doc.metadata or {}),
            },
        )
        for doc in documents
    ]


async def store_data_in_vector_db(
    data: Iterable[Document],
    file_id: str,
    user_id: str = "",
    clean_content: bool = False,
    executor=None,
) -> bool:
    loop = asyncio.get_running_loop()
    docs = await loop.run_in_executor(
        executor,
        _prepare_documents_sync,
        data,
        file_id,
        user_id,
        clean_content,
    )

    try:
        if EMBEDDING_BATCH_SIZE <= 0:
            # Generate unique IDs per chunk to avoid Chroma duplicate rejection
            chunk_ids = [f"{file_id}_{i}" for i in range(len(docs))]
            ids = await vector_store.aadd_documents(
                docs, ids=chunk_ids, executor=executor
            )
        else:
            ids = await _process_documents_async_pipeline(
                docs, file_id, vector_store, executor
            )
        return {"message": "Documents added successfully", "ids": ids}
    except Exception as e:
        logger.error(
            "Failed to store data in vector DB | File ID: %s | User ID: %s | Error: %s",
            file_id, user_id, str(e)
        )
        return {"message": "An error occurred while adding documents.", "error": str(e)}


@router.post("/local/embed")
async def embed_local_file(
    document: StoreDocument, request: Request, entity_id: str = None
):
    file_path = validate_file_path(RAG_UPLOAD_DIR, document.filepath)
    if file_path is None or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.FILE_NOT_FOUND)

    user_id = get_user_id(request, entity_id)
    loader = None
    try:
        loader, known_type, file_ext = get_loader(
            document.filename, document.file_content_type, file_path
        )
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            request.app.state.thread_pool, lambda: list(loader.lazy_load())
        )

        result = await store_data_in_vector_db(
            data,
            document.file_id,
            user_id,
            clean_content=file_ext == "pdf",
            executor=request.app.state.thread_pool,
        )

        if result:
            return {
                "status": True,
                "file_id": document.file_id,
                "filename": document.filename,
                "known_type": known_type,
            }
        else:
            raise HTTPException(status_code=500, detail=ERROR_MESSAGES.DEFAULT())
    finally:
        if loader is not None:
            cleanup_temp_encoding_file(loader)


@router.post("/embed")
async def embed_file(
    request: Request,
    file_id: str = Form(...),
    file: UploadFile = File(...),
    entity_id: str = Form(None),
):
    user_id = get_user_id(request, entity_id)
    validated_file_path = _make_unique_temp_path(user_id, file.filename)

    if validated_file_path is None:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT("Invalid request"))

    try:
        os.makedirs(os.path.dirname(validated_file_path), exist_ok=True)
        await save_upload_file_async(file, validated_file_path)
        data, known_type, file_ext = await load_file_content(
            file.filename,
            file.content_type,
            validated_file_path,
            request.app.state.thread_pool,
        )

        result = await store_data_in_vector_db(
            data=data,
            file_id=file_id,
            user_id=user_id,
            clean_content=file_ext == "pdf",
            executor=request.app.state.thread_pool,
        )

        if not result or "error" in result:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to store file data"))
            
        return {
            "status": True,
            "message": "File processed successfully.",
            "file_id": file_id,
            "filename": file.filename,
            "known_type": known_type,
        }
    finally:
        await cleanup_temp_file_async(validated_file_path)


@router.get("/documents/{id}/context")
async def load_document_context(request: Request, id: str):
    try:
        executor = request.app.state.thread_pool
        existing_ids = await vector_store.get_filtered_ids([id], executor=executor)
        documents = await vector_store.get_documents_by_ids([id], executor=executor)

        if not existing_ids:
            raise HTTPException(status_code=404, detail="The specified file_id was not found")

        if not documents:
            raise HTTPException(status_code=404, detail="No document found for the given ID")

        return process_documents(documents)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT(e))


@router.post("/query_multiple")
async def query_embeddings_by_file_ids(request: Request, body: QueryMultipleBody):
    try:
        embedding = get_cached_query_embedding(body.query)
        documents = await vector_store.asimilarity_search_with_score_by_vector(
            embedding,
            k=body.k,
            filter={"file_id": {"$in": body.file_ids}},
            executor=request.app.state.thread_pool,
        )
        documents = _apply_distance_threshold(documents)
        if not documents:
            raise HTTPException(status_code=404, detail="No documents found for the given query")
        return documents
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/text")
async def extract_text_from_file(
    request: Request,
    file_id: str = Form(...),
    file: UploadFile = File(...),
    entity_id: str = Form(None),
):
    user_id = get_user_id(request, entity_id)
    validated_temp_file_path = _make_unique_temp_path(user_id, file.filename)

    if validated_temp_file_path is None:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES.DEFAULT("Invalid request"))

    try:
        os.makedirs(os.path.dirname(validated_temp_file_path), exist_ok=True)
        await save_upload_file_async(file, validated_temp_file_path)
        data, known_type, file_ext = await load_file_content(
            file.filename,
            file.content_type,
            validated_temp_file_path,
            request.app.state.thread_pool,
            raw_text=True,
        )
        text_content = extract_text_from_documents(data, file_ext)
        return {
            "text": text_content,
            "file_id": file_id,
            "filename": file.filename,
            "known_type": known_type,
        }
    finally:
        await cleanup_temp_file_async(validated_temp_file_path)
