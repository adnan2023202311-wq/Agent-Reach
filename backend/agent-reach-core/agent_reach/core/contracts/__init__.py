"""
Contracts package.

Provides contract models, registry, and validator for plugin contracts.
"""

from .interfaces import ContractRegistry
from .models import Contract, ContractStatus, ContractType
from .registry import InMemoryContractRegistry, ContractError
from .validator import ContractValidator

__all__ = [
    # Models
    "Contract",
    "ContractStatus",
    "ContractType",
    # Interfaces
    "ContractRegistry",
    # Implementations
    "InMemoryContractRegistry",
    "ContractValidator",
    # Exceptions
    "ContractError",
]
