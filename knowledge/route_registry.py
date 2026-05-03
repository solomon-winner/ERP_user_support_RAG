"""
Route Registry — loads and queries the JSON route registry.

The route_registry.json is the structured representation of every ERP
route/page, including its fields, permissions, and navigation links.
"""
import json
from typing import List, Optional, Dict
from app.models.schemas import RouteInfo, FieldDescription
from app.config import settings


class RouteRegistry:
    """In-memory route registry loaded from JSON file."""

    def __init__(self, registry_path: Optional[str] = None):
        self._path = registry_path or settings.ROUTE_REGISTRY_PATH
        self._routes: Dict[str, RouteInfo] = {}   # path → RouteInfo
        self._module_index: Dict[str, List[str]] = {}  # module → [paths]
        self._tag_index: Dict[str, List[str]] = {}     # tag → [paths]
        self._loaded = False

    def load(self) -> None:
        """Load route registry from JSON file."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"[RouteRegistry] File not found: {self._path}. Using empty registry.")
            self._loaded = True
            return
        except json.JSONDecodeError as e:
            print(f"[RouteRegistry] JSON parse error: {e}. Using empty registry.")
            self._loaded = True
            return

        routes_data = data.get("routes", [])
        for r in routes_data:
            route = RouteInfo(**r)
            self._routes[route.path] = route

            # Build module index
            if route.module not in self._module_index:
                self._module_index[route.module] = []
            self._module_index[route.module].append(route.path)

            # Build tag index
            for tag in route.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(route.path)

        self._loaded = True
        print(f"[RouteRegistry] Loaded {len(self._routes)} routes from {self._path}")

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def get_route(self, path: str) -> Optional[RouteInfo]:
        """Get route info by exact path match."""
        self._ensure_loaded()
        return self._routes.get(path)

    def search_routes(self, query: str, limit: int = 10) -> List[RouteInfo]:
        """Simple text search across route titles, descriptions, and tags."""
        self._ensure_loaded()
        query_lower = query.lower()
        results = []
        for route in self._routes.values():
            score = 0
            if query_lower in route.title.lower():
                score += 10
            if query_lower in route.description.lower():
                score += 5
            if query_lower in route.module.lower():
                score += 3
            if any(query_lower in tag.lower() for tag in route.tags):
                score += 2
            if score > 0:
                results.append((score, route))
        results.sort(key=lambda x: -x[0])
        return [r for _, r in results[:limit]]

    def get_routes_by_module(self, module: str) -> List[RouteInfo]:
        """Get all routes belonging to a module."""
        self._ensure_loaded()
        paths = self._module_index.get(module, [])
        return [self._routes[p] for p in paths if p in self._routes]

    def get_all_modules(self) -> List[str]:
        """Get list of all known modules."""
        self._ensure_loaded()
        return list(self._module_index.keys())

    def get_all_routes(self) -> List[RouteInfo]:
        """Get all registered routes."""
        self._ensure_loaded()
        return list(self._routes.values())

    def get_field(self, route_path: str, field_name: str) -> Optional[FieldDescription]:
        """Get a specific field description from a route."""
        self._ensure_loaded()
        route = self._routes.get(route_path)
        if not route:
            return None
        for field in route.fields:
            if field.name == field_name:
                return field
        return None

    def validate_route_exists(self, path: str) -> bool:
        """Check if a route path exists in the registry."""
        self._ensure_loaded()
        return path in self._routes

    def validate_field_exists(self, route_path: str, field_name: str) -> bool:
        """Check if a field exists on a given route."""
        return self.get_field(route_path, field_name) is not None

    def get_next_steps(self, path: str) -> List[RouteInfo]:
        """Get the next logical routes after the given path."""
        self._ensure_loaded()
        route = self._routes.get(path)
        if not route:
            return []
        return [self._routes[p] for p in route.next_steps if p in self._routes]

    def get_prerequisites(self, path: str) -> List[RouteInfo]:
        """Get prerequisite routes for the given path."""
        self._ensure_loaded()
        route = self._routes.get(path)
        if not route:
            return []
        return [self._routes[p] for p in route.prerequisites if p in self._routes]

    def route_count(self) -> int:
        self._ensure_loaded()
        return len(self._routes)


# Singleton instance
route_registry = RouteRegistry()
