"""
Contracts package.

Provides contract models and registry for plugin contracts.
"""

from .interfaces import ContractRegistry
from .models import Contract, ContractStatus, ContractType
from .registry import InMemoryContractRegistry, ContractError

__all__ = [
    # Models
    "Contract",
    "ContractStatus",
    "ContractType",
    # Interfaces
    "ContractRegistry",
    # Implementations
    "InMemoryContractRegistry",
    # Exceptions
    "ContractError",
]
