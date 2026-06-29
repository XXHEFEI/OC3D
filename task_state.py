"""task_state.py — Thin state persistence for generation tasks.

Reads/writes work/{task_id}_state.json. Used by both the FastAPI backend
(for polling) and the OpenClaw Agent (for progress updates during pipeline).

Supports subscription-based notifications for WebSocket real-time push.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine

BASE = Path(__file__).parent
WORK_DIR = BASE / "work"

os.makedirs(WORK_DIR, exist_ok=True)

# ─── Subscription system ──────────────────────────────────────────────────────
# Maps task_id -> list of async callbacks
_subscribers: dict[str, list[Callable[[dict], Coroutine[Any, Any, None]]]] = {}


def subscribe(task_id: str, callback: Callable[[dict], Coroutine[Any, Any, None]]):
    """Register an async callback for task state changes."""
    if task_id not in _subscribers:
        _subscribers[task_id] = []
    _subscribers[task_id].append(callback)


def unsubscribe(task_id: str, callback: Callable[[dict], Coroutine[Any, Any, None]]):
    """Remove a previously registered callback."""
    if task_id in _subscribers:
        try:
            _subscribers[task_id].remove(callback)
        except ValueError:
            pass
        if not _subscribers[task_id]:
            del _subscribers[task_id]


async def _notify(task_id: str, state: dict):
    """Notify all subscribers of a state change."""
    callbacks = _subscribers.get(task_id, [])
    for cb in callbacks:
        try:
            await cb(state)
        except Exception:
            pass


def set_status(
    task_id,
    status,
    step=None,
    progress=None,
    message=None,
    preview_url=None,
    analyze_result=None,
    download_url=None,
    **extra,
):
    """Write (merge) task state to work/{task_id}_state.json.

    After writing, schedules notification to all subscribers.
    """
    state_file = WORK_DIR / f"{task_id}_state.json"
    state = {}
    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    updates = {
        "status": status,
        "step": step,
        "progress": progress,
        "message": message,
        "preview_url": preview_url,
        "analyze_result": analyze_result,
        "download_url": download_url,
    }
    for k, v in updates.items():
        if v is not None:
            state[k] = v
    state.update({k: v for k, v in extra.items() if v is not None})

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    # Schedule async notification (safe to call from sync context)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_notify(task_id, state))
    except RuntimeError:
        pass


def get_status(task_id):
    """Read task state. Returns {"status":"unknown"} if not found or corrupt."""
    state_file = WORK_DIR / f"{task_id}_state.json"
    if state_file.exists():
        try:
            with open(state_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"status": "unknown"}
    return {"status": "unknown"}


def start_task(ip_id: str) -> str:
    """Create a new task_id with initial queued state. Returns task_id."""
    task_id = uuid.uuid4().hex[:10]
    set_status(
        task_id,
        "queued",
        step="queued",
        progress=0,
        message="任务已创建，等待 OpenClaw Agent 处理...",
        ip_id=ip_id,
    )
    return task_id
