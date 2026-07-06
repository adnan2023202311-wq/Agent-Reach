"""
Schema resolution for Agent Reach.

Loads and resolves JSON schemas for plugins and contracts.
"""

from __future__ import annotations

import json
import os
from typing import Any


class SchemaResolver:
    """
    Resolves JSON schemas from the filesystem.
    
    Loads schema files and provides access to them.
    """
    
    def __init__(self, schema_dir: str) -> None:
        """
        Initialize with schema directory.
        
        Args:
            schema_dir: Path to directory containing schema files
        """
        self._schema_dir = schema_dir
        self._schemas: dict[str, Any] = {}
        self._load_schemas()
    
    def _load_schemas(self) -> None:
        """Load all schema files from the schema directory."""
        if not os.path.exists(self._schema_dir):
            return
        
        for filename in os.listdir(self._schema_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self._schema_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        schema = json.load(f)
                        schema_id = filename.replace('.json', '')
                        self._schemas[schema_id] = schema
                except Exception as e:
                    print(f"Error loading schema {filename}: {e}")
    
    def get_schema(self, schema_id: str) -> dict[str, Any] | None:
        """
        Get a schema by ID.
        
        Args:
            schema_id: The schema ID (filename without .json)
            
        Returns:
            The schema dictionary, or None if not found
        """
        return self._schemas.get(schema_id)
    
    def list_schemas(self) -> list[str]:
        """
        List all available schema IDs.
        
        Returns:
            List of schema IDs
        """
        return list(self._schemas.keys())
    
    def validate_against_schema(
        self,
        data: dict[str, Any],
        schema_id: str
    ) -> tuple[bool, list[str]]:
        """
        Validate data against a schema.
        
        Args:
            data: The data to validate
            schema_id: The schema ID to validate against
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        schema = self.get_schema(schema_id)
        if not schema:
            return False, [f"Schema {schema_id} not found"]
        
        errors = []
        
        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"Required field '{field}' is missing")
        
        # Check property types (basic validation)
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type:
                    if not self._check_type(value, expected_type):
                        errors.append(f"Field '{key}' has wrong type")
        
        return len(errors) == 0, errors
    
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
