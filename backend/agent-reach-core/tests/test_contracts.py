"""
Tests for the Contract system.

Test the InMemoryContractRegistry and ContractValidator.
"""

import pytest
import asyncio
from datetime import datetime

from agent_reach.core.contracts import (
    Contract,
    ContractStatus,
    ContractType,
    InMemoryContractRegistry,
)
from agent_reach.core.contracts.validator import ContractValidator


@pytest.fixture
def registry() -> InMemoryContractRegistry:
    """Create a contract registry for testing."""
    return InMemoryContractRegistry()


@pytest.fixture
def validator(registry: InMemoryContractRegistry) -> ContractValidator:
    """Create a contract validator for testing."""
    return ContractValidator(registry)


@pytest.fixture
def sample_contract() -> Contract:
    """Create a sample contract for testing."""
    return Contract(
        id="contract.input.research.v1",
        name="Research Agent Input Contract",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="agent.research.v1",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    )


def test_register_contract(
    registry: InMemoryContractRegistry,
    sample_contract: Contract,
) -> None:
    """Test registering a contract."""
    asyncio.run(registry.register(sample_contract))
    retrieved = asyncio.run(registry.get(sample_contract.id))
    assert retrieved is not None
    assert retrieved.id == sample_contract.id


def test_validate_contract_valid(
    registry: InMemoryContractRegistry,
    validator: ContractValidator,
    sample_contract: Contract,
) -> None:
    """Test validating valid data against a contract."""
    asyncio.run(registry.register(sample_contract))
    
    valid_data = {"query": "test query", "max_results": 10}
    errors = asyncio.run(validator.validate(sample_contract.id, valid_data))
    assert len(errors) == 0


def test_validate_contract_invalid(
    registry: InMemoryContractRegistry,
    validator: ContractValidator,
    sample_contract: Contract,
) -> None:
    """Test validating invalid data against a contract."""
    asyncio.run(registry.register(sample_contract))
    
    # Missing required field "query"
    invalid_data = {"max_results": 10}
    errors = asyncio.run(validator.validate(sample_contract.id, invalid_data))
    assert len(errors) > 0


def test_contract_status_inactive(
    registry: InMemoryContractRegistry,
    validator: ContractValidator,
) -> None:
    """Test that inactive contracts fail validation."""
    inactive_contract = Contract(
        id="inactive.contract",
        name="Inactive Contract",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.DRAFT,
        plugin_id="test.plugin",
        schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    
    asyncio.run(registry.register(inactive_contract))
    
    data = {"query": "test"}
    errors = asyncio.run(validator.validate("inactive.contract", data))
    assert len(errors) > 0  # Should have errors - contract not active


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
