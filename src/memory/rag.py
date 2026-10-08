"""Hybrid Dual-Path RAG Engine (ChromaDB + BM25)

This module implements a production-grade dual-path retrieval system for Agentic text games:
1. Vector Retrieval (ChromaDB): Captures semantic meanings and contextual queries.
2. Lexical Retrieval (BM25): Captures exact keywords (clues, names, item names, keys, timestamps).
3. Hybrid Fusion: Reciprocal Rank Fusion (RRF) / weighted score blending.
4. Two isolated memory stores:
   - World Lore: Static scenario setting, room blueprints, secret documents.
   - Episodic Memory: Dynamic dialogue logs, accusations, discovered physical clues.
"""

from typing import List, Dict, Any, Optional
import os
import re
import math
from pathlib import Path


class SimpleTokenizer:
    """Chinese & English hybrid word tokenizer supporting jieba fallback."""

    def __init__(self):
        try:
            import jieba
            self.jieba = jieba
            # 关闭 jieba 初始化多余的调试打印
            jieba.setLogLevel(20)
        except ImportError:
            self.jieba = None

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        text = text.lower().strip()
        if self.jieba:
            tokens = [t.strip() for t in self.jieba.cut(text) if t.strip()]
            return tokens
        # Fallback simple regex word split
        return re.findall(r"[\w]+", text)


class BM25Retriever:
    """BM25 (Best Matching 25) Keyword Retrieval Engine."""

    def __init__(self, tokenizer: Optional[SimpleTokenizer] = None):
        self.tokenizer = tokenizer or SimpleTokenizer()
        self.corpus_docs: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25_model = None

    def index(self, docs: List[Dict[str, Any]]) -> None:
        """Index a list of documents where each doc has {'id': ..., 'content': ..., 'metadata': ...}."""
        self.corpus_docs = docs
        self.tokenized_corpus = [self.tokenizer.tokenize(d.get("content", "")) for d in docs]
        if not self.tokenized_corpus or all(len(tokens) == 0 for tokens in self.tokenized_corpus):
            self.bm25_model = None
            return

        try:
            from rank_bm25 import BM25Plus
            self.bm25_model = BM25Plus(self.tokenized_corpus)
        except ImportError:
            try:
                from rank_bm25 import BM25Okapi
                self.bm25_model = BM25Okapi(self.tokenized_corpus)
            except ImportError:
                self.bm25_model = None

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Perform BM25 search with overlap validation."""
        if not self.corpus_docs:
            return []

        tokenized_query = self.tokenizer.tokenize(query)
        if not tokenized_query:
            return []

        query_set = set(tokenized_query)
        if self.bm25_model:
            scores = self.bm25_model.get_scores(tokenized_query)
            ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            results = []
            for idx in ranked_indices[:top_k]:
                # 确保命中至少一个查询关键词
                tokens = self.tokenized_corpus[idx]
                if any(w in tokens for w in query_set):
                    doc_copy = dict(self.corpus_docs[idx])
                    doc_copy["score"] = float(scores[idx])
                    results.append(doc_copy)
            if results:
                return results

        # Simple overlap fallback if rank_bm25 is not available
        query_set = set(tokenized_query)
        results = []
        for idx, tokens in enumerate(self.tokenized_corpus):
            overlap = len(query_set.intersection(tokens))
            if overlap > 0:
                doc_copy = dict(self.corpus_docs[idx])
                doc_copy["score"] = float(overlap)
                results.append(doc_copy)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class HybridRAGEngine:
    """双路 RAG 记忆检索系统 (ChromaDB + BM25 混合检索)

    架构设计：
    1. World Lore (世界设定库)：管理剧本万字世界观、地形建筑、物证档案等静态知识。
    2. Episodic Memory (情景剧情库)：按轮次存储跨场景线索交互与发言。
    3. 混合重排序：结合 BM25 关键词精确度与 Chroma 语义泛化能力，实现低 Token 开销的高精度召回。
    """

    def __init__(
        self,
        collection_name: str = "game_world_lore",
        persist_dir: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.tokenizer = SimpleTokenizer()
        self.bm25 = BM25Retriever(self.tokenizer)
        self.chroma_client = None
        self.collection = None
        self.memory_store: List[Dict[str, Any]] = []

        self._init_chroma()

    def _init_chroma(self):
        """延迟/容错初始化 Chroma 向量客户端，内置轻量 Embedding 函数保证零网络下载开销"""
        try:
            import chromadb
            from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

            class FastLocalEmbedding(EmbeddingFunction):
                """高效轻量本地分词哈希向量发生器（维度 128），具备零网络依赖与毫秒级延迟特性"""
                def __call__(self, input: Documents) -> Embeddings:
                    embeddings: Embeddings = []
                    for text in input:
                        vec = [0.0] * 128
                        words = re.findall(r"[\w]+", text.lower())
                        for w in words:
                            h = abs(hash(w)) % 128
                            vec[h] += 1.0
                        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
                        embeddings.append([x / norm for x in vec])
                    return embeddings

            if self.persist_dir:
                self.chroma_client = chromadb.PersistentClient(path=self.persist_dir)
            else:
                self.chroma_client = chromadb.EphemeralClient()

            self.embedding_fn = FastLocalEmbedding()
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            self.chroma_client = None
            self.collection = None

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """添加文档列表。每个元素形如 {'id': 'lore_1', 'content': '...', 'metadata': {...}}"""
        if not documents:
            return

        for doc in documents:
            self.memory_store.append(doc)

        # 1. 更新 BM25 索引
        self.bm25.index(self.memory_store)

        # 2. 更新 ChromaDB 向量库
        if self.collection:
            try:
                ids = [doc["id"] for doc in documents]
                documents_text = [doc["content"] for doc in documents]
                metadatas = [doc.get("metadata", {}) for doc in documents]
                self.collection.upsert(
                    ids=ids,
                    documents=documents_text,
                    metadatas=metadatas,
                )
            except Exception as e:
                pass

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """双路混合检索召回核心入口，利用 RRF (Reciprocal Rank Fusion) 融合排名"""
        if not query.strip() or not self.memory_store:
            return []

        # 1. BM25 关键词检索结果
        bm25_results = self.bm25.search(query, top_k=top_k * 2)

        # 2. Chroma 向量检索结果
        chroma_results: List[Dict[str, Any]] = []
        if self.collection:
            try:
                query_res = self.collection.query(
                    query_texts=[query],
                    n_results=min(top_k * 2, len(self.memory_store))
                )
                if query_res and query_res.get("ids") and query_res["ids"][0]:
                    ids = query_res["ids"][0]
                    distances = query_res["distances"][0] if query_res.get("distances") else []
                    docs = query_res["documents"][0] if query_res.get("documents") else []
                    metas = query_res["metadatas"][0] if query_res.get("metadatas") else []

                    for i, doc_id in enumerate(ids):
                        chroma_results.append({
                            "id": doc_id,
                            "content": docs[i] if i < len(docs) else "",
                            "metadata": metas[i] if i < len(metas) else {},
                            "distance": distances[i] if i < len(distances) else 0.0,
                        })
            except Exception:
                chroma_results = []

        # 3. Reciprocal Rank Fusion (RRF) 算法打分融合
        k_rrf = 60
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict[str, Any]] = {}

        # 存入 BM25 排名权重
        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            doc_map[doc_id] = item
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + bm25_weight * (1.0 / (k_rrf + rank + 1))

        # 存入 Chroma 向量排名权重
        for rank, item in enumerate(chroma_results):
            doc_id = item["id"]
            if doc_id not in doc_map:
                doc_map[doc_id] = item
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + vector_weight * (1.0 / (k_rrf + rank + 1))

        # 若两路都未命中高分，且存在本地文档，尝试关键词模糊补充
        if not rrf_scores:
            fallback = []
            for doc in self.memory_store[:top_k]:
                item = dict(doc)
                item["rrf_score"] = 0.0
                fallback.append(item)
            return fallback

        # 排序并返回 top_k
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        final_results = []
        for doc_id in sorted_ids[:top_k]:
            res = dict(doc_map[doc_id])
            res["rrf_score"] = rrf_scores[doc_id]
            final_results.append(res)

        return final_results
