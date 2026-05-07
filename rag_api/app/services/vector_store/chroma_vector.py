import logging
import asyncio
from typing import Any, List, Optional, Tuple, Dict, TypeVar, Callable
from concurrent.futures import Executor
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

T = TypeVar("T")

class ChromaVector(Chroma):
    def __init__(
        self,
        collection_name: str,
        embedding_function: Embeddings,
        persist_directory: str,
    ):
        super().__init__(
            collection_name=collection_name,
            embedding_function=embedding_function,
            persist_directory=persist_directory,
        )
        self._thread_pool = None
        logger.info(f"Initialized ChromaVector at {persist_directory}")

    @property
    def embedding_function(self):
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
        executor: Optional[Executor] = None,
        **kwargs: Any
    ) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self.add_documents, documents, **kwargs)

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
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> List[Tuple[Document, float]]:
        chroma_filter = None
        if filter:
            chroma_filter = {}
            for key, val in filter.items():
                if isinstance(val, dict) and "$eq" in val:
                    chroma_filter[key] = val["$eq"]
                elif isinstance(val, dict) and "$in" in val:
                    chroma_filter[key] = {"$in": val["$in"]}
                else:
                    chroma_filter[key] = val
        
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            where=chroma_filter,
            include=["metadatas", "documents", "distances"]
        )
        
        docs_with_scores = []
        if results["documents"]:
            for i in range(len(results["documents"][0])):
                doc = Document(
                    page_content=results["documents"][0][i],
                    metadata=results["metadatas"][0][i]
                )
                score = results["distances"][0][i]
                docs_with_scores.append((doc, score))
        
        return docs_with_scores

    async def get_all_ids(self, executor: Optional[Executor] = None) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_all_ids_sync)

    def _get_all_ids_sync(self) -> List[str]:
        results = self.get(include=["metadatas"])
        ids = [m.get("file_id") for m in results["metadatas"] if m.get("file_id")]
        return list(set(ids))

    async def get_filtered_ids(
        self,
        file_ids: List[str],
        executor: Optional[Executor] = None
    ) -> List[str]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_filtered_ids_sync, file_ids)

    def _get_filtered_ids_sync(self, file_ids: List[str]) -> List[str]:
        results = self.get(
            where={"file_id": {"$in": file_ids}},
            include=["metadatas"]
        )
        ids = [m.get("file_id") for m in results["metadatas"] if m.get("file_id")]
        return list(set(ids))

    async def get_documents_by_ids(
        self,
        file_ids: List[str],
        executor: Optional[Executor] = None
    ) -> List[dict]:
        executor = executor or self._get_thread_pool()
        return await self._run_in_executor(executor, self._get_documents_by_ids_sync, file_ids)

    def _get_documents_by_ids_sync(self, file_ids: List[str]) -> List[dict]:
        results = self.get(
            where={"file_id": {"$in": file_ids}},
            include=["metadatas", "documents"]
        )
        
        docs = []
        for i in range(len(results["ids"])):
            docs.append({
                "page_content": results["documents"][i],
                "metadata": results["metadatas"][i]
            })
        return docs

    async def delete(
        self,
        ids: Optional[List[str]] = None,
        executor: Optional[Executor] = None
    ) -> None:
        if ids is not None:
            executor = executor or self._get_thread_pool()
            await self._run_in_executor(executor, self._delete_sync, ids)

    def _delete_sync(self, ids: List[str]) -> None:
        self._collection.delete(where={"file_id": {"$in": ids}})
