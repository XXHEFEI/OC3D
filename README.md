# OC3D

OC3D 是一个双链路体验项目：

- **经典速印**：用户选择已切片的经典模型；页面通过 OpenClaw 发送提示词，由运行在本机环境中的 Bambu 工具把 3MF 文件发送至打印机，并持续展示监控状态。
- **魔法衣橱**：用户从 6 套服饰 × 6 个配饰状态（5 个实体道具加“不佩戴”）中自由搭配，查看预制主图与正／侧／背三视图，扫码下载 OSS 上对应的数字包。

## 正式用户流程

```text
首页 → 选择枢纽
       ├─ 经典速印 → 选模型/颜色 → OpenClaw → Bambu 打印 → 完成页
       └─ 魔法衣橱 → 6×6 搭配 → 三视图 → 二维码 → OSS ZIP
```

打印完成由 `monitor_bridge.py` 写入 `done` 状态，`printing_classic.html` 随后跳转到 `finish_classic.html`。失败会保留在打印页显示原因。

## OpenClaw 集成边界

本仓库**只保留接入 OpenClaw 的接口**，不负责安装、配置或托管 OpenClaw，也不提交 Gitee 或其他模型供应商的实际配置与凭据。

仓库中的接口包括：

- `/ws/gateway`：浏览器到本机 OpenClaw Gateway 的 WebSocket 代理。
- `static/gateway.js`：Gateway RPC 客户端。
- `static/prompt.js`：打印提示词构造器；传模型展示名、文件名、任务 ID 和 AMS 映射。
- `/api/gateway-token`：从外部已配置的 OpenClaw 环境读取 Gateway token，令牌不写入仓库。

部署环境需自行提供一个已可用的 OpenClaw Gateway。当前接口约定如下：

| 名称 | 用途 | 归属 |
| --- | --- | --- |
| `OPENCLAW_HOME` | 让后端定位外部 Gateway token 配置 | 外部 OpenClaw 环境 |
| `OC3D_PROJECT_DIR` | Agent 执行 `bambu.py` 与监控脚本时使用的仓库绝对路径 | 外部运行环境 |
| `BAMBU_MODE`、`BAMBU_IP`、`BAMBU_SERIAL`、`BAMBU_ACCESS_CODE` | Bambu 本机连接信息 | 外部运行环境 |

打印机凭据、模型供应商凭据和 Gateway token 均不得硬编码或提交到前端静态资源、提示词、README 或 Git。浏览器会在运行时从后端取得 Gateway token 用于认证。

## 本地运行

前提：外部 OpenClaw Gateway 已经按现场环境启动并配置完成；本仓库不提供该配置步骤。

当前 Web 与打印监控的 Python 依赖：

```bash
pip install fastapi uvicorn pydantic websockets "qrcode[pil]" bambulabs-api
```

二维升三维接口停用时无需安装其依赖；将来恢复时再额外安装
`requests`、`trimesh`、`Pillow`、`oss2`。

安装后启动 FastAPI：

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

浏览器访问 `http://localhost:8080`。打印链路还需要 Gateway 与打印机处于可用状态；换装预制展示不调用 Meshy 或 OpenClaw。

## 当前必须保留的运行资源

| 范围 | 关键文件／目录 |
| --- | --- |
| 共用后端 | `main.py`、`task_state.py`、`monitor_bridge.py` |
| 打印页面 | `templates/select_classic.html`、`preview_classic.html`、`printing_classic.html`、`finish_classic.html` |
| 打印资源 | `ips/list.json`、`static/3D_model/*_{black,white}.gcode.3mf`、`static/turntable/` |
| 枢纽展示资源 | `曦曦IP/曦曦IP/IP换装/`，由后端以 `/ips/` 提供给 `select.html` |
| Bambu 接口 | `bambu-studio-ai/scripts/bambu.py`、`bambu-studio-ai/scripts/common.py` |
| 换装页面 | `templates/customize.html`、`preview_diy.html`、`takeaway.html` |
| 换装资源 | `static/xixi_diy/`、`static/qr/`、`static/qr/manifest.json` |

换装侧已校验为完整 6×6：36 张组合主图、108 张三视图和 36 张二维码。二维码指向的 OSS ZIP 是数字包的来源；仓库当前不提供视频播放器，也不存放 DIY 视频文件。若数字包承诺包含视频，应在 OSS 交付侧验收。

二维码需要更新时，维护 `static/qr/manifest.json` 并使用 `scripts/generate_diy_qr.py` 重新生成二维码图片。

## 停用但保留：二维升三维接口

现行页面不调用二维升三维链路；它作为后续恢复能力保留：

- `generate_3d.py`：可插拔的生成适配器（Meshy 或未来一体机后端）。
- `static/prompt.generate.js`：未被页面加载的 OpenClaw 提示词接口，默认 `--mock`。
- `compose_views.py`：已失效的历史图层合成原型，当前配置和素材不满足其输入约定，不能直接恢复。
- `combos.json`、`scripts/aio_upscale.sh`、`scripts/启动一体机TripoSG容器.command`：历史实验与未来接入参考。

恢复时必须保持 `generate_3d.py` 的外部契约不变：

```text
--combo <衣_配> --task-id <id> --out-dir <目录>
成功输出：✅ Generated: <path>
产物：model.stl + bundle.zip
```

开发和演示应优先使用 mock 或预制缓存，只有明确需要时才接通真实模型服务。

## 运行产物与安全

- `work/` 是 Git 忽略的任务状态、STL 和 ZIP 缓存；确认无进行中的任务后可本地清理，不能提交。
- `.oss.json`、`.meshy_key`、Bambu 凭据、OpenClaw 配置和所有 API Key 都属于机器本地状态，不应进入仓库。
