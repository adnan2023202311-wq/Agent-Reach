# Agent Reach — Architecture (Foundation Milestone)

## Layout

```
domain/            no imports from anywhere else in the project.
  models.py          AgentType, TaskStatus, SubTask, TaskPlan, AgentResult,
                      TaskExecutionOutcome, RetryPolicy
  interfaces.py       Agent, Planner, ModelClient
  exceptions.py       AgentReachError and subclasses

core/              depends inward on domain/ only.
  planner.py          RuleBasedPlanner
  dispatcher.py       AgentDispatcher — retry/timeout/error-wrapping
  controller.py       MainController — the one orchestration use case

agents/            implements domain.interfaces.Agent.
  research_agent.py   real — calls ModelClient
  coding_agent.py     stub

infrastructure/    plain concrete classes, no interfaces (see below for why).
  memory_store.py     InMemoryStore
  tool_manager.py     ToolManager
  model_client.py     AnthropicModelClient (implements domain.interfaces.ModelClient)

config/            environment/config management.
  settings.py, logging_config.py

composition.py     the one place agents + core + config get wired together.

api/               HTTP interface. Only api/ and composition.py may import
                   a concrete Agent implementation.
  main.py, schemas.py, exception_handlers.py, dependencies.py
  routers/           chat.py, health.py, agents.py, tools.py, providers.py, dashboard.py

frontend/          production UI (TanStack Start, built in Lovable) — a
                   separate app/process, not served by the Python backend.
                   See frontend/README.md. Talks to api/ over HTTP.
```

**The rule that matters:** `domain/` imports nothing else in this project;
`core/` imports only `domain/`; nothing outside `composition.py` and `api/`
is allowed to import a concrete `Agent` implementation. That's the entire
enforcement mechanism — it's a naming/folder convention, not a framework.

## What's an interface here, and what deliberately isn't

Three interfaces exist: `Agent`, `Planner`, and `ModelClient`. Each was kept
for the same reason — a second, real, present-tense consumer already
exists or is imminent:

- `Agent` — `AgentDispatcher` already routes between two implementations
  (`ResearchAgent`, `CodingAgent`), with seven more planned per the
  Blueprint (Section 9). Removing this interface would mean
  `AgentDispatcher` matching on agent *names* internally — worse, not
  simpler.
- `Planner` — one implementation today (`RuleBasedPlanner`), but
  `MainController` already depends on the interface rather than the
  concrete class, and replacing it with an LLM-driven planner is a
  standing recommended milestone (see bottom of this document). Still
  the one interface here with a single implementation — flagged
  honestly as the closest call.
- `ModelClient` — one implementation (`AnthropicModelClient`), but the
  Blueprint (Section 19) explicitly plans multiple providers, and
  `ResearchAgent` already depends on the interface, not the concrete
  class (added in Milestone 3, put to real use in Milestone 5).

One interface was deliberately **not** added: `MemoryStore`. There's one
implementation (`infrastructure/memory_store.py`) and zero callers of it —
nothing in `MainController` uses memory yet. An interface with one
implementation and no consumer is speculation. `InMemoryStore` is a plain
class; the interface gets added back the moment a second implementation
(e.g. SQLite) needs to be swappable with it.

## Files that were removed for being wrappers, not layers

A first pass at this milestone introduced a few files that, on review,
didn't earn their place. Removed:

| File | Why it was cut |
|---|---|
| `api/dependencies.py` | One function, one line (`return request.app.state.controller`), one caller. Inlined into `api/routers/chat.py`. |
| `api/schemas.py`'s `AgentResultDTO` | A field-for-field copy of `domain.models.AgentResult`. Pydantic already serializes its enum fields to plain strings, so there was no format gap to bridge — `ChatResponse` now embeds `AgentResult` directly. |
| `domain/enums.py` (separate from `entities.py`) | Nothing ever imported one without the other. Merged into `domain/models.py`. |
| `infrastructure/memory/` and `infrastructure/tools/` (subpackages) | Each held exactly one file plus an `__init__.py`. Flattened to `infrastructure/memory_store.py` and `infrastructure/tool_manager.py`. |
| `composition/` (package) | Two functions don't need a package. Flattened to one file, `composition.py`. |

None of these were "wrong" in isolation — each one individually looked
like reasonable Clean Architecture. Collectively they added file-hopping
without adding safety. The test for keeping a file, applied here going
forward: *does this file do something a caller couldn't just do inline in
three lines, or does it have (or clearly will soon have) more than one
implementation/caller?*

## Milestone log

### Milestone 3 — ModelClient interface + AnthropicModelClient adapter

**What was built:** `domain.interfaces.ModelClient` (text-messages-in,
text-out contract) and `infrastructure/model_client.py`'s
`AnthropicModelClient`, the first concrete implementation. Plus
`domain.exceptions.ModelProviderError` (wraps any provider SDK failure,
mapped to HTTP 502 in `api/exception_handlers.py`) and
`composition.build_anthropic_model_client()`, a factory that is **not**
called by `build_default_controller()` yet.

**Why it was the highest priority:** every agent that graduates from
stub to real needs to call a model. An Execution Engine (an agentic
tool-use loop) needs this even more directly — it can't inspect
tool-use blocks or iterate on a response without first having a way to
call the model at all. Building the Execution Engine before this would
mean building this anyway, just embedded inside the loop instead of as
its own seam. This was a dependency-order decision, not a preference.

**What architectural problem it solves:** without this seam, the first
agent wired to a real provider would import `anthropic` directly,
handle its exception types itself, and read `ANTHROPIC_API_KEY` from
Settings itself. The next seven agents (Blueprint Section 9) would each
repeat that. `ModelClient` is the same fix `Agent` already was for
`AgentDispatcher` — one abstraction, applied where a second consumer is
already known to be coming.

**Trade-offs:**
- `ModelClient.complete()` is deliberately narrow (no tool-use, no
  streaming, no multi-turn history management). Real near-term needs
  (Execution Engine) will likely require widening it — accepted now
  rather than guessing at that shape early.
- `AnthropicModelClient` was written carefully but **not run against a
  live API** — this sandbox has no network access and no API key.
  Verified with `python -m py_compile` (syntax only) and unit tests
  that mock `messages.create` entirely (`tests/test_model_client.py`).
  Run `pytest` locally, then a real call, before trusting this against
  production traffic.
- `complete()` catches `Exception` broadly rather than specific
  `anthropic.*` exception classes. This is intentional (see
  `AgentDispatcher` for the same choice) but means a genuine bug inside
  this adapter would also get wrapped as `ModelProviderError` instead
  of surfacing as a stack trace — acceptable here because the method
  body is short enough to review directly.

**Remaining weaknesses:** everything listed below, plus: no agent
actually calls `AnthropicModelClient` yet (by design — see next
milestone); no token-usage/cost tracking; no streaming; no per-provider
timeout distinct from `RetryPolicy`'s (a slow model call and a broken
agent currently look the same to `AgentDispatcher`).

**Next milestone:** see below — wiring `ResearchAgent` to
`AnthropicModelClient` is what this milestone was built to unblock.

---

### Milestone 5 — First end-to-end vertical slice (User → API → Frontend)

**What was built:**
1. `ResearchAgent` now takes a `ModelClient` and calls it for real —
   no longer a stub.
2. `composition.build_default_agent_registry()` and
   `build_default_controller()` updated to construct and inject a real
   `AnthropicModelClient`. This means starting the app now requires
   `ANTHROPIC_API_KEY` (see Trade-offs).
3. Corrected `default_model` from a placeholder value
   (`claude-sonnet-4-6`, never actually called before this milestone)
   to the real current identifier (`claude-sonnet-5`).
4. `frontend/index.html` — a single static file, no build step, no
   framework, mounted at `/` by `api/main.py` via `StaticFiles`. It
   posts to the existing `/api/v1/chat` endpoint and renders both the
   answer and the actual per-subtask trace (`agent_type`, `status`,
   `attempts`, `duration_ms`) from `ChatResponse.results`.
5. `tests/test_composition.py` — proves the fail-fast behavior
   (missing key -> `ConfigurationError`) and successful wiring.

**Why this was the priority:** you asked for the product to actually
work end-to-end, not another architectural layer. Every piece needed
for that already existed from Milestones 1–4 except the one line
connecting `ResearchAgent` to the `ModelClient` it was built to use,
and a way for a human to reach the API without `curl`. No new
architecture was introduced — this milestone is entirely "turn what
exists on."

**What's still mocked / simulated:**
- The frontend's `Plan → Dispatch → Agent` stage highlighting is a
  fixed-timing UI approximation (`setTimeout`), not a live progress
  feed from the server — the API returns one response, it doesn't
  stream intermediate state. The final `Respond` stage and the trace
  table *are* real data from the actual response.
- `CodingAgent` is still a stub (out of scope — the requested pipeline
  was Research only).
- `ResearchAgent`'s answer is model-only, not a live web search (see
  its docstring) — accurate answers depend entirely on the model's own
  knowledge.
- Nothing here was run against a live network in this sandbox (no
  internet access). Verified via `python -m py_compile`, a real
  Node.js syntax check on the frontend's inline JS (`node --check`),
  and mocked unit tests. You'll need to run this with a real
  `ANTHROPIC_API_KEY` to confirm the live call actually succeeds.

**Remaining weaknesses:** everything already listed below, plus: no
loading/error states beyond what's in `index.html` (no retry button,
no request cancellation), no session continuity in the UI (each
request is independent — matches `InMemoryStore` not being wired in
yet), and the frontend has no build tooling by design, so it won't
scale past a page or two of UI before that becomes the right trade-off
to revisit.

**Next milestone:** see bottom of this document.

---

### Milestone 6 — Production frontend integration (Lovable)

**What was built:**

Backend:
1. Four new read-only endpoints: `GET /api/v1/agents`, `GET
   /api/v1/tools`, `GET /api/v1/providers`, `GET /api/v1/dashboard` —
   each reports real backend state (see "Design decisions" below for
   exactly how honest vs. how complete each one is).
2. `AgentDispatcher.registered_agent_types()` and
   `MainController.registered_agent_types()` — small additions so
   `api/routers/agents.py` can report which agents are *actually*
   registered instead of hardcoding the Blueprint's full roster.
3. `config.settings.KNOWN_PROVIDERS` and `Settings.is_provider_ready()`
   — so the providers endpoint and agents endpoint agree on what a
   "ready" provider means, in one place.
4. `api/dependencies.py` is back (see "Files that were removed for
   being wrappers" above) — `get_controller` now has three callers
   instead of one.
5. Reworked `api/exception_handlers.py` to emit `{message, code,
   details}` on every error path (domain errors, `HTTPException`,
   Pydantic validation errors) — this is the error shape the Lovable
   frontend's `src/lib/api/types.ts` already expected, written before
   this backend had any error handling to match it against.
6. `agents/research_agent.py`'s `SYSTEM_PROMPT` constant made public
   (was `_SYSTEM_PROMPT`) so `api/routers/agents.py` can report the
   real prompt instead of a second hardcoded copy.
7. Corrected `Settings.allowed_origins` defaults — CORS is now
   load-bearing since the frontend is a separate process on a
   different port, not something FastAPI serves itself.
8. Removed the `StaticFiles` mount and `frontend/index.html` from
   `api/main.py` — archived to `docs/archive/poc-frontend-milestone5.html`.

Frontend (`frontend/` — the unzipped Lovable project):
1. `src/services/http/index.ts` rewritten from stubs that threw
   `NotImplementedError` into real implementations calling the
   endpoints above, with a static icon/tint lookup merged onto
   backend data for the two presentation-only fields JSON can't carry
   (React component references, Tailwind classes).
2. **The more consequential fix**: several routes (`agents.tsx`,
   `tools.tsx`, `settings.providers.tsx`, `index.tsx`, `chat.tsx`,
   `hooks/use-topbar.ts`) read their initial data via a
   `const x = someService.xSync()` at module scope. That pattern works
   for the mock service (a static array, available instantly) but
   cannot work for real data in this app, for a reason specific to it
   being a TanStack Start (SSR) app: module-level code runs once when
   the server bundle boots, not per request, so there is no request
   context and no way for a synchronous accessor to have fetched
   anything yet. This isn't a style preference — it would 500 on
   server boot the moment `VITE_API_MODE=http` was set. Fixed by
   moving each of those into a `useQuery` call inside the component
   (TanStack Query was already configured in `router.tsx`; nothing new
   to wire up). This is exactly what this codebase's own comments
   already said should happen ("routes migrate to the async methods
   via TanStack Query") — Lovable scaffolded the seam and named the
   fix; this milestone is the fix actually landing.
3. `chat.tsx`: `sendMessage` was entirely local — a `buildMockReply()`
   function fabricated a response synchronously and the `ChatService`
   was never called at all. Rewired to call `chatService.sendMessage()`
   for real, made async, and added a typing indicator (`isSending`
   state) — the old code had no loading state because it never needed
   one. `buildMockReply` deleted.
4. `frontend/.env.example`, `frontend/README.md` — how to point the
   app at the real backend.
5. Root `.gitignore` added (there wasn't one) — the project now has a
   real `.env` with a real API key for the first time; `frontend/.env`
   is covered too.

**Why this was the priority:** you asked for the existing production
frontend connected to the existing backend, explicitly not a redesign.
Everything above is either wiring (wrong data source → right data
source) or fixing what was blocking the wiring from working at all
(the SSR module-scope problem, the error-shape mismatch) — no new
product surface was added.

**Design decisions — how much of "replace all mock data" this actually does:**

Inspecting the routes that consume the mock services first (before
writing any backend code) changed the scope in three ways:

- **Agents/Tools/Providers "Configure" panels never called `.update()`
  even in mock mode** — they mutate local component state only
  (confirmed by reading the code, not assumed). So `.update()` stays
  unimplemented (`501`) on the backend and unwired on the frontend for
  all three resources: building real persistence for a code path
  nothing calls would be exactly the over-engineering you asked me to
  avoid. If real editing is wanted later, this is the seam to build it
  on — not fake it now.
- **Tools are honestly empty.** `infrastructure/tool_manager.py` has
  no registered tools (see Milestone 3/4 notes) — `GET /api/v1/tools`
  reports that directly rather than constructing an unused
  `ToolManager` instance just to call an always-empty method on it.
- **Dashboard's activity stats and recent chats are honestly empty.**
  No usage metrics or conversation history are persisted anywhere.
  Real zeros, not fabricated numbers — and not a reason to build a
  metrics/persistence system this milestone didn't ask for.
- **Static catalog data stayed static.** Provider names, model lists,
  docs links, and agent/tool icons are reference data, not per-user
  state — they're merged client-side onto live `status`/`enabled`
  fields from the backend rather than duplicated into a Python
  catalog. `apiKey` is never populated from the backend at all, even
  masked — see api/schemas.py's `ProviderSummary` docstring.

**What's still mocked / not wired:**

- `agentsHttpService.update`, `toolsHttpService.update`,
  `providersHttpService.update` — all throw clearly; see above.
- Several `*Sync` methods in `http/index.ts` also throw — they're
  retained only so the `Services` TypeScript interface (shared with
  the mock implementation) type-checks; nothing calls them after the
  `useQuery` refactor. See that file's top-of-file design note.
- Chat's provider/model/agent selectors are sent to the backend inside
  `ChatRequest.context` but **do not change backend routing** —
  `MainController.handle_request(message: str)` only ever sees the
  plain text; `RuleBasedPlanner` still routes by keyword regardless of
  what's selected in the UI. This is the single most likely thing to
  look like a bug that isn't one — flagged here, in the frontend
  README, and in the root README.
- Nothing in this milestone was run against a live `bun run dev` +
  live backend pair — no network access in this sandbox, and no
  `node_modules` installed (no way to `bun install`). Every backend
  file was verified with `python -m py_compile`; every changed
  frontend file was checked with `tsc --noEmit` using manually-supplied
  compiler flags (real type errors were caught and fixed this way —
  see the duplicate-import and provider-type-inference fixes made
  during this milestone). What `tsc` could not check without installed
  dependencies: whether `bun install` succeeds cleanly, the actual dev
  server port, and whether the real Anthropic call behaves as expected
  under real latency. Run `bun install && bun run dev` locally as the
  first real test.

**Remaining limitations:**
- No auth/rate limiting — unchanged from Milestone 5's recommendation,
  now more urgent: a full production UI is live pointing at a real
  provider key.
- No agent-selection routing (above).
- No persistence for Configure panels, tools, or conversation history.
- CORS origins are a best guess (`:3000`, `:5173`) — confirm against
  whatever `bun run dev` actually prints.

**Next milestone:** see bottom of this document.

---

## What's real vs. stubbed

| Component | Status |
|---|---|
| `domain/models.py`, `interfaces.py`, `exceptions.py` | Real, stable contracts |
| `MainController` orchestration loop | Real |
| `AgentDispatcher`: retry, timeout, error-wrapping | Real, unit-tested in isolation (`tests/test_dispatcher.py`) |
| `RuleBasedPlanner` | Real but simplistic (keyword match, always 1 subtask, ignores UI's agent/provider/model selection) |
| `ResearchAgent` | Real — calls `AnthropicModelClient` for actual answers |
| `CodingAgent` | Still a stub |
| `AnthropicModelClient` | Real adapter, unit-tested with mocks |
| `InMemoryStore` | Real, but not called by anything yet |
| `ToolManager` | Real registration/permission/audit mechanism, zero tools registered |
| `GET /api/v1/agents`, `/tools`, `/providers`, `/dashboard` | Real reads of actual backend state (see Milestone 6) |
| `PATCH` on agents/tools/providers | Not implemented (`501`) — nothing calls them, no persistence exists |
| Production frontend (`frontend/`) | Real, connected — see Milestone 6 for exactly which pages use real vs. locally-mutated data |
| Milestone 5's `frontend/index.html` | Archived, no longer served — `docs/archive/poc-frontend-milestone5.html` |
| API error handling | Real — every error path (domain, HTTP, validation) emits one consistent JSON shape |

## Remaining weaknesses

1. **Planning is single-subtask only, and ignores the frontend's
   agent/provider/model selectors.** No multi-agent chains yet
   (Blueprint Section 22's News → Research → Writing → Image example
   needs this), and `RuleBasedPlanner` routes purely by keyword
   regardless of what's picked in the Chat UI.
2. **`SubTask.depends_on` is defined but not honored** — `MainController`
   runs subtasks strictly in list order.
3. **`InMemoryStore` isn't wired into `MainController`** — no conversation
   history affects planning or dispatch; the Dashboard's activity/recent
   chats are honestly empty as a result.
4. **`CodingAgent` is still a stub.**
5. **`ToolManager` has no registered tools.**
6. **No authentication or rate limiting on the API** — now the most
   urgent item, since a full production frontend is live pointing real
   traffic at a real provider key.
7. **No persistence for agent/tool/provider configuration** — the
   frontend's "Configure" panels edit local browser state only, in
   both mock and http mode.
8. **`pyproject.toml` configures `mypy`/`ruff` but nothing runs them
   automatically** — no CI, no pre-commit hook. The frontend has no
   equivalent CI wiring either.
9. **Nothing in this project has been run end-to-end in this sandbox** —
   no network access to install Python packages or run `bun install`.
   Backend verified via `python -m py_compile`; frontend verified via
   manually-invoked `tsc --noEmit` (real errors were caught and fixed
   this way, so it's more than a formality, but it isn't a substitute
   for actually running `pytest` and `bun run dev`).

## Recommended next milestone

**Basic authentication + rate limiting on `/api/v1/chat`.** This
recommendation hasn't changed since Milestone 5, but the case for it is
stronger now: a real, production-quality frontend is connected and live
traffic through it spends a real Anthropic budget with zero access
control. Right now, anyone who can reach the API — no login, no key, no
limit — can run that budget up.

Concretely: an API-key-per-client check (even a single shared secret
compared via `secrets.compare_digest`, checked in a small FastAPI
dependency) plus a basic per-client rate limit. Both are small, bounded
pieces of work — this is explicitly not a recommendation to build a
full auth/identity system.

Two reasonable alternatives:
1. Wire agent/provider/model selection from the Chat UI into real
   backend routing — closes the most likely-to-confuse gap (Milestone
   6, "Remaining limitations") but is a feature, not a risk reduction.
2. Wire `InMemoryStore` into `MainController` for session continuity —
   also improves the product without reducing risk.

## Running locally

Backend:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # set ANTHROPIC_API_KEY
pytest                        # should pass with zero API keys set
uvicorn api.main:app --reload
```

Frontend (separate terminal — see frontend/README.md for the full picture):

```bash
cd frontend
bun install
cp .env.example .env
bun run dev
```

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "ابحث عن أحدث تطورات نماذج اللغة"}'
```
