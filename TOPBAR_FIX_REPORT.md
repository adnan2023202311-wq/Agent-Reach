# Google↔Gemini Alias + Clean Response — Fix (v2.8)

## v2.7: Store path anchored to module location
Fixed `ProviderConfigStore` path using `Path(__file__)` instead of
`Path.cwd()` so keys are found from any working directory.

## v2.8: Two fixes

### Fix 1: Google↔Gemini provider name alias

#### Symptom
After v2.7, `Settings.provider_api_key("google")` returned True, but
`Settings.provider_api_key("gemini")` returned False. Chat with
`provider_id=google` failed with "Gemini provider requires an API key".

#### Root Cause
The API/config layer uses "google" (KNOWN_PROVIDERS, `google_api_key`
field, `/api/v1/providers?id=google`). The runtime ProviderManager uses
"gemini" (SUPPORTED_PROVIDERS). When the user saves Google's key via
the UI, it's stored under `"google"` in `provider_config.json`.

The override logic maps `"google"` → `"gemini"` via
`_to_runtime_provider_name()`. So `set_provider("gemini")` is called.
But when `ProviderManager._get_or_create_client("gemini")` looks up the
key, it checks `self._provider_keys.get("gemini")` (None at construction)
then `store.get_api_key("gemini")` — which returns None because the key
is stored under `"google"`, not `"gemini"`.

#### Fix
Added a `_PROVIDER_ALIASES` map in both `Settings` and `ProviderManager`:
```python
_PROVIDER_ALIASES = {"google": "gemini", "gemini": "google"}
```

`Settings.provider_api_key(provider)` now checks both the requested name
and its alias. `ProviderManager._get_or_create_client(provider)` does
the same when reading from the store. So a key stored under "google" is
found when the runtime asks for "gemini".

### Fix 2: Raw agent payloads leaking into chat

#### Symptom
The assistant message contained:
```
[coding] {"instruction": "...", "code": null, "error": "...", "source": "model_error"}
```
instead of a clean conversational response.

#### Root Cause
`MainController._assemble_answer()` did:
```python
f"[{r.agent_type.value}] {r.output}"
```
This stringified the entire agent output dict. `CodingAgent.execute()`
returns `{"instruction": ..., "code": ..., "source": ...}` — a structured
dict that's meaningful internally but shouldn't be shown to the user.

#### Fix
`_assemble_answer()` now extracts clean text from agent outputs:
- Dicts: looks for `"answer"`, `"code"`, `"content"`, `"text"`, `"output"`,
  `"result"` keys (in that order) and uses the first string value found
- Strings: used as-is
- Failed agents: concise `(failed: ...)` line with truncated error
- Single successful result: returned directly (no `[agent_type]` prefix)
- Multiple results: each prefixed with `[agent_type]` for context

### Verification

```
=== Settings sees keys (including gemini alias) ===
  google: True
  gemini: True          ← was False before v2.8
  openrouter: True

=== Chat with provider_id=google ===
  Backend log: "picked up key for gemini from config store (stored as google)"
  answer: "Model provider 'gemini' call failed: Error code: 400"
  ← NOT "Gemini provider requires an API key" — the provider IS called now
  ← 400 = fake key rejected by Google's API (expected)

=== Chat with provider_id=openrouter ===
  answer: "[research] (failed: ... 401 ...)"
  ← Clean error format, NOT raw dict
```

### Build Stamp
The topbar shows `TOPBAR-FIX-v2.8`.

## Files Changed (v2.8)

- `backend/agent reach core/agent_reach/config/settings.py`
  — added `_PROVIDER_ALIASES`; `provider_api_key()` checks alias.
- `backend/agent reach core/agent_reach/infrastructure/provider_manager.py`
  — added `_PROVIDER_ALIASES`; `_get_or_create_client()` checks alias
    when reading from the store.
- `backend/agent reach core/agent_reach/core/controller.py`
  — `_assemble_answer()` extracts clean text from agent output dicts.
- `frontend/Agent Canvas/src/components/layout/topbar.tsx`
  — bumped build stamp to `TOPBAR-FIX-v2.8`.
