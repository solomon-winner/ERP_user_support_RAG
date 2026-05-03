"""
Route Extractor — parses ERP route code and generates the Route Registry JSON.

Supports:
  - Express.js (Node.js) routes
  - FastAPI (Python) routes  
  - Generic JSON config format

Usage:
    python -m app.ingestion.route_extractor --source ./erp-codebase --type express --output ./app/data/route_registry.json
    python -m app.ingestion.route_extractor --source ./erp-codebase --type fastapi --output ./app/data/route_registry.json
    python -m app.ingestion.route_extractor --source ./route-config.json --type json --output ./app/data/route_registry.json
"""
import os
import re
import json
import argparse
from typing import List, Dict, Any
from app.models.schemas import RouteInfo, FieldDescription


# ═══════════════════════════════════════════
#  Express.js Route Extractor
# ═══════════════════════════════════════════

def extract_express_routes(source_dir: str) -> List[RouteInfo]:
    """
    Parse Express.js route files and extract route definitions.
    Looks for patterns like:
        router.get('/path', ...)
        router.post('/path', ...)
        app.get('/path', ...)
    """
    routes = []
    route_pattern = re.compile(
        r'(?:router|app|Router)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
        re.IGNORECASE
    )

    for root, dirs, files in os.walk(source_dir):
        # Skip node_modules and hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        for filename in files:
            if not filename.endswith(('.js', '.ts', '.mjs')):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (UnicodeDecodeError, PermissionError):
                continue

            # Infer module from directory structure
            rel_path = os.path.relpath(filepath, source_dir)
            parts = rel_path.split(os.sep)
            module = parts[0].replace('-', ' ').title() if len(parts) > 1 else "General"

            for match in route_pattern.finditer(content):
                method = match.group(1).upper()
                path = match.group(2)

                # Normalize path
                if not path.startswith('/'):
                    path = '/' + path

                # Try to extract a title from comments near the route
                title = _extract_route_title(content, match.start())

                routes.append(RouteInfo(
                    path=path,
                    method=method,
                    module=module,
                    title=title or f"{method} {path}",
                    description="",
                    fields=[],
                    permissions=[],
                    next_steps=[],
                    prerequisites=[],
                    tags=[module.lower()],
                ))

    return routes


# ═══════════════════════════════════════════
#  FastAPI Route Extractor
# ═══════════════════════════════════════════

def extract_fastapi_routes(source_dir: str) -> List[RouteInfo]:
    """
    Parse FastAPI route files and extract route definitions.
    Looks for patterns like:
        @router.get("/path")
        @router.post("/path")
        @app.get("/path")
    """
    routes = []
    route_pattern = re.compile(
        r'@(?:router|app)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]',
        re.IGNORECASE
    )

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for filename in files:
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(root, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (UnicodeDecodeError, PermissionError):
                continue

            rel_path = os.path.relpath(filepath, source_dir)
            parts = rel_path.split(os.sep)
            module = parts[0].replace('_', ' ').title() if len(parts) > 1 else "General"

            for match in route_pattern.finditer(content):
                method = match.group(1).upper()
                path = match.group(2)

                if not path.startswith('/'):
                    path = '/' + path

                # Try to extract Pydantic model fields from the function
                fields = _extract_fastapi_fields(content, match.end())

                # Try to extract title from docstring
                title = _extract_fastapi_docstring(content, match.end())

                routes.append(RouteInfo(
                    path=path,
                    method=method,
                    module=module,
                    title=title or f"{method} {path}",
                    description=title or "",
                    fields=fields,
                    permissions=[],
                    next_steps=[],
                    prerequisites=[],
                    tags=[module.lower()],
                ))

    return routes


def _extract_fastapi_fields(content: str, route_end: int) -> List[FieldDescription]:
    """Attempt to extract Pydantic model fields referenced in the route handler."""
    fields = []
    # Look for function definition after the decorator
    func_match = re.search(r'def\s+\w+\s*\([^)]*\b(\w+):\s*(\w+)\b', content[route_end:route_end + 500])
    if func_match:
        model_name = func_match.group(2)
        # Try to find the Pydantic model definition
        model_pattern = re.compile(
            rf'class\s+{model_name}\s*\([^)]*BaseModel[^)]*\):\s*((?:\s+\w+[^\n]*)+)',
            re.MULTILINE
        )
        model_match = model_pattern.search(content)
        if model_match:
            body = model_match.group(1)
            field_pattern = re.compile(r'(\w+)\s*:\s*(\w[\w\[\], ]*)')
            for fm in field_pattern.finditer(body):
                fields.append(FieldDescription(
                    name=fm.group(1),
                    type=fm.group(2).strip(),
                    description="",
                ))
    return fields


def _extract_fastapi_docstring(content: str, route_end: int) -> str:
    """Extract the docstring from the function right after the route decorator."""
    doc_match = re.search(r'"""([^"]+)"""', content[route_end:route_end + 1000])
    if doc_match:
        return doc_match.group(1).strip()[:200]
    return ""


# ═══════════════════════════════════════════
#  JSON Config Extractor
# ═══════════════════════════════════════════

def extract_json_routes(source_file: str) -> List[RouteInfo]:
    """Load routes from a pre-formatted JSON config file."""
    with open(source_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    routes_data = data.get("routes", [])
    return [RouteInfo(**r) for r in routes_data]


# ═══════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════

def _extract_route_title(content: str, match_start: int) -> str:
    """Try to find a comment or summary near the route definition."""
    # Look backward for a comment
    before = content[max(0, match_start - 200):match_start]
    comment_match = re.search(r'//\s*(.+)', before)
    if comment_match:
        return comment_match.group(1).strip()[:200]
    return ""


def deduplicate_routes(routes: List[RouteInfo]) -> List[RouteInfo]:
    """Remove duplicate routes (same path + method)."""
    seen = set()
    unique = []
    for route in routes:
        key = (route.path, route.method)
        if key not in seen:
            seen.add(key)
            unique.append(route)
    return unique


def main():
    parser = argparse.ArgumentParser(description="Extract ERP routes into Route Registry JSON")
    parser.add_argument("--source", required=True, help="Source directory or file")
    parser.add_argument("--type", required=True, choices=["express", "fastapi", "json"],
                        help="Type of source code to parse")
    parser.add_argument("--output", default="./app/data/route_registry.json", help="Output JSON file")
    parser.add_argument("--module", default="", help="Override module name for all routes")
    args = parser.parse_args()

    print(f"[route_extractor] Extracting {args.type} routes from: {args.source}")

    if args.type == "express":
        routes = extract_express_routes(args.source)
    elif args.type == "fastapi":
        routes = extract_fastapi_routes(args.source)
    elif args.type == "json":
        routes = extract_json_routes(args.source)
    else:
        print(f"Unknown type: {args.type}")
        return

    # Deduplicate
    routes = deduplicate_routes(routes)

    # Override module if specified
    if args.module:
        for route in routes:
            route.module = args.module

    # Save
    output_data = {
        "routes": [r.model_dump() for r in routes]
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"[route_extractor] Extracted {len(routes)} routes → {args.output}")


if __name__ == "__main__":
    main()
