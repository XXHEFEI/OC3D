# 一体机 / 本地升维模型接入 — 独立 TODO

> 本文件专供**新开的 Claude Code 窗口**接手一体机相关工作，不需要读完整的 `TODO.md`
> （那份是整个 OC3D 项目说明，含打印半/换装半，与本任务无关的内容太多）。
> 如需项目整体背景，再去看 `TODO.md`；一体机专项工作看这份就够。

## 目标（这次任务要做的事）

把 `generate_3d.py`（在 `/Users/hefei/Desktop/MX_intern/OC3D/generate_3d.py`）里
负责"升维"的部分，从现在的 **Meshy 云 API** 换成 **SSH 到一体机、在已经配好的
Docker 容器里跑 TripoSG**，得到 STL 后传回来。

**对外契约不能变**（前端、提示词、后端都依赖这个契约，不要动它们）：
```
python3 generate_3d.py --combo 3_2 --task-id <tid> --out-dir work/<tid> [--mock]
→ 产出 <out-dir>/model.stl + bundle.zip
→ 成功打印 "✅ Generated: <path>"，失败打印 "❌ ..." 非零退出
```
`_normalize_size`（缩到 10cm）、`_make_bundle`（打包正视图）、`_oss_upload`
这些下游逻辑都不用动——只需要把 `_meshy_generate` 换掉/新增一个本地推理函数，
其他都复用现有代码。

## 现状：已验证可用的东西（不用重新折腾）

### 连接方式
- 网线直连，Mac 侧 `192.168.100.1/24`，一体机侧 `192.168.100.2/24`（已持久化进
  NetworkManager，一体机重启会自动恢复，不用手动 `ip addr add`）。
- **SSH 免密登录**：`ssh -i ~/.ssh/id_ed25519_aio user@192.168.100.2`
- **Docker 命令免密**（精确授权，只有这两条不用密码，其他 sudo 都要密码）：
  ```bash
  ssh -i ~/.ssh/id_ed25519_aio user@192.168.100.2 "sudo -n docker start triposg-dev"
  ssh -i ~/.ssh/id_ed25519_aio user@192.168.100.2 "sudo -n docker ps"
  ```
- 现在容器 `triposg-dev` 正在运行（已确认）。如果一体机重过启、容器没起来，
  双击桌面 `启动一体机TripoSG容器.command` 拉起（也在仓库 `scripts/` 目录）。

### 容器内环境（`triposg-dev`，镜像 `sglang:0.5.10-maca.ai3.7.1.12-torch2.8-py310`）
- **正确的 Python 解释器**：`/opt/conda/bin/python`（容器默认 `python3` 是另一个
  系统 Python，没装 torch，千万别用错）。
- torch 2.8（MetaX MACA 编译版）+ 全部 TripoSG 依赖 + `diso`（自定义 CUDA 网格
  提取扩展）**都已装好、已验证真实 GPU 推理成功**（用 MACA 的 `mxcc` 编译器编译
  diso 通过，不用改）。
- 挂载：宿主机 `/home/user/triposg_transfer` ↔ 容器内 `/workspace`（双向同步，
  scp 文件到宿主机这个目录，容器里立刻能看到）。
- TripoSG 源码在 `/workspace/TripoSG`，权重在 `/workspace/weights/TripoSG` 和
  `/workspace/weights/RMBG-1.4`（已下载好，不用重新下）。
- **已有一个测试脚本 `/workspace/run_test.py`**，可以直接参考/复用它的逻辑：
  ```python
  # 关键点：
  # 1. os.environ["HF_HUB_OFFLINE"] = "1"  # 一体机无外网，禁止联网检查
  # 2. monkeypatch transformers.utils.FLAX_WEIGHTS_NAME（新版 transformers 已移除
  #    这个常量，但 diffusers 还在 import 它，随便塞个占位字符串即可）
  # 3. BriaRMBG.from_pretrained("/workspace/weights/RMBG-1.4")
  # 4. TripoSGPipeline.from_pretrained("/workspace/weights/TripoSG")
  # 5. mesh.export(output_path) —— trimesh 原生支持导出 .stl，不用转 glb 再转
  ```
- 已实测跑通：用 `static/xixi_diy/1_cloth_o1.png` 当输入，30 步扩散推理 + diso
  提取，产出 607,964 顶点 / 1,215,888 面的真实网格，导出 .glb 21MB（本次可以直接
  改成导出 .stl）。

### 一体机联网情况（重要限制）
- 一体机**内置网口能联网但被隔离，连不了外网**（ping 公网 100% 丢包）。
- **所有新增的依赖/权重都得先在 Mac 上下载，再 scp 传过去**，不能指望在一体机上
  `pip install` 或 `huggingface_hub` 直接下载。当前跑通所需的东西已经都传过去了，
  除非要新增功能（比如换更高质量的模型）才需要再传。

### 已知环境坑（如果要重新搭一遍环境才用得上，现在环境已经装好不用管）
- `opencv-python` 最新版要求 `numpy>=2`，与容器已有 `numpy 1.26.4` 冲突 → 用了
  `opencv-python==4.9.0.80`（要求 `numpy>=1.21.2`，兼容）。
- 不要在容器里装/降级 `torch`、`torchvision`、`numpy`——容器自带的版本已验证可用，
  覆盖了可能连累到已经装好的东西。
- `transformers` 装最新版，靠 monkeypatch 解决 `FLAX_WEIGHTS_NAME` 缺失问题，不要
  尝试降级 `transformers`（会跟容器自带的新版 `huggingface-hub` 冲突）。

## 要做的具体工作

1. **写一个新函数** `_local_triposg_generate(image_path, out_path, task_id=None)`（放在
   `generate_3d.py` 里，参考现有 `_meshy_generate` 的函数签名和进度回传方式）：
   - 通过 `subprocess.run(["scp", ...])` 把 `image_path` 传到一体机
     `/home/user/triposg_transfer/inbox/<task_id>.png`（建议每个任务用 task_id
     建单独子目录，避免并发任务互相覆盖）。
   - 通过 `subprocess.run(["ssh", "-i", "~/.ssh/id_ed25519_aio", ...])` 在容器内跑推理
     （`docker exec triposg-dev /opt/conda/bin/python /workspace/run_inference.py ...`，
     可能需要先把 `run_test.py` 改造成一个更通用的、接受输入图路径和输出路径作为参数
     的脚本，传到 `/workspace/` 下）。
   - 通过 `scp` 把结果 `.stl` 拉回 Mac 本地的 `out_path`。
   - 全程用 `_progress(task_id, pct, msg)`（已有的函数）汇报进度，多个阶段大致给个
     百分比就行（比如：10% 传图，20% 开始推理，90% 推理完成/开始下载，100%完成）。
   - 出错处理：SSH/scp 失败、推理超时、容器不存在等情况都要 `_fail(...)` 清晰报错。

2. **在 `main()` 里加一个选择开关**，让 `--combo`/`--image` 走 Meshy 还是走本地模型
   可以配置（比如环境变量 `GEN_BACKEND=meshy`（默认，向后兼容）或 `GEN_BACKEND=local`），
   这样切换/回退都不用改代码，方便对比测试两条路线的效果。

3. **测试**：先用 `--image` 模式（跳过 combo 解析，直接给一张图）验证本地路径能跑通，
   再用 `--combo` 走完整流程，确认 bundle.zip、OSS 上传等下游逻辑不受影响。

4. **胡子悬空的老问题**（如果还没解决）：这是几何层面的问题，模型不管用哪个都一样，
   真正的修复思路是让美术把胡子在合成图里画成贴脸的浅浮雕/贴图，而不是分离的细线，
   跟这次换模型无关，不用在这次任务里处理。

## 约束（务必遵守）

- **Git 操作需要审核**：commit/push/merge 等任何 git 写操作，必须先跟用户确认再执行，
  不要自己 push。只读查询可以直接做。
- **这台一体机是团队共享的**：除了我们的 `triposg-dev`，上面还有另一个工程师的
  `metax-sglang-eval` 容器（已停止），**不要动它/删它**。也不要把 `user` 加进
  `docker` 组或做其他扩大权限范围的操作——现有的精确 sudoers 授权已经够用。
- **不要碰打印半/前端**：这次任务只改 `generate_3d.py`（和可能新增的一体机侧
  推理脚本），不涉及 `templates/`、`static/prompt.js`、`main.py` 的路由等。
- **额度/性能无关**：本地模型零额度，不用像 Meshy 那样省着测，可以多跑几次调试。
