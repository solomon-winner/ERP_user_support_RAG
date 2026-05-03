"""
Embedding Store — semantic search over documentation chunks using pgvector.

Stores document chunks with their OpenAI embeddings in PostgreSQL + pgvector
and provides similarity search capabilities.
"""
import json
from typing import List, Optional
from app.models.schemas import DocumentChunk
from app.config import settings


class EmbeddingStore:
    """
    Vector store for document chunks using pgvector.
    
    In production, this connects to PostgreSQL with the pgvector extension.
    For development/testing without a database, it falls back to an
    in-memory store with brute-force similarity search.
    """

    def __init__(self):
        self._db = None
        self._memory_store: List[DocumentChunk] = []
        self._use_db = False
        self._initialized = False

    async def initialize(self, database_url: Optional[str] = None) -> None:
        """Initialize the store. Attempts DB connection, falls back to memory."""
        db_url = database_url or settings.DATABASE_URL

        if settings.PGVECTOR_ENABLED:
            try:
                import sqlalchemy
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker

                # Convert postgresql:// to postgresql+asyncpg://
                async_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
                self._engine = create_async_engine(async_url, echo=False)
                
                # Test connection
                async with self._engine.begin() as conn:
                    await conn.execute(sqlalchemy.text("SELECT 1"))

                # Create table if not exists
                await self._create_table()

                self._async_session = sessionmaker(
                    self._engine, class_=AsyncSession, expire_on_commit=False
                )
                self._use_db = True
                print("[EmbeddingStore] Connected to PostgreSQL + pgvector")
            except Exception as e:
                print(f"[EmbeddingStore] DB connection failed ({e}). Using in-memory fallback.")
                self._use_db = False

        self._initialized = True

    async def _create_table(self):
        """Create the document_chunks table with pgvector extension."""
        import sqlalchemy
        async with self._engine.begin() as conn:
            await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(sqlalchemy.text("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    source_file TEXT NOT NULL DEFAULT '',
                    section_heading TEXT NOT NULL DEFAULT '',
                    page_number INTEGER NOT NULL DEFAULT 0,
                    embedding vector(1536)
                )
            """))
            # Create index for fast similarity search
            await conn.execute(sqlalchemy.text("""
                CREATE INDEX IF NOT EXISTS idx_doc_chunks_embedding 
                ON document_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """))

    async def store_chunks(self, chunks: List[DocumentChunk]) -> int:
        """Store document chunks with embeddings. Returns count stored."""
        if not self._initialized:
            await self.initialize()

        if self._use_db:
            return await self._store_in_db(chunks)
        else:
            self._memory_store.extend(chunks)
            return len(chunks)

    async def _store_in_db(self, chunks: List[DocumentChunk]) -> int:
        """Store chunks in PostgreSQL."""
        import sqlalchemy
        stored = 0
        async with self._async_session() as session:
            for chunk in chunks:
                if chunk.embedding is None:
                    continue
                embedding_str = "[" + ",".join(str(v) for v in chunk.embedding) + "]"
                await session.execute(
                    sqlalchemy.text("""
                        INSERT INTO document_chunks (content, source_file, section_heading, page_number, embedding)
                        VALUES (:content, :source, :heading, :page, :embedding::vector)
                    """),
                    {
                        "content": chunk.content,
                        "source": chunk.source_file,
                        "heading": chunk.section_heading,
                        "page": chunk.page_number,
                        "embedding": embedding_str,
                    }
                )
                stored += 1
            await session.commit()
        return stored

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        module_filter: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """
        Search for similar document chunks using cosine similarity.
        Returns the top_k most similar chunks.
        """
        if not self._initialized:
            await self.initialize()

        if self._use_db:
            return await self._search_in_db(query_embedding, top_k)
        else:
            return self._search_in_memory(query_embedding, top_k)

    async def _search_in_db(
        self, query_embedding: List[float], top_k: int
    ) -> List[DocumentChunk]:
        """Search in PostgreSQL using pgvector cosine distance."""
        import sqlalchemy
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        async with self._async_session() as session:
            result = await session.execute(
                sqlalchemy.text("""
                    SELECT id, content, source_file, section_heading, page_number,
                           1 - (embedding <=> :query::vector) AS similarity
                    FROM document_chunks
                    ORDER BY embedding <=> :query::vector
                    LIMIT :limit
                """),
                {"query": embedding_str, "limit": top_k}
            )
            chunks = []
            for row in result:
                chunks.append(DocumentChunk(
                    id=row.id,
                    content=row.content,
                    source_file=row.source_file,
                    section_heading=row.section_heading,
                    page_number=row.page_number,
                ))
            return chunks

    def _search_in_memory(
        self, query_embedding: List[float], top_k: int
    ) -> List[DocumentChunk]:
        """Brute-force cosine similarity search in memory (fallback)."""
        import numpy as np

        if not self._memory_store:
            return []

        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        scored = []
        for chunk in self._memory_store:
            if chunk.embedding is None:
                continue
            chunk_vec = np.array(chunk.embedding)
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm == 0:
                continue
            similarity = np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm)
            scored.append((similarity, chunk))

        scored.sort(key=lambda x: -x[0])
        return [chunk for _, chunk in scored[:top_k]]

    async def chunk_count(self) -> int:
        """Return total number of stored chunks."""
        if self._use_db:
            import sqlalchemy
            async with self._async_session() as session:
                result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM document_chunks")
                )
                return result.scalar()
        return len(self._memory_store)


# Singleton instance
embedding_store = EmbeddingStore()
