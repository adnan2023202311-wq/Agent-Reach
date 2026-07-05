# Agent Reach

A real, end-to-end path through the orchestration pipeline described in
`Agent_Reach_Official_Blueprint_v1.docx`: a person opens the production
UI, types a question, it's planned into a subtask, dispatched to the
Research Agent, answered by Claude, and shown back to them.

## What this is

- A real FastAPI backend: plan → dispatch → retry → respond, plus
  read endpoints for agents, tools, providers, and a dashboard summary.
- `ResearchAgent` is real — it calls Claude via `AnthropicModelClient`
  for actual answers. `CodingAgent` is still a stub.
- The **production frontend** (`frontend/`) — a TanStack Start app
  built in Lovable, connected to the real backend. It's a separate
  process with its own dev server; see `frontend/README.md`. Milestone
  5's single-file proof of concept is archived at
  `docs/archive/poc-frontend-milestone5.html`.
- A test suite that passes with **zero API keys** (it uses fakes, never
  the real composition wiring) — but **running the app for real
  requires `ANTHROPIC_API_KEY`**, since `ResearchAgent` needs a working
  `ModelClient` to be constructed at all. Intentional fail-fast
  behavior — see `docs/ARCHITECTURE.md`, Milestone 5.

## What this is NOT (yet)

- No authentication or rate limiting on the API — see
  `docs/ARCHITECTURE.md` for why this is the recommended next milestone,
  now more urgent with a real frontend pointed at a real provider key.
- No live web search (`ResearchAgent`'s answers come from the model's
  own knowledge, not a search backend).
- No persistent memory (in-memory only, and not even wired in yet) —
  the Dashboard's activity/recent-chats sections are honestly empty.
- Agent/provider/model selection in the Chat UI doesn't yet change
  which backend agent handles a request — the planner still routes by
  keyword regardless of what's selected. See `docs/ARCHITECTURE.md`,
  Milestone 6, "Remaining limitations".
- No persistence for the Agents/Tools/Providers "Configure" panels —
  edits are local to the browser session (true in mock mode too).

## Quickstart

Backend:

```bash
pip install -r requirements-dev.txt
pytest                               # passes with 0 API keys set

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-... — the app will refuse
# to start without it (see ConfigurationError in composition.py)

uvicorn api.main:app --reload        # http://localhost:8000
```

Frontend (separate terminal):

```bash
cd frontend
bun install
cp .env.example .env                 # defaults to VITE_API_MODE=http
bun run dev                          # prints its own URL, e.g. :3000
```

If the frontend's printed URL isn't already in the backend's
`ALLOWED_ORIGINS` (`.env`, defaults cover `:3000` and `:5173`), add it
and restart the backend — CORS will otherwise reject every request.

## Folder structure

```
domain/          data types, interfaces, exceptions — no dependencies
core/            planner, dispatcher, controller — depends on domain/ only
agents/          concrete agents implementing domain.interfaces.Agent
infrastructure/  memory store, tool manager, Anthropic ModelClient adapter
config/          settings + logging setup
composition.py   wires concrete agents/model client into what core/ needs
api/             FastAPI app, routes, dependencies, request/response schemas
frontend/        production UI (TanStack Start) — separate app, own README
docs/            architecture log, archive of the Milestone 5 POC frontend
tests/           pytest suite, using fake agents for isolation
```

See `docs/ARCHITECTURE.md` for the dependency rule, the full milestone
log, what's real vs. stubbed, and the recommended next milestone.
