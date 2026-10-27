"""Read-only hardware knowledge services; no LLM or network dependencies."""

from .service import CatalogError, KnowledgeCatalog

__all__ = ["CatalogError", "KnowledgeCatalog"]
