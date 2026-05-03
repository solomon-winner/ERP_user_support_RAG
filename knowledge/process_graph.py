"""
Process Graph — loads and traverses business process workflows.

The process_graphs.json contains ordered step sequences for each ERP
business process (e.g., payroll_run, invoice_creation, month_end_closing).
"""
import json
from typing import List, Optional, Dict
from app.models.schemas import ProcessGraph, ProcessStep
from app.config import settings


class ProcessGraphStore:
    """In-memory process graph store loaded from JSON."""

    def __init__(self, graphs_path: Optional[str] = None):
        self._path = graphs_path or settings.PROCESS_GRAPHS_PATH
        self._processes: Dict[str, ProcessGraph] = {}  # process_name → ProcessGraph
        self._route_index: Dict[str, List[str]] = {}   # route_path → [process_names]
        self._loaded = False

    def load(self) -> None:
        """Load process graphs from JSON file."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"[ProcessGraph] File not found: {self._path}. Using empty store.")
            self._loaded = True
            return
        except json.JSONDecodeError as e:
            print(f"[ProcessGraph] JSON parse error: {e}. Using empty store.")
            self._loaded = True
            return

        processes_data = data.get("processes", [])
        for p in processes_data:
            process = ProcessGraph(**p)
            self._processes[process.process_name] = process

            # Build route → process index
            for step in process.steps:
                if step.route not in self._route_index:
                    self._route_index[step.route] = []
                if process.process_name not in self._route_index[step.route]:
                    self._route_index[step.route].append(process.process_name)

        self._loaded = True
        print(f"[ProcessGraph] Loaded {len(self._processes)} processes from {self._path}")

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def get_process(self, process_name: str) -> Optional[ProcessGraph]:
        """Get a process by name."""
        self._ensure_loaded()
        return self._processes.get(process_name)

    def get_processes_for_route(self, route_path: str) -> List[ProcessGraph]:
        """Find all processes that include a given route as a step."""
        self._ensure_loaded()
        process_names = self._route_index.get(route_path, [])
        return [self._processes[n] for n in process_names if n in self._processes]

    def get_step_in_process(self, process_name: str, step_order: int) -> Optional[ProcessStep]:
        """Get a specific step in a process by its order number."""
        self._ensure_loaded()
        process = self._processes.get(process_name)
        if not process:
            return None
        for step in process.steps:
            if step.order == step_order:
                return step
        return None

    def get_next_step(self, process_name: str, current_route: str) -> Optional[ProcessStep]:
        """Get the next step after the current route in a process."""
        self._ensure_loaded()
        process = self._processes.get(process_name)
        if not process:
            return None
        for i, step in enumerate(process.steps):
            if step.route == current_route and i + 1 < len(process.steps):
                return process.steps[i + 1]
        return None

    def get_remaining_steps(self, process_name: str, current_route: str) -> List[ProcessStep]:
        """Get all remaining steps after the current route in a process."""
        self._ensure_loaded()
        process = self._processes.get(process_name)
        if not process:
            return []
        found = False
        remaining = []
        for step in process.steps:
            if found:
                remaining.append(step)
            if step.route == current_route:
                found = True
        return remaining

    def search_processes(self, query: str, limit: int = 10) -> List[ProcessGraph]:
        """Simple text search across process names, titles, and descriptions."""
        self._ensure_loaded()
        query_lower = query.lower()
        results = []
        for process in self._processes.values():
            score = 0
            if query_lower in process.title.lower():
                score += 10
            if query_lower in process.process_name.lower():
                score += 8
            if query_lower in process.description.lower():
                score += 5
            if query_lower in process.module.lower():
                score += 3
            if score > 0:
                results.append((score, process))
        results.sort(key=lambda x: -x[0])
        return [p for _, p in results[:limit]]

    def get_all_processes(self) -> List[ProcessGraph]:
        self._ensure_loaded()
        return list(self._processes.values())

    def process_count(self) -> int:
        self._ensure_loaded()
        return len(self._processes)


# Singleton instance
process_graph_store = ProcessGraphStore()
