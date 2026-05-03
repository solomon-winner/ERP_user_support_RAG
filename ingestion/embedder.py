"""
Embedder — generates OpenAI embeddings for document chunks and stores them.

Usage:
    python -m app.ingestion.embedder --input ./app/data/doc_chunks.json
"""
import os
import json
import asyncio
import argparse
from typing import List
from app.models.schemas import DocumentChunk
from app.config import settings


async def generate_embeddings(
    chunks: List[DocumentChunk],
    batch_size: int = 20,
) -> List[DocumentChunk]:
    """
    Generate OpenAI embeddings for document chunks.
    Processes in batches to respect rate limits.
    """
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    total = len(chunks)
    print(f"[embedder] Generating embeddings for {total} chunks...")

    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.content for c in batch]

        try:
            response = client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
                dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
            )

            for j, chunk in enumerate(batch):
                chunk.embedding = response.data[j].embedding

            print(f"[embedder]   Embedded {min(i + batch_size, total)}/{total}")

        except Exception as e:
            print(f"[embedder]   Error on batch {i}: {e}")
            continue

    return chunks


async def embed_and_store(input_path: str) -> int:
    """
    Load doc chunks from JSON, generate embeddings, store in vector DB.
    Returns number of chunks stored.
    """
    # Load chunks
    if not os.path.exists(input_path):
        print(f"[embedder] File not found: {input_path}")
        return 0

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks_data = data.get("chunks", [])
    chunks = [DocumentChunk(**c) for c in chunks_data]

    if not chunks:
        print("[embedder] No chunks to embed")
        return 0

    # Generate embeddings
    chunks = await generate_embeddings(chunks)

    # Store in vector DB
    from app.knowledge.embedding_store import embedding_store
    await embedding_store.initialize()
    stored = await embedding_store.store_chunks(chunks)

    print(f"[embedder] Stored {stored} chunks with embeddings")
    return stored


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for document chunks")
    parser.add_argument("--input", default="./app/data/doc_chunks.json", help="Chunks JSON from docx_parser")
    args = parser.parse_args()

    asyncio.run(embed_and_store(args.input))


if __name__ == "__main__":
    main()
