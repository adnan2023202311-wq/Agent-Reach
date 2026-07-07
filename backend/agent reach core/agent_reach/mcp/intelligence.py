"""
MCP Intelligence (M7.12).

Enhanced MCP layer with automatic tool discovery, ranking,
recommendation, capability detection, dynamic selection,
and benchmarking.

Extends the existing MCPRuntime from Milestone 4.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from mcp.runtime import MCPRuntime, MCPToolDefinition, MCPRequest, MCPResponse


class ToolRankingMethod(str, Enum):
    """How tools are ranked."""
    USAGE = "usage"
    SUCCESS_RATE = "success_rate"
    LATENCY = "latency"
    EFFECTIVENESS = "effectiveness"


@dataclass
class ToolStats:
    """Runtime statistics for a tool."""
    tool_name: str = ""
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    last_used: float = 0.0
    capability_tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successes / max(1, self.total_calls)


@dataclass
class ToolRanking:
    """A ranked tool entry."""
    definition: MCPToolDefinition
    stats: ToolStats
    score: float = 0.0
    rank: int = 0


@dataclass
class ToolBenchmark:
    """Benchmark result for a tool."""
    tool_name: str = ""
    avg_latency_ms: float = 0.0
    success_rate: float = 0.0
    runs: int = 0
    timestamp: float = field(default_factory=time.time)


class MCPIntelligence:
    """Intelligent MCP tool management layer.

    Extends MCPRuntime with:
    - Automatic tool discovery by capability tags
    - Tool ranking by usage, success rate, latency
    - Tool recommendation for tasks
    - Dynamic tool selection
    - Tool benchmarking
    - Capability detection
    """

    def __init__(self) -> None:
        self._runtime = MCPRuntime()
        self._stats: dict[str, ToolStats] = {}
        self._benchmarks: dict[str, list[ToolBenchmark]] = defaultdict(list)
        self._capability_index: dict[str, list[str]] = defaultdict(list)  # tag -> [tool_names]

    @property
    def runtime(self) -> MCPRuntime:
        return self._runtime

    # ------------------------------------------------------------------
    # Registration with capabilities
    # ------------------------------------------------------------------

    def register_tool(
        self,
        definition: MCPToolDefinition,
        executor: Any,
        capability_tags: Optional[list[str]] = None,
    ) -> None:
        """Register a tool with capability tags."""
        self._runtime.register_tool(definition, executor)
        tags = capability_tags or []
        self._stats[definition.name] = ToolStats(
            tool_name=definition.name,
            capability_tags=list(tags),
        )
        for tag in tags:
            self._capability_index[tag].append(definition.name)

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def discover_by_capability(self, capabilities: list[str]) -> list[MCPToolDefinition]:
        """Discover tools matching one or more capability tags."""
        matching: set[str] = set()
        for cap in capabilities:
            matching.update(self._capability_index.get(cap, []))
        return [t for t in self._runtime.list_tools() if t.name in matching]

    def detect_capabilities(self, task_description: str) -> list[str]:
        """Detect required capabilities from a task description."""
        task_lower = task_description.lower()
        detected: list[str] = []

        capability_keywords = {
            "web_search": ["search", "web", "internet", "google", "find online"],
            "code_execution": ["code", "run", "execute", "python", "script"],
            "file_io": ["file", "read", "write", "save", "load", "open"],
            "image": ["image", "picture", "photo", "draw", "generate image"],
            "database": ["database", "sql", "query", "db"],
            "api_call": ["api", "http", "request", "fetch", "endpoint"],
            "calculation": ["calculate", "compute", "math", "sum", "average"],
        }

        for capability, keywords in capability_keywords.items():
            if any(kw in task_lower for kw in keywords):
                detected.append(capability)

        return detected or ["general"]

    # ------------------------------------------------------------------
    # Tool ranking
    # ------------------------------------------------------------------

    def rank_tools(
        self,
        method: ToolRankingMethod = ToolRankingMethod.EFFECTIVENESS,
        limit: int = 10,
    ) -> list[ToolRanking]:
        """Rank all registered tools."""
        rankings: list[ToolRanking] = []

        for tool in self._runtime.list_tools():
            stats = self._stats.get(tool.name, ToolStats(tool_name=tool.name))

            if method == ToolRankingMethod.USAGE:
                score = float(stats.total_calls)
            elif method == ToolRankingMethod.SUCCESS_RATE:
                score = stats.success_rate
            elif method == ToolRankingMethod.LATENCY:
                score = 1.0 / (1.0 + stats.avg_latency_ms / 1000.0) if stats.avg_latency_ms > 0 else 0.5
            else:  # effectiveness
                score = (
                    stats.success_rate * 0.5
                    + min(1.0, stats.total_calls / 50.0) * 0.3
                    + (1.0 / (1.0 + stats.avg_latency_ms / 1000.0)) * 0.2
                )

            rankings.append(ToolRanking(definition=tool, stats=stats, score=score))

        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1

        return rankings[:limit]

    def recommend_tools(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[ToolRanking]:
        """Recommend tools for a specific task."""
        capabilities = self.detect_capabilities(task_description)
        candidates = self.discover_by_capability(capabilities)

        if not candidates:
            return self.rank_tools(limit=limit)

        rankings: list[ToolRanking] = []
        for tool in candidates:
            stats = self._stats.get(tool.name, ToolStats(tool_name=tool.name))
            # Bonus for capability match
            score = (
                stats.success_rate * 0.4
                + min(1.0, stats.total_calls / 50.0) * 0.3
                + (1.0 / (1.0 + stats.avg_latency_ms / 1000.0)) * 0.3
            )
            rankings.append(ToolRanking(definition=tool, stats=stats, score=score))

        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1

        return rankings[:limit]

    def select_tool(self, task_description: str) -> Optional[MCPToolDefinition]:
        """Dynamically select the best tool for a task."""
        recommendations = self.recommend_tools(task_description, limit=1)
        if recommendations:
            return recommendations[0].definition
        return None

    # ------------------------------------------------------------------
    # Execution with stats
    # ------------------------------------------------------------------

    async def execute(self, request: MCPRequest) -> MCPResponse:
        """Execute a tool and record statistics."""
        start = time.perf_counter()
        response = await self._runtime.execute(request)
        latency_ms = (time.perf_counter() - start) * 1000

        stats = self._stats.setdefault(
            request.tool_name,
            ToolStats(tool_name=request.tool_name),
        )
        stats.total_calls += 1
        stats.last_used = time.time()
        stats.total_latency_ms += latency_ms
        stats.avg_latency_ms = stats.total_latency_ms / stats.total_calls

        if response.success:
            stats.successes += 1
        else:
            stats.failures += 1

        return response

    # ------------------------------------------------------------------
    # Benchmarking
    # ------------------------------------------------------------------

    async def benchmark_tool(
        self,
        tool_name: str,
        test_params: dict[str, Any],
        runs: int = 5,
    ) -> ToolBenchmark:
        """Benchmark a tool with repeated runs."""
        latencies: list[float] = []
        successes = 0

        for _ in range(runs):
            request = MCPRequest(tool_name=tool_name, parameters=dict(test_params))
            start = time.perf_counter()
            response = await self._runtime.execute(request)
            latencies.append((time.perf_counter() - start) * 1000)
            if response.success:
                successes += 1

        benchmark = ToolBenchmark(
            tool_name=tool_name,
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
            success_rate=successes / runs,
            runs=runs,
        )
        self._benchmarks[tool_name].append(benchmark)
        return benchmark

    def get_benchmarks(self, tool_name: str) -> list[ToolBenchmark]:
        """Get benchmark history for a tool."""
        return self._benchmarks.get(tool_name, [])

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_tool_stats(self, tool_name: str) -> Optional[ToolStats]:
        """Get stats for a specific tool."""
        return self._stats.get(tool_name)

    def get_all_stats(self) -> dict[str, ToolStats]:
        """Get stats for all tools."""
        return dict(self._stats)

    def get_stats(self) -> dict[str, Any]:
        """Get overall MCP intelligence statistics."""
        all_tools = self._runtime.list_tools()
        return {
            "total_tools": len(all_tools),
            "total_calls": sum(s.total_calls for s in self._stats.values()),
            "capability_tags": list(self._capability_index.keys()),
            "tools_with_benchmarks": len(self._benchmarks),
            "avg_success_rate": (
                sum(s.success_rate for s in self._stats.values()) / max(1, len(self._stats))
            ),
        }

    def clear(self) -> None:
        """Clear all registrations and stats."""
        self._runtime.clear()
        self._stats.clear()
        self._benchmarks.clear()
        self._capability_index.clear()
