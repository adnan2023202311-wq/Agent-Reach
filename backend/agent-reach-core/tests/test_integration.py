"""
Integration tests for Agent Reach.

Tests the full workflow:
- Plugin manifest creation and registration
- Contract creation and registration
- Data validation against contracts
- Plugin loading
"""

import asyncio
import pytest
from datetime import datetime

from agent_reach.core.contracts.models import (
    Contract,
    ContractStatus,
    ContractType,
)
from agent_reach.core.contracts.registry import InMemoryContractRegistry
from agent_reach.core.contracts.validator import ContractValidator
from agent_reach.core.plugin.manifest import PluginManifest
from agent_reach.core.plugin.static_loader import StaticPluginLoader


def test_full_plugin_workflow() -> None:
    """
    Test the full plugin workflow.
    """
    # 1. Create plugin manifest
    manifest = PluginManifest(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type="agent",
        description="Agent for researching information",
        author="Agent Reach Team",
        capabilities=["search", "summarize"],
        dependencies=[],
        entry_point="agent_reach.agents.research:ResearchAgent",
    )
    
    # 2. Register plugin
    loader = StaticPluginLoader()
    loader.register_plugin(manifest)
    
    # 3. Verify plugin can be loaded
    loaded_manifest = asyncio.run(loader.load_manifest("agent.research.v1"))
    assert loaded_manifest is not None
    assert loaded_manifest.id == "agent.research.v1"
    
    # 4. Create and register contract
    contract = Contract(
        id="contract.research.input",
        name="Research Input Contract",
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
    
    registry = InMemoryContractRegistry()
    asyncio.run(registry.register(contract))
    
    # 5. Validate data against contract
    validator = ContractValidator(registry)
    valid_data = {"query": "test query", "max_results": 10}
    errors = asyncio.run(validator.validate(contract.id, valid_data))
    assert isinstance(errors, list)
    assert len(errors) == 0  # Valid data should have no errors
    
    # 6. Verify plugin can be discovered
    discovered = asyncio.run(loader.discover())
    assert "agent.research.v1" in discovered
    
    # 7. Unload plugin
    result = asyncio.run(loader.unload_plugin("agent.research.v1"))
    assert result is True


def test_contract_validation_workflow() -> None:
    """
    Test contract validation workflow.
    """
    # Register a contract
    contract = Contract(
        id="contract.test.input",
        name="Test Input Contract",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="test.plugin",
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    )
    
    registry = InMemoryContractRegistry()
    asyncio.run(registry.register(contract))
    
    # Validate valid data
    validator = ContractValidator(registry)
    valid_data = {"message": "hello"}
    errors = asyncio.run(validator.validate(contract.id, valid_data))
    assert isinstance(errors, list)
    assert len(errors) == 0  # Valid data should have no errors
    
    # Validate invalid data (missing required field)
    invalid_data = {}
    errors = asyncio.run(validator.validate(contract.id, invalid_data))
    assert isinstance(errors, list)
    assert len(errors) > 0  # Invalid data should have errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
