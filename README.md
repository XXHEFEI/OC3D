# IP Print Web

IP 形象 3D 打印直连站。选择 IP 角色，OpenClaw Agent 直接调用 `bambu.py` 将预切片 `.3mf` 文件发送至 Bambu Lab 打印机，`monitor_bridge.py` 持续监控进度并推送前端。

## 环境要求

- **Python** ≥ 3.10
- **OpenClaw** CLI（Gateway + Agent 调度）
- **bambu-studio-ai** skill（提供 `bambu.py` 打印机控制脚本）
- **bambulabs-api**（Python MQTT 库，LAN 模式直连打印机）
- 打印机需开启 **Developer Mode**（关闭 MQTT 签名验证）

### Python 依赖

| 包 | 用途 |
|----|------|
| `fastapi` | Web 框架，REST API + WebSocket |
| `uvicorn` | ASGI 服务器 |
| `pydantic` | 请求体校验 |
| `websockets` | WebSocket 客户端（连接 Gateway） |
| `bambulabs_api` | Bambu Lab 打印机 MQTT 通信 |

安装：

```bash
pip install fastapi uvicorn pydantic websockets bambulabs-api
```

## 快速开始

需要同时启动两个服务：

```bash
# 终端 1: OpenClaw Gateway
openclaw gateway

# 终端 2: FastAPI (端口 8000)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

打开 `http://localhost:8000`，选择角色 → 点击「开始打印」→ Agent 发送打印 → 实时进度推送。

## 项目结构

### 应用代码

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 后端 — 静态文件、REST API、WebSocket 代理 + 任务状态推送 |
| `task_state.py` | 任务状态持久化，写入 `work/{task_id}_state.json` |
| `monitor_bridge.py` | 打印监控脚本 — 直连 MQTT 轮询进度，写入 task_state 供前端读取 |
| `templates/index.html` | SPA 前端 — HTML/CSS 布局、DOM 渲染、交互逻辑 |
| `static/gateway.js` | `GatewayChat` — WebSocket 连接 OpenClaw Gateway、RPC 通信、事件分发 |
| `static/prompt.js` | `COSTUMES` 数据 + `buildPrompt()` — 构造发给 Agent 的打印 prompt |
| `static/app.js` | 应用控制器（预留，当前逻辑内联在 index.html 中） |

### 预切片文件

| 目录 | 内容 |
|------|------|
| `static/3D/` | 预切片的 `.gcode.3mf` 文件（Bambu Studio 切片，直接发送打印） |
| `static/ip-costumes/` | IP 换装预览图 |

### 配置与数据

| 文件/目录 | 职责 |
|-----------|------|
| `.claude/settings.local.json` | Claude Code 项目级权限配置 |
| `ips/list.json` | IP 角色列表（供 `/api/list-ips` 读取） |
| `work/` | 运行时任务状态目录，每个 `{task_id}_state.json` 记录单个任务进度 |
| `曦曦IP/` | 原始 IP 形象素材 |
| `2D 三视图/` | 角色三视图参考 |

## 架构

```
浏览器 (index.html)
  │  gateway.js → WebSocket → OpenClaw Gateway
  │  prompt.js → buildPrompt() 构造打印指令
  ▼
OpenClaw Gateway (:18789)
  │  接收 prompt，调度 Agent 执行
  ▼
OpenClaw Agent
  ├── 步骤 1: bambu.py print              ← FTPS 上传 + MQTT 下发打印指令
  ├── 步骤 2: monitor_bridge.py            ← 阻塞运行，持续轮询直到打印完成
  └── 步骤 3: task_state.set_status(done)  ← 标记完成
       │
       │  monitor_bridge.py 每 60s 轮询一次
       │  直连打印机 MQTT 获取 progress/layer/remaining
       │  写入 work/{task_id}_state.json
       ▼
FastAPI (main.py :8000)
  ├── /                       GET  — index.html
  ├── /api/generate           POST — 创建任务，返回 task_id
  ├── /api/status/{id}        GET  — 任务状态
  ├── /api/download/{id}      GET  — 下载 .3mf 文件
  ├── /api/print/{id}         POST — 发送打印（占位流程）
  ├── /ws/gateway             WS   — 浏览器 ↔ Gateway 代理
  └── /ws/task/{id}           WS   — 实时任务状态推送（mtime 轮询）
```

## 数据流

1. 页面加载 → `GatewayChat` 通过 `/ws/gateway` 连接 Gateway，完成 RPC 握手
2. 用户选择形象 → 点击「开始打印」
3. 前端 `POST /api/generate` 创建任务 → 得到 `task_id`
4. 前端建立 `/ws/task/{task_id}` WebSocket，接收实时状态推送
5. `buildPrompt()` 构造打印 prompt → `GatewayChat.sendMessage()` 发送
6. Agent 依序执行：
   - `bambu.py print <模型> --confirmed` → FTPS 上传 + MQTT 下发
   - `monitor_bridge.py <task_id> --interval 60` → 阻塞监控直到打印完成
   - `task_state.set_status(done)` → 标记完成
7. `monitor_bridge.py` 每 60 秒直连 MQTT 获取进度（state/progress/layer/remaining），写入 `work/{task_id}_state.json`
8. 后端 `/ws/task/{id}` 每秒检查文件 mtime，变化时通过 WebSocket 推前端
9. 前端实时更新进度信息

## Agent 职责

Agent 只负责**按顺序启动命令并等待结束**，不做额外操作：

- 不轮询打印机状态（由 monitor_bridge.py 内部完成）
- 不解析输出、不推送前端（由后端 WebSocket 自动完成）
- 不修改任何文件或参数

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| POST | `/api/generate` | 创建任务，请求体 `{"ip_id"}` |
| GET | `/api/status/{task_id}` | 任务状态（status, step, progress, message） |
| GET | `/api/download/{task_id}` | 下载 .3mf 文件 |
| POST | `/api/print/{task_id}` | 发送打印（当前为占位流程） |
| WS | `/ws/gateway` | 浏览器 ↔ Gateway 透明代理 |
| WS | `/ws/task/{task_id}` | 实时任务状态推送 |

## IP 角色

三个角色定义在 `static/prompt.js` 的 `COSTUMES` 数组中：

- 猫1 (`costume_1`) — `/static/ip-costumes/1.png`
- 猫2 (`costume_2`) — `/static/ip-costumes/2.png`
- 画家 (`painter`) — `/static/ip-costumes/画家.png`

## 搬到别的机器需要改什么（写死的本机路径 / 配置）

以下都是按开发机（macOS, 用户 hefei）写死的，换机器/部署时要按实际情况调整：

**仓库内（git 跟踪，需手动改）：**

| 文件:行 | 写死的值 | 换机器时改成 |
|---|---|---|
| `static/prompt.generate.js` `GEN_WORK_DIR` | `/Users/hefei/Desktop/MX_intern/OC3D` | 本机仓库根目录绝对路径 |
| `static/prompt.generate.js` `GEN_PYTHON` | `/opt/anaconda3/bin/python3` | 装了 requests/trimesh/oss2 的 python3 绝对路径（Agent 要用它跑 generate_3d.py）|
| `static/prompt.js` `WORK_DIR`/`SKILLS_DIR`/`STOCK_DIR` | `/Users/hefei/.../OC3D` | 本机仓库根目录（打印半）|
| `static/prompt.js` `PRINTER_IP`/`PRINTER_SERIAL`/`ACCESS_CODE` | `172.20.10.6` 等 | 现场打印机的 IP/序列号/访问码 |
| `main.py` `/api/gateway-token` 兜底 | `~/Desktop/openclaw-home` | 优先用环境变量 `OPENCLAW_HOME`；启动脚本已 export，改这个即可 |

**不在仓库内（gitignore / 桌面，各机器自建）：**

- `.oss.json`（阿里云 OSS 凭据，各机器填自己的；模板见 `.oss.json.example`）
- `.meshy_key`（Meshy API key，各机器自己放）
- 桌面 `启动OC3D换装Demo.command` / `停止OC3D换装Demo.command`：里面 `OPENCLAW_BIN`/`OPENCLAW_HOME_DIR`/`PROJECT_DIR` 是本机绝对路径，换机器要改（脚本本身不在仓库，需各机器自备）

**依赖**：generate_3d.py 需要 `requests`、`trimesh`、`Pillow`、`oss2`；且必须装在 `GEN_PYTHON` 指向的那个解释器里（Agent 默认的系统 python3 可能没装 → 会 `ModuleNotFoundError`）。

**gateway token**：不用改——前端 `gateway.js` 运行时从 `/api/gateway-token` 动态取本机 OpenClaw 配置里的 token，不写死。
