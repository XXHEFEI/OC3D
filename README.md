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
| `static/prompt.js` | `buildPrintPrompt()` — 构造发给 Agent 的打印 prompt，并按黑/白文件传 AMS 映射 |
| `static/app.js` | 应用控制器（预留，当前逻辑内联在 index.html 中） |

### 预切片文件

| 目录 | 内容 |
|------|------|
| `static/3D_model/` | 预切片的 `.gcode.3mf` 文件（Bambu Studio 切片，直接发送打印） |
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
  │  prompt.js → buildPrintPrompt() 构造打印指令
  ▼
OpenClaw Gateway (:18789)
  │  接收 prompt，调度 Agent 执行
  ▼
OpenClaw Agent
  ├── 步骤 1: bambu.py print              ← FTPS 上传 + MQTT 下发打印指令
  ├── 步骤 2: monitor_bridge.py            ← 后台运行，持续轮询直到打印完成
  └── 步骤 3: task_state.set_status(done)  ← 标记完成
       │
       │  monitor_bridge.py 每 15s 轮询一次
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
5. `buildPrintPrompt()` 构造打印 prompt → `GatewayChat.sendMessage()` 发送
6. Agent 依序执行：
   - `bambu.py print <模型> --confirmed --ams-mapping <映射>` → FTPS 上传 + MQTT 下发
   - `monitor_bridge.py <task_id> --interval 15` → 后台监控直到打印完成
   - `task_state.set_status(done)` → 标记完成
7. `monitor_bridge.py` 每 15 秒直连 MQTT 获取进度（state/progress/layer/remaining），写入 `work/{task_id}_state.json`
8. 后端 `/ws/task/{id}` 每秒检查文件 mtime，变化时通过 WebSocket 推前端
9. 前端实时更新进度信息

## Agent 职责

Agent 只负责按顺序执行提示词中的命令：步骤 1 等待发送结果，步骤 2 启动后台监控后立即返回，不做额外操作：

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

角色和黑/白预切片文件由 `ips/list.json` 提供，页面把选中的文件名传给 `static/prompt.js`：

- `models.black` — 黑色 `.gcode.3mf` 文件
- `models.white` — 白色 `.gcode.3mf` 文件
- `turntable` — 预览用的转台帧目录

## 搬到别的机器需要改什么（写死的本机路径 / 配置）

以下都是按开发机（macOS, 用户 hefei）写死的，换机器/部署时要按实际情况调整：

**仓库内（git 跟踪，需手动改）：**

| 文件:行 | 写死的值 | 换机器时改成 |
|---|---|---|
| `static/prompt.generate.js` `GEN_WORK_DIR` | `/Users/hefei/Desktop/MX_intern/OC3D` | 本机仓库根目录绝对路径；Windows 示例：`C:/Users/<user>/Desktop/OC3D` |
| `static/prompt.generate.js` `GEN_PYTHON` | `/opt/anaconda3/bin/python3` | 装了 requests/trimesh/oss2 的 Python 绝对路径；Windows 示例：`C:/Users/<user>/miniconda3/envs/oc3d/python.exe` |
| `static/prompt.js` `WORK_DIR`/`SKILLS_DIR`/`STOCK_DIR` | `/Users/hefei/.../OC3D` | 本机仓库根目录；`STOCK_DIR` 必须指向 `static/3D_model` |
| `static/prompt.js` `PRINTER_IP`/`PRINTER_SERIAL`/`ACCESS_CODE` | `172.20.10.6` 等 | 现场打印机的 IP/序列号/访问码；访问码不要写入 README 或提交到 Git |
| `main.py` `/api/gateway-token` 兜底 | `~/Desktop/openclaw-home` | 建议设置 `OPENCLAW_HOME`；Windows 示例：`C:/Users/<user>/Desktop/openclaw-home` |
| `scripts/启动OC3D换装Demo.command` | `OPENCLAW_BIN`/`OPENCLAW_HOME_DIR`/`PROJECT_DIR` | 本机绝对路径；换机器要改这三个变量。**用时需复制到桌面双击**（.command 文件从 Finder 里跑才有终端窗口，直接在仓库目录里双击体验不好） |
| `scripts/停止OC3D换装Demo.command` | 无路径依赖，只按端口号 kill 进程 | 一般不用改，除非端口号变了 |
| `scripts/启动一体机TripoSG容器.command` | `AIO_IP`(`192.168.100.2`)/`AIO_USER`(`user`)/`SSH_KEY`(`~/.ssh/id_ed25519_aio`)/`CONTAINER`(`triposg-dev`) | 换一体机或换网络方案要改这四个变量 |

**不在仓库内（gitignore / 各机器自建，且换机器/换一体机时需要重新配置，不是简单复制文件就行）：**

- `.oss.json`（阿里云 OSS 凭据，各机器填自己的；模板见 `.oss.json.example`）
- `.meshy_key`（Meshy API key，各机器自己放）
- `~/.ssh/id_ed25519_aio`（Mac→一体机的专用 SSH 私钥，**私钥本身绝不能进仓库**）。换一体机需要重新走一遍：
  1. `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_aio -N ""` 生成新 key
  2. `ssh-copy-id -i ~/.ssh/id_ed25519_aio.pub user@<一体机IP>` 装到新一体机
  3. 一体机上装一条精确授权的 sudoers 规则（只允许免密执行 `docker start <容器名>` 和裸 `docker ps`，不要开放整个 docker 组/sudo 权限），示例见下方"一体机运维"一节
  4. 一体机的静态 IP 也要用 `nmcli` 重新配置并设 `autoconnect yes`（不要只用临时的 `ip addr add`，重启会丢）

**依赖**：generate_3d.py 需要 `requests`、`trimesh`、`Pillow`、`oss2`；且必须装在 `GEN_PYTHON` 指向的那个解释器里（Agent 默认的系统 python3 可能没装 → 会 `ModuleNotFoundError`）。

**gateway token**：不用改——前端 `gateway.js` 运行时从 `/api/gateway-token` 动态取本机 OpenClaw 配置里的 token，不写死。

### Windows 移植步骤（PowerShell）

当前经典打印页面的 macOS 版本包含三类平台相关内容：JavaScript 中的绝对路径、`static/prompt.js` 生成的 bash 命令，以及 `.command` 启动脚本。移植到 Windows 时，不能只把 `/Users/...` 替换成 Windows 路径，还要把 Agent 执行的 shell 命令改为 PowerShell。

#### 1. 先确定三条本机路径

下面是示例，按 Windows 实际安装位置修改：

```powershell
$ProjectDir = "C:/Users/<user>/Desktop/OC3D"
$OpenClawHome = "C:/Users/<user>/Desktop/openclaw-home"
$Python = "C:/Users/<user>/miniconda3/envs/oc3d/python.exe"

$env:OPENCLAW_HOME = $OpenClawHome
$env:PYTHONIOENCODING = "utf-8"
```

JavaScript 字符串建议使用正斜杠 `C:/Users/...`，这样不用额外处理反斜杠转义。修改：

1. `static/prompt.generate.js`：`GEN_WORK_DIR`、`GEN_PYTHON`
2. `static/prompt.js`：`WORK_DIR`、`SKILLS_DIR`、`STOCK_DIR`
3. `main.py`：优先通过环境变量 `OPENCLAW_HOME` 指向 `$OpenClawHome`

当前 `SKILLS_DIR` 指向 OC3D 仓库，所以网页打印流程执行的是仓库内的 `bambu-studio-ai/scripts/bambu.py`。如果 Windows 上改为使用 OpenClaw 技能目录的副本，也必须同步修改：

```text
C:/Users/<user>/Desktop/openclaw-home/.openclaw/workspace/skills/bambu-studio-ai/scripts/bambu.py
```

OpenClaw 不会固定只调用某一份副本，实际使用哪份由提示词中的绝对路径或技能工作目录决定。

#### 2. 把打印 prompt 从 bash 改成 PowerShell

macOS 版本使用 `export`、`nohup`、`disown`。Windows 版本应在 `static/prompt.js` 生成类似下面的命令：

```powershell
$env:BAMBU_MODE = "local"
$env:BAMBU_IP = "<printer-ip>"
$env:BAMBU_SERIAL = "<printer-serial>"
$env:BAMBU_ACCESS_CODE = "<access-code>"
$env:PYTHONIOENCODING = "utf-8"

# 黑色文件
& $Python "$ProjectDir/bambu-studio-ai/scripts/bambu.py" print `
  "$ProjectDir/static/3D_model/spring_cat_black.gcode.3mf" `
  --confirmed --ams-mapping "-1,-1,2"

# 白色文件
& $Python "$ProjectDir/bambu-studio-ai/scripts/bambu.py" print `
  "$ProjectDir/static/3D_model/spring_cat_white.gcode.3mf" `
  --confirmed --ams-mapping "-1,1"
```

监控命令用 `Start-Process` 后台启动，不要在 Windows 继续使用 `nohup` 或 `disown`：

```powershell
$monitorOut = Join-Path $env:TEMP "monitor_<task_id>.out.log"
$monitorErr = Join-Path $env:TEMP "monitor_<task_id>.err.log"
Start-Process -FilePath $Python -ArgumentList @(
  "$ProjectDir/monitor_bridge.py",
  "<task_id>",
  "--interval", "15"
) -RedirectStandardOutput $monitorOut `
  -RedirectStandardError $monitorErr `
  -WindowStyle Hidden
```

`Start-Process` 会立即返回，环境变量会传给后台进程；前端状态仍由 `monitor_bridge.py` 写入 `work/{task_id}_state.json`。

#### 3. Windows 启动服务

`.command` 文件是 macOS 启动器，Windows 不执行它们。打开两个 PowerShell 窗口：

```powershell
# 窗口 1：OpenClaw Gateway
$env:OPENCLAW_HOME = "C:/Users/<user>/Desktop/openclaw-home"
openclaw gateway run
```

```powershell
# 窗口 2：OC3D 后端
Set-Location "C:/Users/<user>/Desktop/OC3D"
& "C:/Users/<user>/miniconda3/envs/oc3d/python.exe" -m uvicorn main:app `
  --host 0.0.0.0 --port 8000 --reload
```

然后打开 `http://localhost:8000`。Windows 等价替代：

| macOS | Windows PowerShell |
|---|---|
| `open http://localhost:8000` | `Start-Process "http://localhost:8000"` |
| `lsof -i :8000` | `Get-NetTCPConnection -LocalPort 8000` |
| `tail -15 /tmp/file.log` | `Get-Content $env:TEMP/file.log -Tail 15` |

#### 4. 打印前检查

- 电脑和打印机在同一局域网，打印机开启 LAN Mode/Developer Mode。
- `BAMBU_IP`、`BAMBU_SERIAL`、`BAMBU_ACCESS_CODE` 使用 Windows 现场打印机的真实值。
- `static/3D_model/` 中保留 ASCII 文件名，避免 FTP 上传中文文件名触发 553。
- 黑色映射为 `-1,-1,2`，白色映射为 `-1,1`；不要恢复固定的 `--ams-mapping "0"`。
- `bambu-studio-ai/.secrets.json` 只放本机，不要提交真实访问码或其他密钥。

Windows 移植完成后，先用以下命令检查脚本路径和打印机连接：

```powershell
& $Python "$ProjectDir/bambu-studio-ai/scripts/bambu.py" status
& $Python "$ProjectDir/bambu-studio-ai/scripts/bambu.py" ams
```

如果要测试打印，优先从网页流程测试，因为网页会同时验证路径、OpenClaw 调度、AMS 映射和后台监控。

## 一体机运维（网线直连 + 免密启动容器）

一体机（MetaX C500，详见 `TODO.md` 第 8 节）与 Mac 网线直连、跑 TripoSG 的 Docker 容器。以下是重启/换机时要恢复的配置（均不在仓库里，是一体机/Mac 本机状态）：

**一体机侧：静态 IP 持久化**（用 NetworkManager，不要只用临时的 `ip addr add`，否则重启会丢）：
```bash
sudo nmcli connection modify <连接名> ipv4.method manual ipv4.addresses 192.168.100.2/24
sudo nmcli connection modify <连接名> connection.autoconnect yes
sudo nmcli connection up <连接名>
```

**一体机侧：精确授权的 sudoers 规则**（只让免密执行这两条命令，不开放整个 docker 组/sudo 权限）：
```
# /etc/sudoers.d/oc3d-docker-start（权限须是 root:root 0440，务必先用 visudo -c -f 验证语法再安装）
user ALL=(root) NOPASSWD: /snap/bin/docker start <容器名>
user ALL=(root) NOPASSWD: /snap/bin/docker ps
```
（`docker` 的实际路径视安装方式而定，snap 装的通常在 `/snap/bin/docker`；sudoers 按精确字符串匹配，多加参数如 `docker ps -a` 不会命中这条规则，是有意为之的最小权限设计。）

**Mac 侧**：`scripts/启动一体机TripoSG容器.command` 用上面配置的 SSH key + sudoers 规则，一键 SSH 过去拉起容器，不需要手动敲命令。
