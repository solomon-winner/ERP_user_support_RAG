"""
Process Extractor — uses LLM to extract business process workflows from documentation.

Given a DOCX manual or text file, this uses the LLM to identify and extract
ordered step sequences for each business process described in the document.

Usage:
    python -m app.ingestion.process_extractor --input ./app/data/sample_docs --output ./app/data/process_graphs.json
"""
import os
import json
import argparse
from typing import List
from app.models.schemas import ProcessGraph, ProcessStep
from app.config import settings


PROCESS_EXTRACTION_PROMPT = """You are an ERP business process analyst. Given the following documentation text, identify all distinct business processes/workflows described and extract their step-by-step sequences.

For each process, output a JSON object with this exact structure:
{
  "process_name": "snake_case_identifier",
  "title": "Human-Readable Process Name",
  "description": "What this process accomplishes",
  "module": "ERP Module Name",
  "steps": [
    {
      "order": 1,
      "route": "/suggested/route/path",
      "title": "Short Step Title",
      "description": "Detailed description of what to do",
      "target_element": "#css-selector-if-identifiable",
      "action": "click|fill|select|navigate",
      "fields": [
        {"name": "field_name", "type": "string", "description": "What this field is for"}
      ],
      "next_step_condition": null
    }
  ]
}

Rules:
- Each process must have at least 2 steps
- Routes should follow RESTful patterns (e.g., /payroll/period/select)
- Include all form fields mentioned in each step
- If a step has a conditional branch, describe it in next_step_condition
- Use snake_case for process_name and field names
- Output ONLY a JSON array of process objects, no other text

Documentation text:
---
{doc_text}
---

Extract all business processes:"""


async def extract_processes_from_text(
    text: str,
    openai_client=None,
) -> List[ProcessGraph]:
    """
    Use LLM to extract business process definitions from documentation text.
    """
    if openai_client is None:
        from openai import OpenAI
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # Truncate text to fit in prompt (rough token estimate)
    max_chars = 12000  # ~3000 tokens
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"

    prompt = PROCESS_EXTRACTION_PROMPT.format(doc_text=text)

    try:
        response = openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an ERP business process analyst. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
        )

        content = response.choices[0].message.content.strip()

        # Clean up markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        processes_data = json.loads(content)

        processes = []
        for p in processes_data:
            processes.append(ProcessGraph(**p))

        return processes

    except json.JSONDecodeError as e:
        print(f"[process_extractor] JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"[process_extractor] Error: {e}")
        return []


def extract_processes_from_docx_file(file_path: str) -> str:
    """Extract all text from a DOCX file for process extraction."""
    try:
        from docx import Document
    except ImportError:
        print("[process_extractor] python-docx not installed")
        return ""

    doc = Document(file_path)
    paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
    return "\n".join(paragraphs)


async def extract_from_directory(
    docs_dir: str,
    output_path: str,
) -> List[ProcessGraph]:
    """
    Process all DOCX files in a directory, extract processes, and save.
    """
    all_processes: List[ProcessGraph] = []

    if not os.path.isdir(docs_dir):
        print(f"[process_extractor] Directory not found: {docs_dir}")
        return all_processes

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    for filename in sorted(os.listdir(docs_dir)):
        if not filename.endswith(".docx"):
            continue
        file_path = os.path.join(docs_dir, filename)
        print(f"[process_extractor] Processing: {filename}")

        text = extract_processes_from_docx_file(file_path)
        if not text.strip():
            continue

        processes = await extract_processes_from_text(text, client)
        print(f"[process_extractor]   Found {len(processes)} processes")
        all_processes.extend(processes)

    # Save
    output_data = {
        "processes": [p.model_dump() for p in all_processes]
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"[process_extractor] Saved {len(all_processes)} processes to {output_path}")
    return all_processes


def main():
    parser = argparse.ArgumentParser(description="Extract business processes from DOCX manuals")
    parser.add_argument("--input", default="./app/data/sample_docs", help="Directory with DOCX files")
    parser.add_argument("--output", default="./app/data/process_graphs.json", help="Output JSON file")
    args = parser.parse_args()

    import asyncio
    asyncio.run(extract_from_directory(args.input, args.output))


if __name__ == "__main__":
    main()
