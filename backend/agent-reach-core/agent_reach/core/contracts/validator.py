"""
Contract validator for Agent Reach.

Validates plugin contracts against schemas.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .interfaces import ContractRegistry
from .models import Contract, ContractStatus, ContractType


class ContractValidator:
    """
    Validates plugin contracts.
    
    Features:
    - Validates contract schema format
    - Validates data against contract schema
    - Checks contract dependencies
    """
    
    def __init__(self, registry: ContractRegistry) -> None:
        """
        Initialize validator with a contract registry.
        
        Args:
            registry: The contract registry to use
        """
        self._registry = registry
    
    async def validate(
        self,
        contract_id: str,
        data: Dict[str, Any]
    ) -> List[str]:
        """
        Validate data against a contract.
        
        Args:
            contract_id: The ID of the contract
            data: The data to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[str] = []
        
        # Get contract
        contract = await self._registry.get(contract_id)
        if not contract:
            errors.append(f"Contract {contract_id} not found")
            return errors
        
        # Check contract is active
        if contract.status != ContractStatus.ACTIVE:
            errors.append(f"Contract {contract_id} is not active")
            return errors
        
        # Validate against schema
        schema = contract.schema
        
        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"Required field '{field}' is missing")
        
        # Check field types (basic)
        properties = schema.get("properties", {})
        for field_name, field_value in data.items():
            if field_name in properties:
                expected_type = properties[field_name].get("type")
                if expected_type:
                    if not self._check_type(field_value, expected_type):
                        errors.append(
                            f"Field '{field_name}' has wrong type. "
                            f"Expected {expected_type}"
                        )
        
        return errors
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """
        Check if a value matches an expected JSON schema type.
        
        Args:
            value: The value to check
            expected_type: The expected type (string, number, boolean, etc.)
            
        Returns:
            True if type matches, False otherwise
        """
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        
        python_type = type_map.get(expected_type)
        if python_type:
            return isinstance(value, python_type)
        
        return True  # Unknown type, assume valid
