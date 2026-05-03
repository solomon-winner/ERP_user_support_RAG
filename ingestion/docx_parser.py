"""
DOCX Parser — extracts and chunks text from DOCX user manuals.

Usage:
    python -m app.ingestion.docx_parser --input ./app/data/sample_docs --output ./app/data/doc_chunks.json
"""
import os
import json
import argparse
from typing import List, Tuple
from app.models.schemas import DocumentChunk


def parse_docx(file_path: str) -> List[Tuple[str, str, int]]:
    """
    Parse a DOCX file into sections.
    
    Returns list of (heading, content, page_number) tuples.
    Uses heading styles to split sections.
    """
    try:
        from docx import Document
    except ImportError:
        print("[docx_parser] python-docx not installed. Run: pip install python-docx")
        return []

    doc = Document(file_path)
    sections: List[Tuple[str, str, int]] = []
    current_heading = "Introduction"
    current_content: List[str] = []
    page_estimate = 1

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Check if this is a heading
        style_name = para.style.name if para.style else ""
        is_heading = style_name.startswith("Heading") or style_name.startswith("Title")

        if is_heading and current_content:
            # Save previous section
            sections.append((
                current_heading,
                "\n".join(current_content),
                page_estimate,
            ))
            current_heading = text
            current_content = []
            # Rough page estimate: ~3000 chars per page
            total_chars = sum(len(s[1]) for s in sections)
            page_estimate = total_chars // 3000 + 1
        elif is_heading:
            current_heading = text
        else:
            current_content.append(text)

    # Don't forget the last section
    if current_content:
        sections.append((current_heading, "\n".join(current_content), page_estimate))

    return sections


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks of approximately chunk_size tokens.
    Uses a simple word-based approximation (1 token ≈ 0.75 words).
    """
    words = text.split()
    # Approximate tokens from words
    words_per_chunk = int(chunk_size * 0.75)
    overlap_words = int(overlap * 0.75)

    if len(words) <= words_per_chunk:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + words_per_chunk
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        start += words_per_chunk - overlap_words

    return chunks


def parse_docx_directory(
    docs_dir: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[DocumentChunk]:
    """
    Parse all DOCX files in a directory and return chunked DocumentChunks.
    Embeddings are NOT generated here — use embedder.py for that.
    """
    all_chunks: List[DocumentChunk] = []

    if not os.path.isdir(docs_dir):
        print(f"[docx_parser] Directory not found: {docs_dir}")
        return all_chunks

    for filename in sorted(os.listdir(docs_dir)):
        if not filename.endswith(".docx"):
            continue
        file_path = os.path.join(docs_dir, filename)
        print(f"[docx_parser] Parsing: {filename}")

        sections = parse_docx(file_path)
        chunk_id = len(all_chunks)

        for heading, content, page_num in sections:
            text_chunks = chunk_text(content, chunk_size, overlap)
            for chunk_text in text_chunks:
                all_chunks.append(DocumentChunk(
                    id=chunk_id,
                    content=chunk_text,
                    source_file=filename,
                    section_heading=heading,
                    page_number=page_num,
                ))
                chunk_id += 1

    print(f"[docx_parser] Total chunks: {len(all_chunks)}")
    return all_chunks


def main():
    parser = argparse.ArgumentParser(description="Parse DOCX manuals into chunks")
    parser.add_argument("--input", default="./app/data/sample_docs", help="Directory with DOCX files")
    parser.add_argument("--output", default="./app/data/doc_chunks.json", help="Output JSON file")
    parser.add_argument("--chunk-size", type=int, default=500, help="Chunk size in tokens")
    parser.add_argument("--overlap", type=int, default=50, help="Chunk overlap in tokens")
    args = parser.parse_args()

    chunks = parse_docx_directory(args.input, args.chunk_size, args.overlap)

    # Save as JSON (without embeddings — those are added by embedder.py)
    output_data = {
        "chunks": [
            {
                "id": c.id,
                "content": c.content,
                "source_file": c.source_file,
                "section_heading": c.section_heading,
                "page_number": c.page_number,
            }
            for c in chunks
        ]
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"[docx_parser] Saved {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
