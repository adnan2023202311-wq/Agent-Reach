"""
In-memory contract registry implementation.

Stores contracts in memory (no persistence).
"""

from __future__ import annotations

from typing import Any, List, Optional

from .interfaces import ContractRegistry
from .models import Contract, ContractStatus, ContractType


class InMemoryContractRegistry(ContractRegistry):
    """
    In-memory implementation of ContractRegistry.
    
    Stores all contracts in a dictionary keyed by contract ID.
    Useful for development and testing.
    """
    
    def __init__(self) -> None:
        """Initialize with empty contract store."""
        self._contracts: dict[str, Contract] = {}
    
    async def register(self, contract: Contract) -> None:
        """Register a contract."""
        if contract.id in self._contracts:
            raise ContractError(f"Contract {contract.id} already registered")
        
        self._contracts[contract.id] = contract
    
    async def get(self, contract_id: str) -> Optional[Contract]:
        """Get contract by ID."""
        return self._contracts.get(contract_id)
    
    async def get_by_plugin(self, plugin_id: str) -> List[Contract]:
        """Get all contracts for a plugin."""
        return [
            contract for contract in self._contracts.values()
            if contract.plugin_id == plugin_id
        ]
    
    async def validate(self, contract_id: str, data: dict[str, Any]) -> bool:
        """Validate data against contract schema."""
        contract = self._contracts.get(contract_id)
        if not contract:
            return False
        
        # Simple validation - check required fields
        schema = contract.schema
        required = schema.get("required", [])
        
        for field in required:
            if field not in data:
                return False
        
        return True
    
    def clear(self) -> None:
        """Clear all contracts. Useful for testing."""
        self._contracts.clear()


class ContractError(Exception):
    """Contract registry error."""
    pass
