"""
Contract registry interface for Agent Reach.

Defines the contract that all contract registry implementations must fulfill.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, List, Optional

from .models import Contract, ContractStatus, ContractType


class ContractRegistry:
    """
    Interface for contract registry.
    
    Responsible for:
    - Registering contracts
    - Retrieving contracts
    - Validating against contracts
    """
    
    @abstractmethod
    async def register(self, contract: Contract) -> None:
        """
        Register a contract.
        
        Args:
            contract: The contract to register
            
        Raises:
            ContractError: If a contract with the same ID already exists
        """
        ...
    
    @abstractmethod
    async def get(self, contract_id: str) -> Optional[Contract]:
        """
        Get a contract by ID.
        
        Args:
            contract_id: The ID of the contract
            
        Returns:
            The contract, or None if not found
        """
        ...
    
    @abstractmethod
    async def get_by_plugin(self, plugin_id: str) -> List[Contract]:
        """
        Get all contracts for a plugin.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            List of contracts for the plugin
        """
        ...
    
    @abstractmethod
    async def validate(self, contract_id: str, data: dict[str, Any]) -> bool:
        """
        Validate data against a contract.
        
        Args:
            contract_id: The ID of the contract
            data: The data to validate
            
        Returns:
            True if valid, False otherwise
        """
        ...
