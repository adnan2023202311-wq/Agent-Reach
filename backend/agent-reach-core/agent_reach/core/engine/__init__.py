"""
Execution engine package for Agent Reach.

Provides plugin execution with contract validation and an event bus
for inter-plugin communication.
"""

from .events import EventBus
from .executor import ExecutionEngine, ExecutionResult

__all__ = [
    "EventBus",
    "ExecutionEngine",
    "ExecutionResult",
]
