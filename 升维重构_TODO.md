# 升维侧重构 — 三视图输入 + 转台视频展示（独立 TODO）

> 本文件专供**新开的 Claude Code 窗口**接手"换装升维侧重构"，不用读完整的 `TODO.md`。
> 项目整体背景看 `TODO.md`；一体机本地模型看 `AIO_TODO.md`；本任务看这份就够。
> 相关文件：`generate_3d.py`、`compose_views.py`、`combos.json`、
> `templates/customize.html`、`templates/preview_diy.html`、`static/prompt.generate.js`、
> 已建好的转台工具 `static/turntable/render_turntable.py`。

## 为什么要重构（问题）

现在换装 DIY 的升维（2D→3D）效果不理想。**根因基本可以确定**：
`generate_3d.py` 只把**一张预渲染的正面合成图**
（`static/xixi_diy/{衣}_cloth_o{配}.png`）喂给 Meshy 的
`multi-image-to-3d`。单图重建先天弱——侧面和背面全靠模型脑补，所以出来的
STL 糊、结构错。Meshy 这个接口本来就是**为多图设计的**，我们却只给一张。

## 新想法（这次要做的事）

为每个换装形象（6×6 = 36 个搭配）准备**三视图（正/侧/后）**，再**生成一段
360° 旋转视频**来展示，视频可以**现场生成**或**预制**。

⚠️ **动手前必须先跟晖飞定这个岔路口**（它决定整套实现，别自己拍板）：

### 岔路 A：三视图 → 真 3D 重建 → 转台视频（推荐）
- 三视图喂给多图重建（Meshy `multi-image-to-3d` 传 3 张，或用一体机
  TripoSG，见 `AIO_TODO.md`），得到质量明显更好的 STL；
- "视频"= 用已经写好的 `static/turntable/render_turntable.py` 把这个 STL
  渲成 360° 转台帧序列（前端播放器已在 `preview_classic_test.html` 里验证过）。
- **好处**：可打印的 STL / 扫码带走这条价值链**保留**；最大化复用现有代码；
  很可能直接解决"效果不理想"（三图输入 >> 单图）。
- **预制** = 演示前把 36 个搭配的 STL + 转台帧全部烤好（现场零延迟、零 API 额度）；
  **现场生成** = 用户选完当场重建 + 渲染（新鲜但慢、且走 API 额度/一体机算力）。

### 岔路 B：三视图 → 纯视觉视频（不做真 3D）
- 不再产出可打印模型，直接用三视图做一段旋转/过渡视频（image-to-video 模型，
  或三张图之间做轨道插值）。
- **代价**：扔掉"扫码带走可打印模型"这个卖点；takeaway 改成下载视频/GIF。

**我的建议是岔路 A**：复用最多、保住可打印卖点、且最可能真正修好画质。
下面的"要做的具体工作"按岔路 A 写；如果最终选 B，第 2、3 步换成视频生成即可。

## 现状：可复用/可复活的东西（别重造）

- **`compose_views.py`（现已弃用，但本来就是干这个的）**：它设计上就是把基础
  曦曦三视图（`2D 三视图/{正,侧,后}视图.png`）叠加"衣服+配饰"的分视角透明图层，
  输出一套三张合成三视图。当初弃用只是因为改走了"预渲染单张正面合成图"。
  **这次正好把它复活**。图层约定见文件头：
  `layers/clothes/<id>/{front,side,back}.png`、`layers/accessories/<id>/{front,side,back}.png`。
- **`static/turntable/render_turntable.py`（这次刚写的，已跑通 4 个经典模型）**：
  输入 3mf/stl → 输出 360° 帧序列 PNG。岔路 A 的"视频"直接用它。
  已知坑都踩过了（只取单实例、场景变换矩阵要 apply、大网格分两段抽稀）。
- **转台前端播放器**：`templates/preview_classic_test.html` 里那套
  "自动旋转 + 拖动 + 帧序列切图"的 JS，可直接搬进 `preview_diy.html`。
- **`generate_3d.py` 的下游全不用动**：`_normalize_size`（缩到 10cm）、
  `_make_bundle`、`_oss_upload`、`_finalize`、进度回传、缓存都复用。
- **`_meshy_generate(image_paths, ...)` 已经收的是图片列表**，现在被
  `_meshy_generate([img], ...)` 只传一张——改成传三张几乎零成本。

## 要做的具体工作（按岔路 A）

1. **准备三视图素材**（二选一，跟晖飞确认走哪条）：
   - (a) **复活 `compose_views.py`**：需要补齐分视角透明图层
     （`layers/clothes/<id>/{front,side,back}.png` 等，现在 `layers/` 目录还不存在），
     运行时或预渲染时逐视角叠图；素材缺失能自动降级不报错。
   - (b) **直接预渲染 36×3 张合成三视图**（像现在的 36 张单图那样，但每个搭配出
     正/侧/后三张），命名扩展成 `{衣}_cloth_o{配}_{front|side|back}.png`。
   - 对应改 `combos.json` 的 `composite_pattern`（现在是 `{cloth}_cloth_o{ornament}.png`）。

2. **改 `generate_3d.py` 的输入**：把"取单张合成图"改成"取三张合成三视图"，
   组成 `[front, side, back]` 列表传给 `_meshy_generate`（或换成一体机 TripoSG
   的多图入口）。`_composite_path()` 改成返回三条路径。bundle 里的源图相应带上三视图。

3. **接转台视频**（预制或现场）：
   - **预制**：写个批处理脚本，对 36 个搭配跑完"三视图→STL→
     `render_turntable.py` 出帧"，产物放 `static/turntable_diy/<combo>/…`。
   - **现场**：在 `generate_3d.py` 出 STL 后追加一步转台渲染，把帧写进
     `work/<task_id>/turntable/`，前端轮询到就播放。
   - 把 `preview_classic_test.html` 的帧序列播放器搬进 `preview_diy.html`，
     替换现在那张静态合成图预览。

4. **takeaway 决策**：岔路 A 下保留 STL bundle 扫码带走不变；如果还想让用户带走
   转台视频/GIF，再在 `_make_bundle` 里加一份（可选）。

## 约束（务必遵守）

- **Git 操作需审核**：commit/push/merge 前必须先跟晖飞确认，不要自己 push；
  只读查询随意。
- **对外契约尽量稳**：`generate_3d.py` 的命令行签名
  （`--combo/--task-id/--out-dir/--mock`）和"✅ Generated / ❌ 失败非零退出"
  约定别乱改，前端/提示词/后端都依赖它。要扩展就加可选项，别改已有语义。
- **额度保护**：Meshy 测试额度很少，开发期一律 `--mock` 或用缓存/预制；
  真调 API 只在最终验证。岔路 A 选"预制"能彻底躲开现场额度问题。
- **不碰打印半**：本任务只动换装/升维侧，不涉及 `bambu*`、打印相关路由。
- **别动刚做完的经典转台**：`static/turntable/` 下 4 个经典模型的帧图是打印半
  预览在用的，重构 DIY 侧请另起目录（如 `static/turntable_diy/`），别覆盖。

## 待晖飞拍板的问题（新窗口开工前先问）

1. 走**岔路 A（真 3D + 转台视频，保住可打印）**还是**岔路 B（纯视频，放弃打印）**？
2. 视频**现场生成**还是**预制**？（现场=新鲜但慢/耗额度；预制=零延迟但选项固定）
3. 三视图素材从哪来：**分视角图层叠加**（复活 compose_views，要补图层美术）、
   **预渲染 36×3 合成图**，还是 **AI 生成三视图**？
4. 重建后端用 **Meshy 多图** 还是 **一体机 TripoSG**（见 `AIO_TODO.md`）？
5. takeaway 带走的是 **STL**、**视频/GIF**，还是**都要**？
