"""
API layer: /api/v1/runtime/extensions — Runtime Extensions (M10.34).

Streaming responses and event sourcing. Enables real-time streaming
of model responses and persistent event logs for replay/debugging.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/runtime/extensions", tags=["runtime-extensions"])


class StreamEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stream_id: str
    event_type: str = "token"  # token | chunk | done | error
    content: str = ""
    sequence: int = 0
    timestamp: float = Field(default_factory=time.time)


class EventLog(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str  # session | agent | workflow | request
    entity_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


_active_streams: dict[str, list[StreamEvent]] = {}
_event_logs: dict[str, EventLog] = {}


class StartStreamRequest(BaseModel):
    message: str
    provider_id: Optional[str] = None
    model_id: Optional[str] = None


@router.post("/stream/start")
async def start_stream(request: StartStreamRequest) -> dict[str, Any]:
    """Start a streaming response session."""
    stream_id = str(uuid.uuid4())
    _active_streams[stream_id] = []
    return {"stream_id": stream_id, "status": "started"}


@router.get("/stream/{stream_id}")
async def stream_response(stream_id: str) -> StreamingResponse:
    """Stream a response (simulated token-by-token for demo)."""
    if stream_id not in _active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")

    async def generate():
        tokens = ["Hello", "!", " ", "This", " ", "is", " ", "a", " ", "streamed", " ", "response", "."]
        for i, token in enumerate(tokens):
            event = StreamEvent(
                stream_id=stream_id, event_type="token", content=token, sequence=i,
            )
            _active_streams[stream_id].append(event)
            yield f"data: {event.model_dump_json()}\n\n"
            await asyncio.sleep(0.05)
        done_event = StreamEvent(stream_id=stream_id, event_type="done", content="", sequence=len(tokens))
        _active_streams[stream_id].append(done_event)
        yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/stream/{stream_id}/events")
async def get_stream_events(stream_id: str) -> dict[str, Any]:
    """Get all events from a completed stream."""
    if stream_id not in _active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")
    events = _active_streams[stream_id]
    return {"stream_id": stream_id, "events": [e.model_dump() for e in events], "count": len(events)}


class RecordEventRequest(BaseModel):
    entity_type: str
    entity_id: str
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


@router.post("/events/record")
async def record_event(request: RecordEventRequest) -> dict[str, Any]:
    """Record an event in the event log (event sourcing)."""
    log_key = f"{request.entity_type}:{request.entity_id}"
    log = _event_logs.get(log_key)
    if log is None:
        log = EventLog(entity_type=request.entity_type, entity_id=request.entity_id)
        _event_logs[log_key] = log
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": request.event_type,
        "data": request.data,
        "timestamp": time.time(),
    }
    log.events.append(event)
    return {"event_id": event["event_id"], "log_key": log_key, "status": "recorded"}


@router.get("/events/{entity_type}/{entity_id}")
async def get_event_log(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Get the event log for an entity (event sourcing replay)."""
    log_key = f"{entity_type}:{entity_id}"
    log = _event_logs.get(log_key)
    if log is None:
        return {"entity_type": entity_type, "entity_id": entity_id, "events": [], "count": 0}
    return log.model_dump()


@router.post("/events/{entity_type}/{entity_id}/replay")
async def replay_events(entity_type: str, entity_id: str, from_timestamp: float = 0) -> dict[str, Any]:
    """Replay events from a given timestamp (event sourcing replay)."""
    log_key = f"{entity_type}:{entity_id}"
    log = _event_logs.get(log_key)
    if log is None:
        return {"events": [], "count": 0}
    events = [e for e in log.events if e["timestamp"] >= from_timestamp]
    return {"replayed_events": events, "count": len(events), "from_timestamp": from_timestamp}


@router.get("/events/stats")
async def event_stats() -> dict[str, Any]:
    total_logs = len(_event_logs)
    total_events = sum(len(log.events) for log in _event_logs.values())
    active_streams = len(_active_streams)
    return {
        "total_logs": total_logs,
        "total_events": total_events,
        "active_streams": active_streams,
    }
