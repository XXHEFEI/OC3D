# OC3D 魔法衣橱（换装升维）— 项目说明 & TODO（给 Codex）

> 本文件面向协助本项目的 AI（Codex）。先读完"约束"再动手。

## 1. 项目目标

曦曦 IP 形象的线下互动站，前端两条路径：
- **唤醒经典**：直达 3D 打印（选形象 → 发送打印机打印实物）。
- **魔法衣橱（本半负责）**：DIY 换装 → 把搭配升维成 3D 模型（.stl）→ 展示二维码，用户扫码把数字模型带走（**不打印**）。

升维由 OpenClaw Agent 调度执行；升维模型现在用 **Meshy 云 API**（占位/跑通用），未来换成**一体机上的本地开源模型**（型号未定，见"在等"）。

## 2. 仓库与分支（重要）

- GitLink：`https://gitlink.org.cn/xiao-ke/OC3D.git`，本地：`/Users/hefei/Desktop/MX_intern/OC3D`。
- 主干 `master`：同事维护，含**两半完整前端 + 真打印后端 + 落地页**；但其 DIY 半是**纯前端模拟**（无真实升维后端）。
- 工作分支 **`macos`（我们）：只负责"魔法衣橱/换装升维"这半的真实后端 + 接线**。
- **打印半归同事在 master，本分支不碰、也不合并回 master**（详见约束）。

## 3. 架构与关键文件

浏览器 → FastAPI（`main.py`）：
- `POST /api/generate {ip_id}` → 建任务，返回 task_id
- `GET  /api/status/{id}` → 任务状态（前端轮询进度）
- `GET  /api/download/{id}` → 发 STL 文件
- `GET  /api/qr/{id}` → 返回二维码 PNG（编码下载链接）
- `GET  /api/gateway-token` → 读本机 OpenClaw 配置返回 gateway token（前端动态取，不写死）
- `WS /ws/gateway` → 浏览器↔OpenClaw Gateway 透明代理；`WS /ws/task/{id}` → 状态推送
- 页面通过路由/静态挂载提供；入口 `/` → `select.html`

核心文件：
| 文件 | 职责 |
|---|---|
| `generate_3d.py` | **升维适配器（可插拔）**。`--combo 3_2`（衣3+配2）→ 取合成图 → Meshy multi-image → 下 STL → 等比缩到 ~10cm。`--task-id` 把进度写进 `task_state`。`--mock` 零额度出占位立方体。`presets/<combo>.stl` 命中则复用（零额度）。`--image <png>` 单图直测。未来换模型只改内部 `_meshy_generate`。 |
| `combos.json` | 搭配注册表，**7×7**（衣 0-6 × 配 0-6，0=经典原皮/卸下配饰）。合成图 `static/xixi_diy/{cloth}_cloth_o{ornament}.png`。 |
| `static/prompt.generate.js` | `buildGenPrompt(comboId, taskId)` 构造发给 Agent 的升维指令。`GEN_USE_MOCK` 开关（true=mock）。 |
| `static/gateway.js` | `GatewayChat` 类；连接时先 `fetch('/api/gateway-token')` 取 token。 |
| `templates/customize.html` | 换装页（7×7，已接线：连 gateway→建任务→发指令→跳预览）。 |
| `templates/preview_diy.html` | 预览页，轮询 `/api/status` 用真实进度驱动进度条，done→takeaway。 |
| `templates/takeaway.html` | 扫码页，二维码 `img.src=/api/qr/{task}`。 |
| `templates/select.html` | 双路枢纽（左=打印，右=换装）。 |
| `task_state.py` | 状态持久化 `work/{task_id}_state.json`。 |

**端到端流程**：customize 点"封装" → `/api/generate` 建 task → `gateway.sendMessage(buildGenPrompt(combo, task))` → Agent 跑 `generate_3d.py --combo X --task-id Y` → 脚本写进度 → preview_diy 轮询 `/api/status` → done → takeaway 显示 `/api/qr`。

**本地运行**：桌面 `启动OC3D换装Demo.command`（端口 8080），或手动：
```bash
openclaw gateway                                   # 终端1（18789）
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080   # 终端2
```

## 4. 已完成

- 全链路 **mock 跑通**：换装(7×7) → 封装 → OpenClaw 升维 → 预览真实进度 → 二维码。
- Meshy **真路单图验证过**（`--image` → 真 STL，已缩到 10cm）。
- 换装规模**对齐 master 到 7×7** + 搬入全套合成图素材。
- gateway token **动态取**（不写死进仓库）；连接时序 bug 已修。
- STL **高度归一化 ~10cm**。

## 5. 待办（TODO）

1. **真 Meshy 全流程验证**：把 `static/prompt.generate.js` 的 `GEN_USE_MOCK` 改 `false`，从换装 UI 完整走一遍，确认经 Agent 真调 Meshy 出 STL + 二维码。（`.meshy_key` 已配好；⚠️ 耗额度，见约束，只跑 1~2 次）
2. **预烤缓存**：对要展示的搭配逐个跑 `generate_3d.py` 生成 STL 存入 `presets/`，现场走缓存零额度。
3. **修 select.html 右半门面图**：现引用 `/ips/1.png、2.png、3.png`——文件不存在，且 `/ips` 路径未被后端服务。需放到 `static/ips/` 并把 `src` 改成 `static/ips/N.png`（或对齐 master 的 select.html 看是否已修）。
4. **前端页面对齐 master**：`select.html / preview_diy.html / takeaway.html` 目前是 updata 版 + 我们接线；master 整合后可能有更新，需对齐（`customize.html` 已是 master 7×7 版 + 接线）。
5. **换模型（未来）**：Meshy → 一体机本地开源模型（TRELLIS/Hunyuan3D 等），只改 `generate_3d.py` 内部升维函数，其余不动。

## 6. 在等什么

- **一体机到货**：现场跑本地升维模型（128GB VRAM，型号未定）→ 最终替掉 Meshy。
- **现场升维方案拍板**：继续 Meshy（需堆多个 key，Meshy 闭源不能自部署）vs 一体机跑开源模型（推荐，零额度离线）。
- **用户提供 select 右半门面图**（3 张）或确定用占位。

## 7. 约束（必须遵守）

- **Git 需审核**：任何 git 写操作（commit/push/merge/branch…）必须**先向用户说明、经同意再执行**；**绝不自动 push 或改动远端**。只读查询（status/log/diff）可直接做。
- **不合并进 master**：本分支只做生成半；打印半在 master 归同事，不强行合并。
- **不改前端 UI 设计**：只做功能接线（加 script/fetch/逻辑），不动布局、样式、视觉。
- **Meshy 额度很少**：开发一律用 `--mock`；真 Meshy 只在必要时少量跑。
- **密钥不进仓库**：`MESHY_API_KEY`、gateway token、`.meshy_key` 均已 gitignore；token 走 `/api/gateway-token` 动态取，`.meshy_key` 本地文件。
- **升维适配器保持可插拔**：换模型只动 `generate_3d.py` 内部，对外契约（`--combo/--task-id/--out-dir` + 输出 `✅ Generated:`）不变。

## 8. 一体机接入（本地升维模型）计划

现场用一体机（128GB VRAM，Linux）跑**本地开源升维模型**替掉 Meshy（零额度、离线）。

**连接**：Mac 无法上内网 → **网线直连一体机**（点对点）。设静态 IP（如 Mac `192.168.100.1/24`、一体机 `192.168.100.2/24`），`ssh 用户@192.168.100.2`。Mac 保留 Wi-Fi 上网 + 以太网连一体机，两者并行。

**步骤**（连通后）：
1. SSH 上一体机，确认环境：`nvidia-smi`（GPU/驱动/CUDA）、python/conda、磁盘空间、能否联网下权重。
2. 选并装开源图生 3D 模型（TRELLIS / Hunyuan3D / TripoSR），跑通"单图 → 3D（.stl/.glb）"。
   - ⚠️ 权重是 GB 级：一体机能联网就直接下；离线则在能上网的机器下好再 `scp` 过去。
3. 把 `generate_3d.py` 的 `_meshy_generate` 换成"SSH 到一体机跑本地模型 → 取回 STL"（对外契约不变，前端/提示词/后端都不动）。
4. 一体机模型对外接口约定：输入合成图（单图），输出 STL；`generate_3d.py` 负责 scp 图上去 + ssh 触发 + scp STL 回来。

**待定/在等**：一体机具体型号与系统、是否联网、SSH 凭据、最终选哪个开源模型。
