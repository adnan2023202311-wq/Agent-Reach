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

### Milestone 5 (Complete)
- **M5 WorkflowEngine is sequential**: The M5 spec calls for sequential
  step execution; the engine does NOT run independent steps in
  parallel the way M4\'s capability-driven DAG WorkflowEngine
  does. Independent branches in an M5 workflow still execute in
  declared order. Parallel branches belong to a future milestone
  (M5 deliberately reuses M4 for that use case).
- **WorkflowMonitor is in-memory only**: Like the M4 metrics layer,
  workflow statistics are not persisted to disk or pushed to an
  external system. Cross-process aggregation belongs to a future
  milestone.
- **WorkflowPersistence is JSON-only**: Per the M5 specification,
  no database. JSON is fine for a handful of workflows but does
  not scale; a database-backed persistence layer belongs to a
  future milestone.
- **Template resolver is intentionally narrow**: Custom template
  resolver (no Jinja2) supports only `variables.x` and
  `outputs.step_id.key` paths. No loops, no conditionals, no
  arithmetic, no function calls. This is by design — workflow
  inputs should not host arbitrary code execution.
- **Conditions use structured operators only**: A Condition is a
  (variable, op, value) triple. No `and`/`or` composition; nested
  expressions belong to a future milestone.
- **`StepExecutionRecord.attempts` is the engine-level retry
  count, not the total underlying invocations**: Per the M5
  spec v1.1 amendment (Semantic Definitions —
  StepExecutionRecord.attempts), the field records the number
  of times the WorkflowEngine invoked the step. Inner
  orchestrator retries (e.g., AgentDispatcher\'s per-call retry
  policy) are an implementation detail of that orchestrator and
  are not reflected in the workflow-level audit. Callers that
  need the inner-retry count can use the underlying
  `OrchestrationResult.attempts` / `AgentResult.attempts`
  directly. The composition is therefore: a step with
  `max_attempts=2` (engine) and a dispatcher with
  `max_attempts=3` produces up to 2 (not 6) recorded attempts.
  The multiplicative behavior is documented here so a future
  maintainer does not interpret the small audit count as "the
  retry policy was ineffective" when in fact the inner
  orchestrator did the retries internally.
- **WorkflowValidator inspects `ToolManager._tools` directly**:
  the registry-aware tool check reaches into the private
  `_tools` dict of ToolManager because ToolManager has no public
  list_registered() accessor yet. A public accessor would be a
  one-line M5.5 follow-up; the dependency is documented here so
  it does not surprise future maintainers.
- **WorkflowEngine retries inside the dispatcher**: when the
  orchestrator (AgentOrchestrator) already has internal retries
  via AgentDispatcher, the engine\'s outer retry loop and the
  dispatcher\'s inner retry loop compose multiplicatively. A
  step configured with `max_attempts=2` and a dispatcher with
  `max_attempts=3` results in up to 6 underlying invocations.
  This is correct (the policy of each layer is honored) but is
  not obvious from the workflow definition; future work could
  expose the effective per-step attempt budget up front.
- **Synchronous execution via `asyncio.run`**: `run_sync()` uses
  `asyncio.run()` per call, which creates a fresh event loop.
  Calling it from inside an already-running event loop will
  raise. The async `run()` API is the one to use in async code.

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

## Risks After Milestone 5

6. **M5 and M4 workflow engines coexist**: There are now TWO workflow
   engines in the codebase:
   - M4\'s `workflow/engine.py` — capability-driven DAG, integrates
     with evaluation/reflection/observability.
   - M5\'s `workflows/engine.py` — agent/tool-driven, sequential,
     named workflows with persistence and validation.
   Callers must pick the one that fits their use case. A future
   milestone could unify them or make the choice explicit via a
   single orchestrator.
7. **Workflow authoring surface**: workflows are constructed
   programmatically today. A DSL or YAML authoring layer would
   make workflows easier to write by hand, but is out of scope
   for M5.
8. **No cross-workflow transactions**: a workflow that mutates
   shared state (memory, knowledge) does not have rollback
   semantics. Failed mid-workflow, side effects persist.
9. **WorkflowRegistry is process-local**: there is no inter-process
   discovery or replication. A workflow registered in process A
   is invisible to process B.

### Milestone 6 (Complete)

- **ConversationEngine history is in-memory only**: Conversation
  history and context are stored in-memory keyed by session_id. A
  future milestone could persist history to SQLite or a database.
- **SessionManager uses InMemorySessionStore by default**: Sessions
  are not persisted across restarts. A `JsonSessionStore` or
  SQLite-backed store could be added for persistence.
- **ProviderManager2.0 clients are cached indefinitely**: Once a
  provider client is created, it is never refreshed. If credentials
  change, the process must be restarted. A future milestone could
  add client invalidation.
- **ProviderManager2.0 uses lazy SDK imports**: Each provider's SDK
  is imported on first use. This means import errors only surface
  when a provider is first activated, not at startup. A future
  milestone could validate SDK availability at startup.
- **ToolRegistry2.0 rebuilds the underlying ToolManager on
  unregister**: Since `ToolManager` has no `unregister` method,
  `ToolRegistry2.0` rebuilds the entire manager when a tool is
  removed. This is O(n) in the number of tools. Acceptable for
  small registries; a future milestone could add unregister to
  ToolManager.
- **AgentRegistry2.0 dependencies are validated but not enforced**:
  `validate_dependencies()` returns missing dependencies, but
  registration does not block on validation failures. A future
  milestone could make validation mandatory.
- **PromptLibrary uses simple regex-based substitution**: The
  `{{ variable }}` syntax does not support nested paths, defaults,
  or escaping. A future milestone could adopt Jinja2 or a more
  expressive template engine.
- **VisualWorkflowAPI loses information in graph conversion**:
  Converting a Workflow to a graph and back loses conditions,
  retry policies, and timeouts. The graph is a structural view,
  not a full representation.
- **PluginMarketplace is local-only**: The marketplace manages a
  local registry of plugin metadata. There is no external
  marketplace integration, no download/install from URLs, and no
  signature verification.
- **Production API has no rate limiting**: The FastAPI endpoints
  have no rate limiting or request throttling. A future milestone
  could add middleware for rate limiting.
- **Authentication uses in-memory UserStore**: Users and API keys
  are stored in-memory and lost on restart. A future milestone
  could add database-backed user storage.
- **JWT secret key comes from configuration**: The JWT secret is
  read from settings. If not configured, it should default to a
  secure random value (currently it must be explicitly set).
- **ConfigurationManager replaces the cached Settings instance**:
  `apply_profile()` and `reload()` clear the lru_cache and rebuild
  the Settings. Existing references to the old Settings object
  become stale. Callers must re-call `get_settings()` to see
  updates.
- **BenchmarkSuite memory measurement is platform-dependent**:
  `tracemalloc` is used when available, but memory stats may not
  be available in all environments. Results should be compared
  within the same environment only.
- **SDK remote mode has no retry logic**: The SDK's remote mode
  does not retry failed requests. A future milestone could add
  exponential backoff for transient failures.
- **SDK in-process mode creates a new controller per instance**:
  Each `AgentReach()` instance builds its own controller and
  conversation engine. For multiple instances, this duplicates
  setup. A future milestone could add a shared app context.
