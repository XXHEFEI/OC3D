"""
main.py — FastAPI backend for IP Print Web.

Endpoints:
  GET  /              → index.html
  GET  /ws/gateway    → WebSocket proxy to OpenClaw Gateway
  GET  /api/list-ips  → IP character list
  POST /api/generate  → create a task, return task_id
  GET  /api/status/{id}  → task state
  GET  /api/download/{id} → .3mf file download
  POST /api/print/{id}    → send stock test cube to printer (placeholder
                             until the generated model's geometry is finalized)
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

import websockets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

import task_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

# ─── paths ────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
IPS_DIR = BASE / "ips"
WORK_DIR = BASE / "work"
STATIC_DIR = BASE / "static"
TEMPLATES = BASE / "templates"

GATEWAY_WS = "ws://127.0.0.1:18789"

# 占位打印目标：白模未定稿期间，"同意打印"实际送去打印机的是这个
# 已经在 Bambu Studio 里手动切好片的官方校准方块项目文件。
STOCK_PRINT_3MF = BASE / "static" / "3D" / "cat.gcode.3mf"
DISCOVER_SCRIPT = BASE / "discover_printer.py"
BAMBU_SKILL_DIR = Path("C:/Users/i26293/.openclaw/workspace/skills/bambu-studio-ai")
BAMBU_SCRIPTS_DIR = BAMBU_SKILL_DIR / "scripts"
BAMBU_SECRETS_PATH = BAMBU_SKILL_DIR / ".secrets.json"
PRINTER_SERIAL = "20P6BJ652100030"


def _bambu_env(printer_ip: str) -> dict:
    """LocalBackend (bambu.py) only reads BAMBU_* from os.environ — it does
    NOT fall back to config.json/.secrets.json for IP/serial/access_code.
    So we must inject them explicitly for every subprocess call.
    """
    with open(BAMBU_SECRETS_PATH, encoding="utf-8") as f:
        access_code = json.load(f)["access_code"]
    env = os.environ.copy()
    env["BAMBU_MODE"] = "local"
    env["BAMBU_IP"] = printer_ip
    env["BAMBU_SERIAL"] = PRINTER_SERIAL
    env["BAMBU_ACCESS_CODE"] = access_code
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="IP Print Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── WebSocket proxy to OpenClaw Gateway ─────────────────────────────────────
@app.websocket("/ws/gateway")
async def ws_gateway_proxy(browser_ws: WebSocket):
    """Raw proxy: browser ↔ OpenClaw Gateway. No message parsing."""
    await browser_ws.accept()

    try:
        gw_ws = await websockets.connect(
            GATEWAY_WS,
            ping_interval=None,
            max_size=30 * 1024 * 1024,
            origin="http://127.0.0.1:18789",
        )
    except Exception as e:
        log.error("Failed to connect to Gateway: %s", e)
        await browser_ws.close()
        return

    async def browser_to_gw():
        try:
            while True:
                data = await browser_ws.receive_text()
                await gw_ws.send(data)
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            await gw_ws.close()

    async def gw_to_browser():
        try:
            async for data in gw_ws:
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                await browser_ws.send_text(data)
        except Exception:
            pass

    await asyncio.gather(browser_to_gw(), gw_to_browser())


@app.websocket("/ws/task/{task_id}")
async def ws_task_status(websocket: WebSocket, task_id: str):
    """Real-time task status push via WebSocket.

    Polls the state JSON file for changes (Agent runs in a subprocess and
    can only write to the file, not trigger in-process callbacks).
    """
    await websocket.accept()

    state_file = task_state.WORK_DIR / f"{task_id}_state.json"
    if not state_file.exists():
        await websocket.close(code=1008, reason="Task not found")
        return

    # Send current state immediately
    state = task_state.get_status(task_id)
    await websocket.send_json(state)

    if state["status"] in ("done", "failed"):
        await websocket.close()
        return

    last_mtime = state_file.stat().st_mtime if state_file.exists() else 0

    try:
        while True:
            await asyncio.sleep(1.0)

            if not state_file.exists():
                continue

            current_mtime = state_file.stat().st_mtime
            if current_mtime != last_mtime:
                last_mtime = current_mtime
                current = task_state.get_status(task_id)
                await websocket.send_json(current)

                if current["status"] in ("done", "failed"):
                    break
    except WebSocketDisconnect:
        pass

    await websocket.close()


# ─── pydantic models ──────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    ip_id: str


# ─── HTTP endpoints ───────────────────────────────────────────────────────────
@app.get("/api/list-ips")
def list_ips():
    with open(IPS_DIR / "list.json", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    """Create a task and return task_id. Pipeline is driven by OpenClaw Agent."""
    task_id = task_state.start_task(req.ip_id)
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/status/{task_id}")
def api_status(task_id: str):
    state = task_state.get_status(task_id)
    if state.get("status") == "unknown":
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, **state}


@app.get("/api/download/{task_id}")
def api_download(task_id: str):
    state = task_state.get_status(task_id)
    if state.get("status") != "done":
        raise HTTPException(400, "Task not ready")
    # Check both root and work/{task_id}/ for .3mf output
    files = list(BASE.glob("*.3mf")) + list((WORK_DIR / task_id).glob("*.3mf"))
    if not files:
        raise HTTPException(404, ".3mf file not found")
    path = files[0]
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.ms-3mf",
    )


@app.post("/api/print/{task_id}")
def api_print(task_id: str):
    """User approved the preview. Send the printer a job.

    Placeholder behavior: the model geometry the agent generates isn't
    finalized yet (precision/print-time not validated), so this sends a
    pre-sliced stock calibration cube instead, to validate the
    discover → upload → start-print pipeline independently of model quality.
    """
    state = task_state.get_status(task_id)
    if state.get("status") != "done":
        raise HTTPException(400, "Task not ready for printing")

    if not STOCK_PRINT_3MF.exists():
        raise HTTPException(500, f"Stock print file missing: {STOCK_PRINT_3MF}")

    # Step 1: re-resolve printer IP by serial (printer may have switched networks)
    try:
        disc = subprocess.run(
            [
                "python",
                str(DISCOVER_SCRIPT),
                "--serial",
                PRINTER_SERIAL,
                "--update-config",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "打印机发现超时，请确认打印机已开机并在同一局域网")

    if disc.returncode != 0:
        log.error("discover_printer failed: %s", disc.stderr.strip())
        raise HTTPException(502, "未找到打印机，请确认它已开机并连接到当前网络")

    printer_ip = disc.stdout.strip().splitlines()[0] if disc.stdout.strip() else None
    if not printer_ip:
        raise HTTPException(502, "未能解析打印机 IP")

    # Step 2: send the stock cube to the printer
    try:
        result = subprocess.run(
            [
                "python",
                str(BAMBU_SCRIPTS_DIR / "bambu.py"),
                "print",
                str(STOCK_PRINT_3MF),
                "--confirmed",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=_bambu_env(printer_ip),
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "发送打印指令超时")

    output = result.stdout + result.stderr
    if "Started printing" not in output:
        log.error("bambu.py print failed: %s", output.strip())
        raise HTTPException(502, f"打印机未确认开始打印: {output.strip()[-300:]}")

    task_state.set_status(
        task_id,
        "printing",
        step="printing",
        progress=100,
        message=f"已发送至打印机（占位模型，IP {printer_ip}），等待自定义模型定稿后再切换",
    )
    return {"task_id": task_id, "status": "printing", "printer_ip": printer_ip}


@app.get("/")
def index():
    return FileResponse(TEMPLATES / "index.html")
