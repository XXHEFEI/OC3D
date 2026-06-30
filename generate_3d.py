"""
generate_3d.py — 换装升维适配器（占位/跑通阶段：Meshy 后端）。

对外契约固定，内部可换模型（Meshy → 以后精度更高的模型），提示词/前端/后端不动：
  python3 generate_3d.py --combo c3_a2 --out-dir work/<task_id> [--mock]
  → 产出 <out-dir>/model.stl，成功打印 "✅ Generated: <path>"，失败打印 "❌ ..." 非零退出。

流程: 解析搭配 → compose_views 合成三视图 → 升维 → 下 STL。

额度保护（Meshy 测试额度很少）:
  1. --mock / 环境变量 MESHY_MOCK=1 → 不调 API，用 trimesh 生成占位 STL（开发期一律用这个，零额度）。
  2. 缓存: 若 presets/<combo>.stl 已存在，直接复用，不调 API（演示前把预设烤一遍，现场零额度）。
  3. 只有 mock 关闭且无缓存时才真调 Meshy。

Meshy multi-image-to-3D: 1-4 张图（同物体不同角度）→ 默认导出 STL。
API key 只从环境变量 MESHY_API_KEY 读，绝不写进前端 prompt.js。
"""

import argparse
import base64
import json
import os
import shutil
import sys
import time

import compose_views

BASE = os.path.dirname(os.path.abspath(__file__))
PRESETS_DIR = os.path.join(BASE, "presets")
MESHY_BASE = "https://api.meshy.ai/openapi/v1"
VIEW_ORDER = ("front", "side", "back")


def _fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)


def _mock_stl(out_path):
    """生成一个有效的占位 STL（一个立方体），不调任何 API。"""
    try:
        import trimesh
        mesh = trimesh.creation.box(extents=(20, 20, 20))
        mesh.export(out_path)
    except Exception as e:  # trimesh 不可用时退化为最简 ASCII STL
        with open(out_path, "w") as f:
            f.write("solid placeholder\nendsolid placeholder\n")
        print(f"  (trimesh 不可用，写了最简占位 STL: {e})")
    print(f"  [mock] 占位 STL: {out_path}")


def _data_uri(png_path):
    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _load_key():
    """读 Meshy API key：优先环境变量 MESHY_API_KEY，否则读仓库内 .meshy_key 文件。
    .meshy_key 已被 .gitignore 忽略；key 不进聊天、不进仓库。"""
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if key:
        return key
    key_file = os.path.join(BASE, ".meshy_key")
    if os.path.exists(key_file):
        with open(key_file, encoding="utf-8") as f:
            return f.read().strip()
    _fail("缺少 API key：设 MESHY_API_KEY 环境变量，或把 key 写进 OC3D/.meshy_key（开发请加 --mock）")


def _meshy_generate(view_paths, out_path):
    """真调 Meshy multi-image-to-3D，下 STL 到 out_path。"""
    import requests

    api_key = _load_key()

    headers = {"Authorization": f"Bearer {api_key}"}
    image_urls = [_data_uri(view_paths[v]) for v in VIEW_ORDER if v in view_paths]

    # 1) 建任务
    payload = {
        "image_urls": image_urls,
        "should_texture": True,
        "target_formats": ["stl", "glb"],
    }
    r = requests.post(f"{MESHY_BASE}/multi-image-to-3d", headers=headers,
                      json=payload, timeout=60)
    if r.status_code not in (200, 201, 202):
        _fail(f"Meshy 建任务失败 HTTP {r.status_code}: {r.text[:300]}")
    task_id = r.json().get("result") or r.json().get("id")
    if not task_id:
        _fail(f"Meshy 未返回 task id: {r.text[:300]}")
    print(f"  Meshy task: {task_id}")

    # 2) 轮询
    deadline = time.time() + 600  # 最多等 10 分钟
    stl_url = None
    while time.time() < deadline:
        time.sleep(8)
        rs = requests.get(f"{MESHY_BASE}/multi-image-to-3d/{task_id}",
                          headers=headers, timeout=30)
        if rs.status_code != 200:
            print(f"  轮询 HTTP {rs.status_code}，重试中…")
            continue
        data = rs.json()
        status = data.get("status")
        prog = data.get("progress", 0)
        print(f"  Meshy {status} {prog}%")
        if status == "SUCCEEDED":
            stl_url = (data.get("model_urls") or {}).get("stl")
            break
        if status in ("FAILED", "CANCELED"):
            _fail(f"Meshy 任务 {status}: {json.dumps(data.get('task_error', {}))[:300]}")
    if not stl_url:
        _fail("Meshy 轮询超时或未返回 STL 链接")

    # 3) 下载 STL
    dl = requests.get(stl_url, timeout=120)
    if dl.status_code != 200:
        _fail(f"下载 STL 失败 HTTP {dl.status_code}")
    with open(out_path, "wb") as f:
        f.write(dl.content)
    print(f"  已下载 STL: {out_path} ({len(dl.content)//1024} KB)")


def main():
    ap = argparse.ArgumentParser(description="换装升维：搭配 → 三视图 → STL")
    ap.add_argument("--combo", help="搭配 id，形如 c3_a2（图层合成三视图升维）")
    ap.add_argument("--image", help="单张图片路径，直接升维（用于快速验证 Meshy）")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--mock", action="store_true",
                    help="不调 Meshy，生成占位 STL（开发用，零额度）")
    args = ap.parse_args()

    if not args.combo and not args.image:
        _fail("需要 --combo 或 --image 其一")

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_stl = os.path.join(out_dir, "model.stl")
    mock = args.mock or os.environ.get("MESHY_MOCK") == "1"

    # 单图模式：跳过搭配/合成/缓存，直接把这张图喂给 Meshy（最少 1 张即可）
    if args.image:
        img = os.path.abspath(args.image)
        if not os.path.exists(img):
            _fail(f"图片不存在: {img}")
        view_paths = {"front": img}
        if mock:
            _mock_stl(out_stl)
        else:
            _meshy_generate(view_paths, out_stl)
        if not os.path.exists(out_stl):
            _fail("未产出 STL")
        print(f"✅ Generated: {out_stl}")
        return

    # 缓存命中 → 零额度
    cached = os.path.join(PRESETS_DIR, f"{args.combo}.stl")
    if os.path.exists(cached):
        shutil.copyfile(cached, out_stl)
        print(f"  缓存命中: {cached}")
        print(f"✅ Generated: {out_stl}")
        return

    # 合成三视图
    try:
        view_paths = compose_views.compose(args.combo, os.path.join(out_dir, "views"))
    except Exception as e:
        _fail(f"合成三视图失败: {e}")

    # 升维
    if mock:
        _mock_stl(out_stl)
    else:
        _meshy_generate(view_paths, out_stl)

    if not os.path.exists(out_stl):
        _fail("未产出 STL")
    print(f"✅ Generated: {out_stl}")


if __name__ == "__main__":
    main()
