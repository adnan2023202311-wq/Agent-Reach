# Agent Reach — Technical Debt

## Current Technical Debt

### Milestone 1 (Complete)
- `datetime.utcnow()` is deprecated — should migrate to `datetime.now(timezone.utc)`
  across all models. Non-blocking; tracked as a cleanup item.

### Milestone 2 (Complete)
- **Plugin system path coupling**: `agents/plugin_agent.py` manipulates `sys.path`
  to import `agent_reach.core...`. Both `backend/agent-reach-core/` and
  `backend/agent reach core/agent_reach/` must be on `PYTHONPATH` in production.
  A proper packaging setup (e.g., editable installs) would eliminate this.
- **Circular import workaround**: `PluginManager` uses a lazy import for
  `ExecutionEngine` to avoid a circular dependency between
  `agent_reach.core.engine.executor` and `agent_reach.core.plugin.manager`.
  A future refactor could merge or restructure these modules.
- **EventBus is in-memory only**: No persistence or cross-process event routing.
  Acceptable for single-process deployments; distributed events belong to a
  future milestone.
- **DynamicPluginLoader error handling**: Invalid manifests are silently skipped.
  A production system might want structured logging or a "broken plugins" report.
- **Kernel bridge heuristic agent mapping**: `_map_capability_to_agent_type()`
  uses simple keyword matching. This is sufficient for the current capability IDs
  but may need a more explicit mapping mechanism as the plugin ecosystem grows.
- **No plugin hot-reloading**: Plugins are loaded once at startup. Unloading and
  reloading requires a process restart.

### Milestone 3 (Complete)
- **AgentRuntime is in-memory only**: Sessions are not persisted across restarts.
  A future milestone could add SQLite or Redis-backed session storage.
- **Planner is rule-based**: The Planner builds plans from explicit step lists.
  LLM-driven autonomous planning is out of scope for M3 but anticipated in
  future milestones.
- **AgentMessenger is in-process only**: No distributed or cross-process
  messaging. This is by design for M3 but will need extension for multi-node
  deployments.
- **RuntimeMonitor aggregates from runtime sessions**: If sessions are destroyed,
  historical metrics are lost unless external persistence is added.
- **AgentBase validation is synchronous**: `validate_input` and `validate_output`
  are sync methods. Async validation could be added if needed in the future.
- **ToolExecutor timeout is asyncio-only**: Tools that block the event loop
  (e.g., CPU-bound sync functions) may not respect asyncio timeouts.
- **MemoryBridge uses InMemoryStore**: No persistence. Conversation and execution
  history are lost on restart.
- **PlanStep.condition is a simple string**: Conditional branching uses string
  expressions rather than a structured condition language or safe eval.

### Milestone 4 (Complete)
- **Observability is in-memory only**: Traces and spans are lost on process
  restart. A future milestone could add persistence or export to external systems.
- **Metrics are in-memory only**: No time-series storage or external push.
- **CapabilityResolver has no distributed resolution**: All capabilities must be
  registered in-process. A future milestone could add remote capability discovery.
- **MCP Runtime is in-process only**: No network transport or stdio server.
  Full MCP protocol transport belongs to a future milestone.
- **KnowledgeLayer uses simple substring search**: No vector embeddings or
  semantic search. Full-text indexing could be added if needed.
- **MemoryLayer uses heuristic scoring**: The relevance score formula
  (importance × 0.6 + recency × 0.4) is arbitrary. A future milestone could
  learn optimal weights from user feedback.
- **EvaluationEngine evaluators are user-provided**: No built-in LLM-as-judge
  or embedding-based similarity metrics yet.
- **ReflectionEngine strategies are rule-based**: No LLM-driven reflection yet.
- **WorkflowEngine checkpoints are in-memory**: No disk persistence for
  checkpoints. Long-running workflows cannot survive restarts.
- **Scheduler is single-process**: No distributed task queue (e.g., Celery,
  RQ). Acceptable for single-node deployments.

## Known Limitations

- `InMemoryRegistry` and `InMemoryContractRegistry` have no persistence.
- `ExecutionEngine` expects plugins to expose an `execute(input_data, config)`
  async method. This is a convention, not an enforced interface at the plugin
  system level (the kernel's `Agent` interface enforces it for kernel agents).
- `ConfigValidator` performs basic type checking. Full JSON Schema validation
  (e.g., with `jsonschema`) is not yet implemented.
- The `SchemaResolver` only loads schemas from a local directory. Remote schema
  resolution is not supported.
- `AgentRuntime` does not enforce global concurrency limits.
- `RuntimeMonitor` does not expose metrics via HTTP or push to external systems.
- All M4 subsystems are in-memory only and do not persist across restarts.
- The Workflow Engine does not yet support dynamic step insertion or
  self-modifying workflows.

## Risks After Milestone 4

1. **Path configuration**: If `PYTHONPATH` is misconfigured in production, the
   kernel will fail to import the plugin system and fall back to native agents
   silently.
2. **Plugin isolation**: Plugins run in the same process as the kernel. A
   misbehaving plugin can crash the entire system. Sandboxing is not yet
   implemented.
3. **No authentication on plugin management APIs**: If plugin management is
   exposed via HTTP, there is no access control yet.
4. **Memory growth**: `AgentRuntime`, `AgentMessenger`, `MemoryLayer`, and
   `KnowledgeLayer` accumulate data in memory indefinitely. Long-running
   processes may need periodic cleanup, session TTLs, or memory pruning.
5. **In-process scaling ceiling**: The Scheduler, Workflow Engine, and
   Observability layer are all single-process. Horizontal scaling would require
   significant redesign.
