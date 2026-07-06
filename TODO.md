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
- `GET  /api/download/{id}` → 发 bundle.zip（模型 model.stl + 生成时用的正视图 front.*，一起打包）
- `GET  /api/qr/{id}` → 返回二维码 PNG（编码下载链接，指向 bundle.zip）
- `GET  /api/gateway-token` → 读本机 OpenClaw 配置返回 gateway token（前端动态取，不写死）
- `WS /ws/gateway` → 浏览器↔OpenClaw Gateway 透明代理；`WS /ws/task/{id}` → 状态推送
- 页面通过路由/静态挂载提供；入口 `/` → `select.html`

核心文件：
| 文件 | 职责 |
|---|---|
| `generate_3d.py` | **升维适配器（可插拔）**。`--combo 3_2`（衣3+配2）→ 取合成图 → Meshy multi-image → 下 STL → 等比缩到 ~10cm → 打包成 `bundle.zip`（model.stl + 源正视图 front.*）→ 上传 OSS（若配置）。`--task-id` 把进度写进 `task_state`。`--mock` 零额度出占位立方体。`presets/<combo>.stl` 命中则复用（零额度）。`--image <png>` 单图直测。未来换模型只改内部 `_meshy_generate`。 |
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
- **下载内容改为 bundle.zip**：`model.stl` + 生成时喂给模型的正视图 `front.*` 一起打包，`/api/download`、`/api/qr`、OSS 上传均已改为发/传这个 zip（不再是裸 STL）。已用 mock 验证打包逻辑正确。
- **一体机 MetaX C500 环境探测 + TripoSG 端到端跑通**（真实推理成功，见第 8 节），按用户指示暂停在此、不继续推进。

## 5. 待办（TODO）

1. **真 Meshy 全流程验证（当前重点）**：`GEN_USE_MOCK` 已改回 `false`，需从换装 UI 完整走一遍，确认经 Agent 真调 Meshy 出 bundle.zip（模型+正视图）+ 二维码。（`.meshy_key` 已配好；⚠️ 耗额度，只跑 1~2 次）
2. **重新完整测试打印半**：确认唤醒经典（打印）路径走通（本次会话决定先测这个/或先测 Meshy，二选一，具体以当次沟通为准）。
3. **预烤缓存**：对要展示的搭配逐个跑 `generate_3d.py` 生成 bundle 存入 `presets/`，现场走缓存零额度。
4. **修 select.html 右半门面图**：现引用 `/ips/1.png、2.png、3.png`——文件不存在，且 `/ips` 路径未被后端服务。需放到 `static/ips/` 并把 `src` 改成 `static/ips/N.png`（或对齐 master 的 select.html 看是否已修）。
5. **前端页面对齐 master**：`select.html / preview_diy.html / takeaway.html` 目前是 updata 版 + 我们接线；master 整合后可能有更新，需对齐（`customize.html` 已是 master 7×7 版 + 接线）。
6. **一体机接入**：暂停中，见第 8 节"下一步"。换模型只改 `generate_3d.py` 内部升维函数，其余不动。

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

## 8. 一体机接入（本地升维模型）现状（2026-07-06）

**结论先行：TripoSG 在这台 MetaX C500 一体机上已跑通端到端真实推理，验证成功。** 目前**按用户指示暂不继续推进/不碰一体机**，生成半测试转回用 Meshy（真实云端），一体机保持现状待命。

### 硬件与网络
- 一体机：**MetaX C500**（沐曦国产卡，非 NVIDIA），64GB 显存，Ubuntu 22.04.5，内核 5.19。
- 连接方式：USB 转网口适配器 + 网线，Mac↔一体机点对点直连。**Mac 侧** `USB 10/100 LAN 2` 静态 IP `192.168.100.1/24`；**一体机侧**网卡 `enx0c3d5e61cd09` 静态 IP `192.168.100.2/24`（`sudo ip addr add ...`，非持久化，重启会丢，需要的话应写入 netplan/systemd-networkd 配置）。延迟 <1ms。
- 登录：`ssh user@192.168.100.2`，密码见本机记录（不写入仓库）。
- **一体机内置网口（`eno1`, 10.6.8.219/24）虽有网关但访问不了外网**（隔离内网，ping 公网 IP 100% 丢包）——所有软件/权重必须现在 Mac 上下载，再 scp 传过去。

### 环境验证结果
- MACA 驱动/SDK **完整安装**（版本 3.7.2.0），编译器 `mxcc` 正常（`/opt/maca-3.7.2/mxgpu_llvm/bin/mxcc`）。
- 本机已有两个现成 Docker 镜像（之前工程师跑 LLM 推理留下的）：
  - `cr.metax-tech.com/public-ai-release/maca/sglang:0.5.10-maca.ai3.7.1.12-torch2.8-py310-ubuntu22.04-amd64`（用的这个）
  - `cr.metax-tech.com/public-ai-release/maca/vllm-metax:0.20.0-maca.ai3.7.0.107-torch2.8-py312-ubuntu22.04-amd64`
  - 镜像内 torch 装在 `/opt/conda/bin/python`（不是默认 `python3`，容器默认 PATH 是系统 python，没有 torch，需显式用 conda 那个）。
  - **真实 GPU 计算验证通过**：`torch 2.8.0+metax3.7.1.4`，`torch.cuda.is_available()=True`，矩阵乘法在 `MetaX C500` 上真实跑通。

### TripoSG 端到端跑通记录
- 持久容器 `triposg-dev`（`docker run -d --name triposg-dev -v /home/user/triposg_transfer:/workspace ... sleep infinity`，未加 `--rm`，装好的东西不会因退出丢失）。
- 依赖来源：Mac 下载 55 个 pip wheel（**排除 torch/torchvision/numpy**，避免覆盖容器已验证版本）+ TripoSG 源码 + 两个 HF 权重仓库（`VAST-AI/TripoSG` 7.7GB、`briaai/RMBG-1.4` 803MB）+ `diso` 源码包，一起打包 7.8GB tar.gz，`scp` 传输，MD5 校验后解压。
- **踩过的坑与解法**：
  - `opencv-python` 最新版要求 `numpy>=2`，与容器已有 `numpy 1.26.4` 冲突 → 换成 `opencv-python==4.9.0.80`（要求 `numpy>=1.21.2`，兼容）。
  - `diso`（Differentiable Dual Marching Cubes，网格提取用的自定义 CUDA 扩展）**用 MACA 的 `mxcc` 直接编译成功**——这是最大的风险项，结果比预期顺利，无需 skimage 备用方案。
  - `diffusers`（任何版本）都 import 已被新版 `transformers`(5.x) 移除的 `FLAX_WEIGHTS_NAME` 常量 → 在推理脚本里 monkeypatch 补一个占位值，不降级 `transformers`。
  - 降级 `transformers` 到 4.x 又会跟容器自带的 `huggingface-hub 1.17.0`（新版）冲突（4.x 要求 `hub<1.0`）→ 索性不降级，保留新版 `transformers`，靠上面的 monkeypatch 解决。
  - `transformers` 新版要求 `safetensors>=0.8.0`，容器原有 `0.7.0` → 升级到 `0.8.0`（这个安全，不像 numpy/torch 那样有 ABI 风险）。
- **真实推理结果**：用项目里的换装合成图（`static/xixi_diy/1_cloth_o1.png`）测试，30 步扩散推理 + diso 网格提取，产出 **607,964 顶点、1,215,888 面**的真实网格，导出 `.glb`（21MB），已拉回 Mac 桌面查看。

### 下一步（用户明确表示现在不做，按下暂停，等以后再启动）
- 把 `generate_3d.py` 的 `_meshy_generate` 换成"SSH 到一体机 `triposg-dev` 容器跑 TripoSG → 取回 STL"，对外契约不变。
- 一体机上的静态 IP 配置需要持久化（重启会丢）。
- 评估是否需要更高贴图质量（Hunyuan3D-2.1，见下方风险表，仅 shape 阶段风险较低，texture 阶段未验证）。
- 之前的模型选型评估表仍然有效：

| 模型 | 依赖 | MetaX 风险 | 结论 |
|---|---|---|---|
| **TripoSG** | 纯 PyTorch/Diffusers，`pip install` 即可 | 🟢 最低 | **已验证跑通**，见上 |
| Hunyuan3D-2.1 | shape 阶段纯 Diffusers；texture 阶段自定义 CUDA 光栅化扩展 | 🟡 中等 | 未测试，若要更高贴图质量可评估 |
| TRELLIS | 需编译 7 个 CUDA 扩展，含 NVIDIA 自家库 kaolin | 🔴 最高 | 不考虑 |

许可证核实：Hunyuan3D-2.1 商用限制是月活>100万才需授权（展会 demo 不受影响），但不适用于欧盟/英国/韩国。

## 9. 打印侧接入清单（2026-07-06 调研，明天开工直接照做）

目标：把 master 分支的"唤醒经典"（打印半）接进 macos 分支。已对比 master/updata 与我们本地差异，逐项标注是否有写死路径需要改。**不要盲目整体覆盖文件——main.py/static/prompt.js 我们这边有自己的改动，需要合并而不是覆盖。**

### ✅ 已经一致，直接忽略
- `monitor_bridge.py`、`bambu-studio-ai/` skill 目录——和 master 逐字节相同，不用动。

### ✅ 纯数据/纯前端，可以直接拿 master 版覆盖（无写死路径）
- `ips/list.json`：master 已是真实数据（云栖懒猫→云朵小猫.gcode.3mf、弹力萌猫→弹簧小猫.gcode.3mf、喵星指环→戒指小猫.gcode.3mf、端坐奶猫→CatKeychain.gcode.3mf），我们这边还是旧占位（costume_1/2/painter）。**直接拿 master 版覆盖。**
- `templates/select_classic.html`、`preview_classic.html`、`printing_classic.html`、`finish_classic.html`、`index.html`、`print.html`、`printing.html`、`finish.html`：逐一 grep 过 `C:\`、`/Users/`、IP 地址，**全部 0 命中**，纯前端调相对路径 API，可以直接复制进来，不用改。

### ⚠️ 需要手动合并/重写（路径 + 架构都要动，不能简单复制）

**`static/prompt.js`**——master 这边不只是路径不同，是做了一次真正的架构升级，务必按新逻辑重写，不要只套用旧模板改改路径：
1. 函数签名变了：`buildPrompt(costume, taskId)` → `buildPrintPrompt(modelName, taskId, modelFile)`（`printing_classic.html` 已按新签名调用，见其第160行 `buildPrintPrompt(modelName, task_id, modelFile)`）。
2. 打印形象数据不再写死在 prompt.js 里的 COSTUMES 数组，改成前端从 `/api/list-ips`（读 `ips/list.json`）动态拉取，`select_classic.html`/`preview_classic.html` 负责把 modelName/modelFile 一路传到 printing_classic.html。
3. **监控方式改成非阻塞后台**（这是真正的改进，解决了我们早前担心的"Agent 长阻塞命令超时"风险）：master 用 PowerShell 的 `Start-Process -NoNewWindow python -ArgumentList ...` 把 `monitor_bridge.py --interval 15` 丢到后台立即返回，Agent 不等打印完成就继续往下走，报"监控已就位"就收尾；真正的 done/failed 由 monitor_bridge.py 自己后台跑完后写 task_state（monitor_bridge.py 本身已确认和 master 一致，自己就有这个逻辑，不用改它）。**移植到 Mac 时 `Start-Process` 要换成 bash 的 `nohup ... > /tmp/xxx.log 2>&1 & disown` 达到同样的"后台启动、立即返回"效果。**
4. 写死的路径/IP 要换成我们自己的（不是抄 master 的）：
   - `WORK_DIR`/`SKILLS_DIR`/`STOCK_DIR`：master 是 `C:\Users\i26293\Desktop\ip-print-web...`（同事 Windows 路径），换成我们的 `/Users/hefei/Desktop/MX_intern/OC3D`（我们自己 `static/prompt.js` 现有版本已经是这个，可以参考）。
   - `PRINTER_IP`：master 是 `10.238.235.64`（同事的网络环境），**不要用这个**，换成我们实测过的 `172.20.10.6`。
   - bash 语法（`export BAMBU_MODE=...`）而不是 PowerShell（`$env:BAMBU_MODE = ...`），我们现有版本已经是 bash，可参考。

**`main.py`**——好消息：合并工作量比想象中小。
- master 版 main.py（227 行，比我们的 383 行少）**完全没有** `/api/print`、`bambu.py` 调用、`discover_printer` 逻辑——他们把"实际发送打印指令"这个动作也挪到了 Agent 直接执行（和我们 `generate_3d.py` 由 Agent 直接跑是同一种模式），不是后端 subprocess 调用。
- master 用的是逐页显式路由（`@app.get("/select_classic.html")` 这种，每个页面一条），我们用的是 `StaticFiles(directory=TEMPLATES, html=True)` 通配挂载——我们的挂载方式本来就会自动服务任何丢进 `templates/` 的 html 文件，**大概率不需要新增任何路由**，只要把 classic 页面文件复制进 `templates/` 目录就会自动生效。
- `/api/list-ips` 我们已经有，语义应该兼容，复制 `ips/list.json` 后验证一下返回格式对不对即可。
- 我们自己在 main.py 加的 `/api/qr`、`/api/download`（bundle.zip）、`/api/gateway-token`、no-cache 中间件都要保留，**不要用 master 版覆盖 main.py**，只需确认 classic 页面用到的路由我们都已支持。

### 明天开工建议顺序
1. `ips/list.json` 直接覆盖成 master 版（纯数据，无风险）。
2. 四个 classic 页面 + `index.html`/`print.html`/`printing.html`/`finish.html` 直接复制进 `templates/`（无写死路径，验证完自动被 StaticFiles 挂载服务）。
3. 重写 `static/prompt.js`：采纳新架构（动态数据 + `Start-Process`→`nohup`后台监控），路径/IP 换成我们自己的（不要抄 master 的 Windows 路径和同事的打印机 IP）。
4. 跑一遍验证：`select.html` 左半"唤醒经典" → 选形象 → 打印 → 后台监控非阻塞、能正确收到 done/failed。
5. 检查 `main.py` 是否有遗漏路由（大概率不需要新增）。
