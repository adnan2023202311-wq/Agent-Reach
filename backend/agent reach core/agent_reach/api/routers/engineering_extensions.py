"""
API layer: /api/v1/engineering/extensions — Engineering Extensions (M10.33).

Test generation and documentation generation agents. Automates the
creation of unit tests, integration tests, API docs, and code comments.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/engineering/extensions", tags=["engineering-extensions"])


class GeneratedTest(BaseModel):
    test_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    test_file: str
    test_type: str = "unit"  # unit | integration | e2e
    language: str = "python"
    content: str = ""
    test_count: int = 0
    coverage_estimate: float = 0.0
    created_at: float = Field(default_factory=time.time)


class GeneratedDoc(BaseModel):
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    doc_type: str = "module"  # module | function | class | api | readme
    format: str = "markdown"
    content: str = ""
    created_at: float = Field(default_factory=time.time)


_tests: dict[str, GeneratedTest] = {}
_docs: dict[str, GeneratedDoc] = {}


class GenerateTestsRequest(BaseModel):
    file_path: str
    language: str = "python"
    content: str
    test_type: str = "unit"


@router.post("/tests/generate")
async def generate_tests(request: GenerateTestsRequest) -> dict[str, Any]:
    """Generate tests for a source file."""
    import re
    # Extract function names
    if request.language == "python":
        functions = re.findall(r"^\s*(?:async\s+)?def\s+(\w+)", request.content, re.MULTILINE)
        classes = re.findall(r"^\s*class\s+(\w+)", request.content, re.MULTILINE)
    else:
        functions = re.findall(r"function\s+(\w+)", request.content)
        classes = []

    test_lines = [
        f'"""Tests for {request.file_path}."""',
        "",
        "import pytest",
        "",
    ]
    # Add imports based on source
    if request.language == "python":
        module_name = request.file_path.replace("/", ".").replace(".py", "")
        test_lines.append(f"from {module_name} import *")
    test_lines.append("")

    # Generate a test per function
    for fn in functions:
        if fn.startswith("_"):
            continue
        test_lines.extend([
            f"def test_{fn}_returns_expected():",
            f'    """Test that {fn} returns the expected result."""',
            f"    # TODO: Implement test for {fn}",
            f"    # Arrange",
            f"    # Act",
            f"    # result = {fn}(...)",
            f"    # Assert",
            f"    # assert result == expected",
            f"    pass",
            "",
        ])

    # Generate a test per class
    for cls in classes:
        test_lines.extend([
            f"class Test{cls}:",
            f'    """Tests for the {cls} class."""',
            "",
            f"    def test_initialization(self):",
            f"        # TODO: Test {cls} initialization",
            f"        pass",
            "",
        ])

    test_content = "\n".join(test_lines)
    test_file = request.file_path.replace(".py", "_test.py").replace(".ts", "_test.ts")
    test = GeneratedTest(
        source_file=request.file_path, test_file=test_file, test_type=request.test_type,
        language=request.language, content=test_content,
        test_count=len(functions) + len(classes),
        coverage_estimate=min(0.8, (len(functions) + len(classes)) * 0.1),
    )
    _tests[test.test_id] = test
    return test.model_dump()


@router.get("/tests")
async def list_generated_tests(limit: int = 20) -> dict[str, Any]:
    tests = sorted(_tests.values(), key=lambda t: t.created_at, reverse=True)
    return {"tests": [t.model_dump() for t in tests[:limit]], "count": len(tests)}


@router.get("/tests/{test_id}")
async def get_test(test_id: str) -> dict[str, Any]:
    test = _tests.get(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    return test.model_dump()


class GenerateDocRequest(BaseModel):
    file_path: str
    language: str = "python"
    content: str
    doc_type: str = "module"
    format: str = "markdown"


@router.post("/docs/generate")
async def generate_docs(request: GenerateDocRequest) -> dict[str, Any]:
    """Generate documentation for a source file."""
    import re
    if request.language == "python":
        functions = re.findall(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", request.content, re.MULTILINE)
        classes = re.findall(r"^\s*class\s+(\w+)(?:\(([^)]*)\))?", request.content, re.MULTILINE)
        module_doc = re.search(r'^""".*?"""', request.content, re.DOTALL)
    else:
        functions = re.findall(r"function\s+(\w+)\s*\(([^)]*)\)", request.content)
        classes = []
        module_doc = None

    doc_lines = [
        f"# {request.file_path}",
        "",
        "## Overview",
        "",
        f"This module is part of the Agent Reach platform.",
        "",
    ]

    if classes:
        doc_lines.extend(["## Classes", ""])
        for cls in classes:
            doc_lines.extend([
                f"### `{cls[0]}`",
                "",
                f"{'Inherits from: `' + cls[1] + '`' if len(cls) > 1 and cls[1] else ''}",
                "",
            ])

    if functions:
        doc_lines.extend(["## Functions", ""])
        for fn in functions:
            doc_lines.extend([
                f"### `{fn[0]}({fn[1]})`",
                "",
                f"**Parameters:** `{fn[1]}`" if fn[1] else "No parameters.",
                "",
                "**Returns:** To be documented.",
                "",
            ])

    doc_lines.extend([
        "## Usage",
        "",
        f"```{request.language}",
        f"# Example usage of {request.file_path}",
        "```",
        "",
    ])

    doc = GeneratedDoc(
        source_file=request.file_path, doc_type=request.doc_type, format=request.format,
        content="\n".join(doc_lines),
    )
    _docs[doc.doc_id] = doc
    return doc.model_dump()


@router.get("/docs")
async def list_generated_docs(limit: int = 20) -> dict[str, Any]:
    docs = sorted(_docs.values(), key=lambda d: d.created_at, reverse=True)
    return {"docs": [d.model_dump() for d in docs[:limit]], "count": len(docs)}


@router.get("/stats")
async def extension_stats() -> dict[str, Any]:
    return {
        "tests_generated": len(_tests),
        "docs_generated": len(_docs),
        "total_test_functions": sum(t.test_count for t in _tests.values()),
        "avg_coverage_estimate": sum(t.coverage_estimate for t in _tests.values()) / max(1, len(_tests)),
    }
