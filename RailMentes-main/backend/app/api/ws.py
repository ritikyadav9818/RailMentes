"""WebSocket /ws/state: pushes a StateSnapshot on connect and after every tick.

Messages are envelopes ``{"type", "seq", "data"}`` (see docs/API.md). The server only sends;
anything a client writes is read and ignored so that a disconnect is noticed.
"""

import asyncio
import contextlib
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.runner import SimulationRunner

router = APIRouter()
PROTOCOL_VERSION = 1


def envelope(kind: str, seq: int, data_json: str) -> str:
    """Wrap an already-serialised JSON payload in the message envelope."""
    return f'{{"type":"{kind}","seq":{seq},"data":{data_json}}}'


async def _pump(websocket: WebSocket, queue: "asyncio.Queue[str]", first_seq: int) -> None:
    """Forward snapshots from the viewer's queue to the socket."""
    seq = first_seq
    while True:
        payload = await queue.get()
        await websocket.send_text(envelope("snapshot", seq, payload))
        seq += 1


async def _discard_incoming(websocket: WebSocket) -> None:
    """Read and ignore client messages; returns when the client disconnects."""
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()


@router.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    """Stream snapshots to one viewer. Any number of viewers may connect."""
    runner: SimulationRunner = websocket.app.state.runner
    await websocket.accept()
    # Take the current state and subscribe in one step (no await between) so no frame is lost or reordered.
    current = runner.snapshot().model_dump_json()
    queue = runner.subscribe()
    tasks: list[asyncio.Task[None]] = []
    try:
        hello = f'{{"protocol":{PROTOCOL_VERSION},"server_time":"{datetime.now(UTC).isoformat()}"}}'
        await websocket.send_text(envelope("hello", 0, hello))
        await websocket.send_text(envelope("snapshot", 1, current))
        tasks = [
            asyncio.create_task(_pump(websocket, queue, first_seq=2)),
            asyncio.create_task(_discard_incoming(websocket)),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:  # a failed send just means the viewer left; mark the error as handled
            if not task.cancelled():
                task.exception()
    except (WebSocketDisconnect, RuntimeError):
        pass  # client went away while we were sending
    finally:
        runner.unsubscribe(queue)  # synchronous, so a viewer is always forgotten, even if we are cancelled
        for task in tasks:
            task.cancel()
