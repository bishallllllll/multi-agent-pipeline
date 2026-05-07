import copy
import hashlib
import asyncio
from typing import Any, List, Optional, Tuple, Dict, TypeVar, Callable
from concurrent.futures import Executor
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_mongodb import MongoDBAtlasVectorSearch

T = TypeVar("T")

class AtlasMongoVector(MongoDBAtlasVectorSearch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._thread_pool = None

    @property
    def embedding_function(self) -> Embeddings:
        return self.embeddings

    def _get_thread_pool(self):
        if self._thread_pool is None:
            try:
                loop = asyncio.get_running_loop()
                self._thread_pool = getattr(loop, "_default_executor", None)
            except Exception:
                pass
        return self._thread_pool

    @staticmethod
    async def _run_in_executor(
        executor: Executor | None,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a sync callable in a thread pool executor."""
        def wrapper() -> T:
            try:
                return func(*args, **kwargs)
            except StopIteration as exc:
                raise RuntimeError from exc

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, wrapper)

    async def aadd_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
        executor: Optional[Executor] = None,
        **kwargs,
    ) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self.add_documents, documents, ids=ids, **kwargs)

    def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
        **kwargs,
    ) -> List[str]:
        """Caller-supplied ``ids`` are intentionally ignored; IDs are derived from
        each document's content digest to ensure cross-batch uniqueness within a file.
        """
        if not documents:
            return []
        file_id = documents[0].metadata["file_id"]
        f_ids = [
            f"{file_id}_{doc.metadata.get('digest') or hashlib.md5(doc.page_content.encode()).hexdigest()}"
            for doc in documents
        ]
        return super().add_documents(documents, f_ids)

    async def asimilarity_search_with_score_by_vector(
        self,
        embedding: List[float],
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
        executor: Optional[Executor] = None,
        **kwargs: Any,
    ) -> List[Tuple[Document, float]]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(
            executor,
            self.similarity_search_with_score_by_vector,
            embedding,
            k=k,
            filter=filter,
            **kwargs
        )

    def similarity_search_with_score_by_vector(
        self,
        embedding: List[float],
        k: int = 4,
        filter: Optional[dict] = None,
        **kwargs: Any,
    ) -> List[Tuple[Document, float]]:
        docs = self._similarity_search_with_score(
            embedding,
            k=k,
            pre_filter=filter,
            post_filter_pipeline=None,
            **kwargs,
        )
        processed_documents: List[Tuple[Document, float]] = []
        for document, score in docs:
            # Make a deep copy to avoid mutating the original document
            doc_copy = copy.deepcopy(document.__dict__)
            # Remove _id field from metadata if it exists
            if "metadata" in doc_copy and "_id" in doc_copy["metadata"]:
                del doc_copy["metadata"]["_id"]
            new_document = Document(**doc_copy)
            processed_documents.append((new_document, score))
        return processed_documents

    async def get_all_ids(self, executor: Optional[Executor] = None) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_all_ids_sync)

    def _get_all_ids_sync(self) -> List[str]:
        return self._collection.distinct("file_id")

    async def get_filtered_ids(
        self,
        ids: List[str],
        executor: Optional[Executor] = None
    ) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_filtered_ids_sync, ids)

    def _get_filtered_ids_sync(self, ids: List[str]) -> List[str]:
        return self._collection.distinct("file_id", {"file_id": {"$in": ids}})

    async def get_documents_by_ids(
        self,
        ids: List[str],
        executor: Optional[Executor] = None
    ) -> List[Document]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_documents_by_ids_sync, ids)

    def _get_documents_by_ids_sync(self, ids: List[str]) -> List[Document]:
        return [
            Document(
                page_content=doc["text"],
                metadata={
                    "file_id": doc["file_id"],
                    "user_id": doc["user_id"],
                    "digest": doc["digest"],
                    "source": doc["source"],
                    "page": int(doc.get("page", 0)),
                },
            )
            for doc in self._collection.find({"file_id": {"$in": ids}})
        ]

    async def delete(
        self,
        ids: Optional[List[str]] = None,
        executor: Optional[Executor] = None
    ) -> None:
        if ids is not None:
            executor = executor or self._get_thread_pool()
            await self._run_in_executor(executor, self._delete_sync, ids)

    def _delete_sync(self, ids: List[str]) -> None:
        self._collection.delete_many({"file_id": {"$in": ids}})
