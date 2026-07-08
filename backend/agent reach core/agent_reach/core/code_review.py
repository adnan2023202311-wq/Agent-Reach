"""
AI Code Review System (M9.15).

Layer: Application/Core.

Every code modification can be submitted for automated review. The
review has two tiers, each honest about what it is:

1. Static analysis (always runs, deterministic): AST-based checks
   covering the M9.15 list where it is objectively verifiable —
   security (eval/exec, shell=True, hardcoded secrets, bare except),
   maintainability (function length, parameter count, nesting depth),
   readability (missing docstrings on public defs), correctness
   hazards (mutable default arguments), and architecture layering
   (api/ importing infrastructure internals directly, core/ importing
   api/ — the project's own Clean Architecture rules).
2. Model review (optional): when requested, the diff is sent through
   the SHARED IntelligentPipeline for a qualitative narrative. The
   result is labeled model-generated and carries its trace request_id
   — it is advisory, never merged into the deterministic findings.

Verdicts derive from static findings only: `blocked` on any critical
security finding, `changes_requested` on warnings, `approved` when
clean. Model narrative never changes the verdict — a probabilistic
reviewer must not gate merges silently.
"""

from __future__ import annotations

import ast
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

_MAX_FUNCTION_LINES = 80
_MAX_PARAMETERS = 7
_MAX_NESTING_DEPTH = 5

_SECRET_PATTERN = re.compile(
    r"(?i)\b(api_key|apikey|secret|password|token)\b\s*=\s*[\"'][^\"']{8,}[\"']"
)

# Architecture layering rules from the project's own conventions.
_LAYER_RULES: tuple[tuple[str, str, str], ...] = (
    ("core/", "api.", "core/ must not import the api/ layer (dependency inversion)"),
    ("domain/", "api.", "domain/ must not import the api/ layer"),
    ("domain/", "infrastructure.", "domain/ must not import infrastructure/ (it owns the interfaces)"),
    ("api/", "infrastructure.model_client", "api/ should depend on composition-provided abstractions, not concrete clients"),
)


@dataclass
class ReviewFinding:
    """One deterministic static-analysis finding."""

    check: str  # security | maintainability | readability | correctness | architecture
    severity: str  # critical | warning | info
    line: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class ReviewResult:
    """One completed review."""

    review_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    reviewed_at: float = field(default_factory=time.time)
    findings: list[ReviewFinding] = field(default_factory=list)
    verdict: str = "approved"  # approved | changes_requested | blocked
    parse_error: Optional[str] = None
    model_review: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "file_path": self.file_path,
            "reviewed_at": self.reviewed_at,
            "findings": [f.to_dict() for f in self.findings],
            "verdict": self.verdict,
            "parse_error": self.parse_error,
            "model_review": dict(self.model_review) if self.model_review else None,
        }


class _Analyzer(ast.NodeVisitor):
    """AST visitor collecting deterministic findings."""

    def __init__(self, source_lines: list[str]) -> None:
        self.findings: list[ReviewFinding] = []
        self._source_lines = source_lines

    # -- security ------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("eval", "exec"):
            self.findings.append(
                ReviewFinding(
                    check="security",
                    severity="critical",
                    line=node.lineno,
                    message=f"Use of {func_name}() — arbitrary code execution risk.",
                )
            )
        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                self.findings.append(
                    ReviewFinding(
                        check="security",
                        severity="critical",
                        line=node.lineno,
                        message="subprocess call with shell=True — injection risk.",
                    )
                )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.findings.append(
                ReviewFinding(
                    check="security",
                    severity="warning",
                    line=node.lineno,
                    message="Bare 'except:' swallows every exception including SystemExit.",
                )
            )
        self.generic_visit(node)

    # -- functions -----------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end = getattr(node, "end_lineno", node.lineno)
        length = end - node.lineno + 1
        if length > _MAX_FUNCTION_LINES:
            self.findings.append(
                ReviewFinding(
                    check="maintainability",
                    severity="warning",
                    line=node.lineno,
                    message=(
                        f"Function '{node.name}' spans {length} lines "
                        f"(limit {_MAX_FUNCTION_LINES}) — consider extracting helpers."
                    ),
                )
            )

        params = node.args.args + node.args.kwonlyargs
        param_count = len([a for a in params if a.arg not in ("self", "cls")])
        if param_count > _MAX_PARAMETERS:
            self.findings.append(
                ReviewFinding(
                    check="maintainability",
                    severity="warning",
                    line=node.lineno,
                    message=(
                        f"Function '{node.name}' takes {param_count} parameters "
                        f"(limit {_MAX_PARAMETERS}) — consider a parameter object."
                    ),
                )
            )

        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.findings.append(
                    ReviewFinding(
                        check="correctness",
                        severity="warning",
                        line=default.lineno,
                        message=(
                            f"Mutable default argument in '{node.name}' — "
                            "shared across calls."
                        ),
                    )
                )

        if not node.name.startswith("_") and ast.get_docstring(node) is None:
            self.findings.append(
                ReviewFinding(
                    check="readability",
                    severity="info",
                    line=node.lineno,
                    message=f"Public function '{node.name}' has no docstring.",
                )
            )

        depth = self._max_depth(node, 0)
        if depth > _MAX_NESTING_DEPTH:
            self.findings.append(
                ReviewFinding(
                    check="maintainability",
                    severity="warning",
                    line=node.lineno,
                    message=(
                        f"Function '{node.name}' nests {depth} levels deep "
                        f"(limit {_MAX_NESTING_DEPTH})."
                    ),
                )
            )

    @classmethod
    def _max_depth(cls, node: ast.AST, depth: int) -> int:
        deepest = depth
        for child in ast.iter_child_nodes(node):
            child_depth = depth
            if isinstance(
                child, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                        ast.AsyncFor, ast.AsyncWith)
            ):
                child_depth += 1
            deepest = max(deepest, cls._max_depth(child, child_depth))
        return deepest


class CodeReviewEngine:
    """Deterministic static review + optional model narrative."""

    def __init__(self, pipeline: Any = None, max_reviews: int = 500) -> None:
        if max_reviews < 1:
            raise ValueError("max_reviews must be >= 1")
        self._pipeline = pipeline
        self._reviews: dict[str, ReviewResult] = {}
        self._max_reviews = max_reviews

    # ── Static analysis ─────────────────────────────────────────

    def review(self, source: str, file_path: str = "") -> ReviewResult:
        """Run the deterministic static review."""
        result = ReviewResult(file_path=file_path)
        lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            result.parse_error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
            result.verdict = "blocked"
            self._store(result)
            return result

        analyzer = _Analyzer(lines)
        analyzer.visit(tree)
        result.findings = analyzer.findings

        # Line-based checks (regexes over raw source).
        for line_number, line in enumerate(lines, start=1):
            if _SECRET_PATTERN.search(line):
                result.findings.append(
                    ReviewFinding(
                        check="security",
                        severity="critical",
                        line=line_number,
                        message="Possible hardcoded secret — credentials belong in the environment.",
                    )
                )

        # Architecture layering (needs the file's project location).
        if file_path:
            result.findings.extend(self._check_layering(tree, file_path))

        result.findings.sort(key=lambda f: f.line)
        result.verdict = self._verdict(result.findings)
        self._store(result)
        return result

    @staticmethod
    def _check_layering(tree: ast.AST, file_path: str) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        normalized = file_path.replace("\\", "/")
        imports: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend((node.lineno, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((node.lineno, node.module))

        for layer_prefix, forbidden, rule in _LAYER_RULES:
            if layer_prefix not in normalized:
                continue
            for lineno, module in imports:
                if module == forbidden.rstrip(".") or module.startswith(forbidden):
                    findings.append(
                        ReviewFinding(
                            check="architecture",
                            severity="warning",
                            line=lineno,
                            message=f"{rule} (imports '{module}').",
                        )
                    )
        return findings

    @staticmethod
    def _verdict(findings: list[ReviewFinding]) -> str:
        if any(f.severity == "critical" for f in findings):
            return "blocked"
        if any(f.severity == "warning" for f in findings):
            return "changes_requested"
        return "approved"

    # ── Model narrative (optional, advisory) ────────────────────

    async def review_with_model(self, source: str, file_path: str = "") -> ReviewResult:
        """Static review + model-generated narrative via the pipeline.

        The narrative is advisory: labeled, trace-linked, and it never
        changes the deterministic verdict.
        """
        result = self.review(source, file_path=file_path)
        if self._pipeline is None:
            result.model_review = {
                "available": False,
                "note": "No pipeline attached — static review only.",
            }
            return result
        try:
            pipeline_result = await self._pipeline.process(
                "Review this code change for architecture, SOLID adherence, "
                "security, performance, and readability. Suggest refactorings.\n\n"
                f"File: {file_path or '(unnamed)'}\n```python\n{source[:8000]}\n```"
            )
            result.model_review = {
                "available": True,
                "narrative": pipeline_result.outcome.answer,
                "request_id": pipeline_result.trace.request_id,
                "note": "Model-generated, advisory — verdict derives from static findings only.",
            }
        except Exception as exc:  # noqa: BLE001 — advisory tier must not break review
            result.model_review = {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return result

    # ── History ─────────────────────────────────────────────────

    def get_review(self, review_id: str) -> Optional[ReviewResult]:
        return self._reviews.get(review_id)

    def list_reviews(self, limit: int = 20) -> list[ReviewResult]:
        reviews = sorted(
            self._reviews.values(), key=lambda r: r.reviewed_at, reverse=True
        )
        return reviews[: max(0, limit)]

    def get_stats(self) -> dict[str, Any]:
        reviews = list(self._reviews.values())
        return {
            "total_reviews": len(reviews),
            "verdicts": {
                verdict: sum(1 for r in reviews if r.verdict == verdict)
                for verdict in ("approved", "changes_requested", "blocked")
            },
            "total_findings": sum(len(r.findings) for r in reviews),
        }

    def clear(self) -> None:
        self._reviews.clear()

    def _store(self, result: ReviewResult) -> None:
        self._reviews[result.review_id] = result
        while len(self._reviews) > self._max_reviews:
            oldest = min(self._reviews.values(), key=lambda r: r.reviewed_at)
            del self._reviews[oldest.review_id]
