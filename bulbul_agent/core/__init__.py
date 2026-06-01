"""Core Agent Package - Exposes the customizable Bulbul agent."""

from .persona_service import PersonaService
from .memory_service import MemoryService

__all__ = [
    'reset_user_persona',
    '_agent',
    '_persona_service',
    '_memory_service',
    'PersonaService',
    'MemoryService',
]


def __getattr__(name: str):
    """Load heavyweight agent services only when they are explicitly requested."""
    if name in {'reset_user_persona', '_agent', '_persona_service', '_memory_service'}:
        from . import service
        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
