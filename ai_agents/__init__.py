from importlib import import_module
from typing import Optional

__all__ = []


def _optional_import(module_name: str, attr_name: str) -> Optional[object]:
    try:
        module = import_module(f".{module_name}", __name__)
        attr = getattr(module, attr_name)
    except ModuleNotFoundError:
        return None
    globals()[attr_name] = attr
    __all__.append(attr_name)
    return attr


_optional_import("planning_agent", "PlanningAgent")
_optional_import("retrieval_service", "RetrievalService")
_optional_import("doc_processing", "DocumentProcessor")
_optional_import("rag_agent", "RAGAgent")
_optional_import("refinement_module", "RefinementModule")
