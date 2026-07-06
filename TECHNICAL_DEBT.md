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

## Known Limitations

- `InMemoryRegistry` and `InMemoryContractRegistry` have no persistence.
- `ExecutionEngine` expects plugins to expose an `execute(input_data, config)`
  async method. This is a convention, not an enforced interface at the plugin
  system level (the kernel's `Agent` interface enforces it for kernel agents).
- `ConfigValidator` performs basic type checking. Full JSON Schema validation
  (e.g., with `jsonschema`) is not yet implemented.
- The `SchemaResolver` only loads schemas from a local directory. Remote schema
  resolution is not supported.

## Risks Before Milestone 3

1. **Path configuration**: If `PYTHONPATH` is misconfigured in production, the
   kernel will fail to import the plugin system and fall back to native agents
   silently (which is the safe fallback, but plugin capabilities will be unavailable).
2. **Plugin isolation**: Plugins run in the same process as the kernel. A
   misbehaving plugin can crash the entire system. Sandboxing (per the charter's
   `enable_sandboxed_execution` setting) is not yet implemented.
3. **No authentication on plugin management APIs**: If plugin management is
   exposed via HTTP, there is no access control yet.
