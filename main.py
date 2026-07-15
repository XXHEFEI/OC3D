"""FastAPI backend for the OC3D print and wardrobe experiences.

Printing is intentionally delegated to OpenClaw.  This service exposes the
browser-to-Gateway bridge and task-status APIs; it does not configure OpenClaw
or send jobs to a printer directly.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import io

import websockets
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
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
IP_IMAGES_DIR = BASE / "曦曦IP" / "曦曦IP" / "IP换装"

GATEWAY_WS = "ws://127.0.0.1:18789"


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="IP Print Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_dev_assets(request, call_next):
    """开发阶段强制不缓存页面/脚本，避免浏览器拿着旧版本跑（之前 GEN_USE_MOCK
    改了但版本号没同步 bump，导致浏览器一直用缓存的旧脚本，白跑了一次)。
    正式上线若要恢复缓存，删掉这段中间件即可。"""
    response = await call_next(request)
    if request.url.path.endswith((".js", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/ips", StaticFiles(directory=str(IP_IMAGES_DIR)), name="ips")


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
    # 有云链接则直接跳转到 OSS（公网可下；生成半上传的是 bundle.zip，含模型+源图）
    if state.get("oss_url"):
        return RedirectResponse(state["oss_url"])
    # 生成半产出 work/{task_id}/bundle.zip（模型+源图）；打印半产出 .3mf。都支持。
    task_dir = WORK_DIR / task_id
    files = (
        list(task_dir.glob("*.zip"))
        + list(task_dir.glob("*.stl"))
        + list(task_dir.glob("*.3mf"))
        + list(BASE.glob("*.3mf"))
    )
    if not files:
        raise HTTPException(404, "model file not found")
    path = files[0]
    if path.suffix.lower() == ".zip":
        media = "application/zip"
    elif path.suffix.lower() == ".stl":
        media = "model/stl"
    else:
        media = "application/vnd.ms-3mf"
    return FileResponse(path, filename=path.name, media_type=media)


def _lan_ip() -> str:
    """本机主局域网 IP。用 UDP socket 探测出口网卡地址（不实际发包），
    这样即使操作台用 localhost 打开页面，二维码也能指向手机可连的局域网地址。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@app.get("/api/qr/{task_id}")
def api_qr(task_id: str, request: Request):
    """返回二维码 PNG，编码该任务 STL 的下载链接（现场可用）。

    默认自动用本机局域网 IP + 当前端口构造链接（即使用 localhost 打开页面也没关系）；
    手机需与本机同一 Wi-Fi。若有固定外网地址/隧道，设环境变量 OC3D_PUBLIC_BASE
    （如 https://xxx.ngrok.io）覆盖。实际编码的链接放在响应头 X-Download-URL 便于核对。
    """
    import qrcode

    # 优先用云端(OSS)公网链接——任意网络都能下，最适合场馆
    oss_url = task_state.get_status(task_id).get("oss_url")
    if oss_url:
        download_url = oss_url
    else:
        base = os.environ.get("OC3D_PUBLIC_BASE", "").rstrip("/")
        if not base:
            port = request.url.port or 8080
            base = f"http://{_lan_ip()}:{port}"
        download_url = f"{base}/api/download/{task_id}"

    img = qrcode.make(download_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"X-Download-URL": download_url})


@app.get("/api/gateway-token")
def api_gateway_token():
    """读本机 OpenClaw 配置里的 gateway token，供前端连接用。
    这样 token 不写死进仓库——每台机器读各自 openclaw.json（经 OPENCLAW_HOME 定位）。"""
    home = os.environ.get("OPENCLAW_HOME")
    if not home:
        raise HTTPException(500, "OPENCLAW_HOME 未设置；请由外部 OpenClaw 环境提供")
    cfg = Path(home) / ".openclaw" / "openclaw.json"
    try:
        with open(cfg, encoding="utf-8") as f:
            data = json.load(f)
        token = data["gateway"]["auth"]["token"]
    except Exception as e:
        raise HTTPException(500, f"读取 gateway token 失败（检查 OPENCLAW_HOME）: {e}")
    return {"token": token}


@app.get("/")
def index():
    # 落地首页：index.html → 点进 select.html 枢纽（左打印 / 右换装建模）
    return FileResponse(TEMPLATES / "index.html")


# 把 templates/ 下的页面按文件名当静态页提供（DIY 多页面流程：
# /select.html /customize.html /preview_diy.html /takeaway.html）。
# 必须放在所有 API/WS/"/" 路由之后挂载——先注册的路由优先匹配，
# 只有未匹配到的路径（各 .html）才落到这里；页面内相对的 static/... 仍走 /static 挂载。
app.mount("/", StaticFiles(directory=str(TEMPLATES), html=True), name="pages")
