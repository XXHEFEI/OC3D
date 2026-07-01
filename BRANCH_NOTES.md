# macos 分支说明

**本分支（macos）只负责「3D 模型生成（换装升维）」这一半，基于 macOS 本地化开发。**

## 范围
- 基于上游 Windows 版本做了 macOS 本地化（路径 / shell / 打印机 IP 等）。
- 生成流程：换装选择 → 合成视图 → Meshy 升维 → STL（高度归一化 ~10cm）→ 二维码下载。
- 相关文件：
  - `generate_3d.py`（升维适配器，Meshy 后端，可插拔；`--mock`/`--image`/尺寸归一化）
  - `compose_views.py`（换装图层合成，当前仅正视图）
  - `combos.json`（6×4=24 套搭配）
  - `static/prompt.generate.js`（生成提示词 + 卡片）
  - `main.py` 的 `/api/download`（发 STL）、`/api/qr`（二维码）

## 不在本分支维护
- **3D 打印那一半**由另一位同事在 `master` 上负责。`master` 对打印半的改动（如删除 `/api/print`、`/api/download` 等）**暂不同步**进本分支，以免与生成半需要的下载/二维码端点反向冲突。

## 整合
- 「master 打印半 + macos 生成半」的最终整合合并留待后续统一进行（届时保留本分支的 `/api/download`、`/api/qr`）。
