"""
Infrastructure layer: Production tool implementations (M9.6).

Layer: Adapters.

Real, executable tools registered into the existing ToolRegistry
(infrastructure/tool_registry.py). This finally populates the
mechanism ToolManager built in Milestone 3 — the "populate with real
tools" TODO — without introducing any parallel tool system.

Tools
-----
- http_request : real HTTP calls via httpx (already a core dependency)
- rss_fetch    : fetch + parse RSS/Atom feeds (stdlib XML parsing)
- browser_fetch: fetch a page and extract title/text/links.
                 This is an HTTP-level browser (no JavaScript
                 execution) — full Playwright automation remains a
                 plugin concern (browser/PLACEHOLDER.md).
- fs_read / fs_write / fs_list : sandboxed filesystem access rooted
                 at a configurable workspace directory. Path escapes
                 are rejected.
- telegram_send: real Telegram Bot API call. Requires a bot token —
                 raises ConfigurationError when unconfigured instead
                 of pretending to send.

Security notes
--------------
- Filesystem tools resolve paths and verify containment within the
  sandbox root before touching the disk (Blueprint Section 23).
- telegram tokens come from the environment (TELEGRAM_BOT_TOKEN), not
  from request payloads, so they are never echoed through the API.
"""

from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

import httpx

from domain.exceptions import ConfigurationError

_DEFAULT_TIMEOUT = 30.0
_MAX_RESPONSE_CHARS = 200_000


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make a real HTTP request and return status, headers, and body."""
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValueError(f"Unsupported HTTP method: {method}")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
        )

    body = response.text[:_MAX_RESPONSE_CHARS]
    return {
        "status_code": response.status_code,
        "ok": response.is_success,
        "headers": dict(response.headers),
        "body": body,
        "url": str(response.url),
        "elapsed_ms": response.elapsed.total_seconds() * 1000,
    }


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------


def _text(element: Optional[ET.Element]) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_rss(root: ET.Element, max_items: int) -> list[dict[str, str]]:
    items = []
    for item in root.iter("item"):
        items.append(
            {
                "title": _text(item.find("title")),
                "link": _text(item.find("link")),
                "description": _text(item.find("description")),
                "published": _text(item.find("pubDate")),
            }
        )
        if len(items) >= max_items:
            break
    return items


def _parse_atom(root: ET.Element, max_items: int) -> list[dict[str, str]]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        link_el = entry.find("atom:link", ns)
        items.append(
            {
                "title": _text(entry.find("atom:title", ns)),
                "link": link_el.get("href", "") if link_el is not None else "",
                "description": _text(entry.find("atom:summary", ns)),
                "published": _text(entry.find("atom:updated", ns)),
            }
        )
        if len(items) >= max_items:
            break
    return items


async def rss_fetch(
    url: str,
    max_items: int = 20,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch and parse an RSS 2.0 or Atom feed."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    tag = root.tag.lower()
    if tag.endswith("feed"):  # Atom
        items = _parse_atom(root, max_items)
        feed_title = _text(root.find("{http://www.w3.org/2005/Atom}title"))
    else:  # RSS 2.0 — <rss><channel>…
        channel = root.find("channel")
        feed_title = _text(channel.find("title")) if channel is not None else ""
        items = _parse_rss(root, max_items)

    return {"url": url, "title": feed_title, "items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Browser (HTTP-level)
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"'#][^\"']*)[\"']", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


async def browser_fetch(
    url: str,
    max_text_chars: int = 20_000,
    max_links: int = 50,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch a web page and extract title, readable text, and links.

    HTTP-level browsing: no JavaScript execution. Pages requiring JS
    rendering need the Playwright browser plugin.
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)

    raw = response.text
    title_match = _TITLE_RE.search(raw)
    title = html.unescape(title_match.group(1).strip()) if title_match else ""

    cleaned = _SCRIPT_STYLE_RE.sub(" ", raw)
    text = html.unescape(_TAG_RE.sub(" ", cleaned))
    text = _WHITESPACE_RE.sub(" ", text).strip()[:max_text_chars]

    links = [html.unescape(m) for m in _LINK_RE.findall(raw)][:max_links]

    return {
        "url": str(response.url),
        "status_code": response.status_code,
        "title": title,
        "text": text,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Filesystem (sandboxed)
# ---------------------------------------------------------------------------


class FilesystemSandbox:
    """Sandboxed file operations rooted at a workspace directory.

    Every path is resolved and verified to remain inside the root —
    ``../`` escapes and absolute paths outside the root are rejected
    with PermissionError.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self._root / relative_path).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise PermissionError(
                f"Path '{relative_path}' escapes the workspace sandbox"
            )
        return candidate

    async def read(self, path: str, max_chars: int = 100_000) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"No such file in workspace: {path}")
        content = target.read_text(encoding="utf-8", errors="replace")[:max_chars]
        return {"path": path, "content": content, "size": target.stat().st_size}

    async def write(self, path: str, content: str, append: bool = False) -> dict[str, Any]:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as fh:
            fh.write(content)
        return {"path": path, "bytes_written": len(content.encode("utf-8")), "appended": append}

    async def list_dir(self, path: str = ".") -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_dir():
            raise NotADirectoryError(f"No such directory in workspace: {path}")
        entries = []
        for child in sorted(target.iterdir()):
            entries.append(
                {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"path": path, "entries": entries, "count": len(entries)}


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


async def telegram_send(
    chat_id: str,
    text: str,
    bot_token: Optional[str] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send a message through the real Telegram Bot API.

    The token comes from the TELEGRAM_BOT_TOKEN environment variable
    unless explicitly injected (tests). Unconfigured => hard error,
    not a silent no-op.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ConfigurationError(
            "Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN."
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    payload = response.json()
    return {
        "ok": bool(payload.get("ok")),
        "status_code": response.status_code,
        "result": payload.get("result"),
        "description": payload.get("description"),
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_production_tools(
    registry: Any,
    *,
    workspace_root: str | Path = "./data/tool_workspace",
) -> Any:
    """Register every production tool into an existing ToolRegistry.

    Reuses the registry's metadata/permission/enable-disable surface —
    no parallel implementation. Returns the registry for chaining.
    """
    sandbox = FilesystemSandbox(workspace_root)

    registry.register(
        "http_request",
        http_request,
        description="Make authenticated HTTP calls to any REST endpoint.",
        version="1.0.0",
        category="integration",
        tags=["http", "rest", "api"],
    )
    registry.register(
        "rss_fetch",
        rss_fetch,
        description="Fetch and parse RSS 2.0 / Atom feeds.",
        version="1.0.0",
        category="data",
        tags=["rss", "atom", "feeds"],
    )
    registry.register(
        "browser_fetch",
        browser_fetch,
        description=(
            "Fetch a web page and extract title, readable text, and links "
            "(HTTP-level; no JavaScript execution)."
        ),
        version="1.0.0",
        category="web",
        tags=["browser", "web", "scraping"],
    )
    registry.register(
        "fs_read",
        sandbox.read,
        description="Read a file inside the workspace sandbox.",
        version="1.0.0",
        category="system",
        tags=["filesystem", "read"],
    )
    registry.register(
        "fs_write",
        sandbox.write,
        description="Write or append to a file inside the workspace sandbox.",
        version="1.0.0",
        category="system",
        tags=["filesystem", "write"],
    )
    registry.register(
        "fs_list",
        sandbox.list_dir,
        description="List a directory inside the workspace sandbox.",
        version="1.0.0",
        category="system",
        tags=["filesystem", "list"],
    )
    registry.register(
        "telegram_send",
        telegram_send,
        description="Send a message via the Telegram Bot API (requires TELEGRAM_BOT_TOKEN).",
        version="1.0.0",
        category="messaging",
        tags=["telegram", "messaging"],
        enabled=bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
    )
    return registry
