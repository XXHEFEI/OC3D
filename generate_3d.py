"""
generate_3d.py — 换装升维适配器（占位/跑通阶段：Meshy 后端，可插拔）。

对外契约固定，内部可换模型（Meshy → 以后本地开源模型如 TRELLIS/Hunyuan3D，
跑在一体机上），提示词/前端/后端不动：

  python3 generate_3d.py --combo 3_2 --task-id <tid> --out-dir work/<tid> [--mock]
  或快速直测单图： python3 generate_3d.py --image <png> --out-dir <dir>

  → 产出 <out-dir>/model.stl；成功打印 "✅ Generated: <path>"，失败 "❌ ..." 非零退出。

流程：combo → 预渲染合成图（static/xixi_diy/{衣}_cloth_o{配}.png，直接当单图）→ 升维 → STL。
（合成图由前端预渲染，故不再运行时叠图层，compose_views.py 已弃用。）

进度：给了 --task-id 就把升维进度写进 work/<tid>_state.json（前端轮询 /api/status 显示进度条）。
      最终 done 状态由生成提示词负责写（与打印半一致）。

额度保护（Meshy 测试额度很少）：
  1. --mock / 环境变量 MESHY_MOCK=1 → 不调 API，用 trimesh 生成占位 STL（开发期一律用，零额度）。
  2. 缓存：presets/<combo>.stl 存在则直接复用，不调 API（演示前预烤，现场零额度）。
  3. 只有 mock 关闭且无缓存时才真调 Meshy。

Meshy multi-image-to-3D：1~4 张图 → 默认导出 STL。API key 只从 MESHY_API_KEY 或 .meshy_key 读，绝不进前端。
"""

import argparse
import base64
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)  # 便于 import task_state
PRESETS_DIR = os.path.join(BASE, "presets")
MESHY_BASE = "https://api.meshy.ai/openapi/v1"


def _fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)


# ─── 搭配解析 ───────────────────────────────────────────────
def _load_combos():
    with open(os.path.join(BASE, "combos.json"), encoding="utf-8") as f:
        return json.load(f)


def _composite_path(combo_id):
    """combo '3_2' → 预渲染合成图绝对路径，并校验存在。"""
    cfg = _load_combos()
    try:
        cloth, ornament = combo_id.split("_", 1)
        int(cloth); int(ornament)
    except ValueError:
        _fail(f"非法 combo id: {combo_id!r}（应形如 3_2 = 衣3+配2）")
    rel = os.path.join(cfg["composite_dir"],
                       cfg["composite_pattern"].format(cloth=cloth, ornament=ornament))
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        _fail(f"该搭配无预渲染合成图（前端应置灰）：{rel}")
    return path


# ─── 进度回传 ───────────────────────────────────────────────
def _progress(task_id, pct, msg):
    """给了 task_id 就把进度写进 task_state（前端轮询可见）；否则静默。"""
    if not task_id:
        return
    try:
        import task_state
        task_state.set_status(task_id, "running", step="generating",
                              progress=int(pct), message=msg)
    except Exception as e:
        print(f"  ⚠️ 进度写入失败（忽略）: {e}")


# ─── STL 处理 ───────────────────────────────────────────────
def _mock_stl(out_path):
    """生成一个有效的占位 STL（立方体），不调任何 API。"""
    try:
        import trimesh
        trimesh.creation.box(extents=(20, 20, 20)).export(out_path)
    except Exception as e:
        with open(out_path, "w") as f:
            f.write("solid placeholder\nendsolid placeholder\n")
        print(f"  (trimesh 不可用，写了最简占位 STL: {e})")
    print(f"  [mock] 占位 STL: {out_path}")


def _normalize_size(stl_path, target_mm):
    """等比缩放到最长边 ≈ target_mm（站姿模型最长边即高度）。就地重写 STL。"""
    try:
        import trimesh
        m = trimesh.load(stl_path)
        longest = float(max(m.extents)) if len(m.extents) else 0.0
        if longest <= 0:
            return
        scale = target_mm / longest
        m.apply_scale(scale)
        m.export(stl_path)
        print(f"  已缩放: 最长边 {longest:.0f} → {target_mm}mm (scale {scale:.4f})")
    except Exception as e:
        print(f"  ⚠️ 缩放跳过: {e}")


def _oss_upload(stl_path, task_id):
    """若配置了 .oss.json，把 STL 上传到阿里云 OSS，返回可公网下载的预签名 URL；
    否则返回 None（回退局域网模式）。凭据只从 .oss.json（gitignored）读，不进仓库。"""
    cfg_path = os.path.join(BASE, ".oss.json")
    if not os.path.exists(cfg_path):
        return None
    try:
        import json as _j
        with open(cfg_path, encoding="utf-8") as f:
            c = _j.load(f)
        if not c.get("access_key_id") or c["access_key_id"].startswith("填"):
            print("  ⚠️ .oss.json 未填 AccessKey，跳过云上传")
            return None
        import oss2
        auth = oss2.Auth(c["access_key_id"], c["access_key_secret"])
        bucket = oss2.Bucket(auth, "https://" + c["endpoint"], c["bucket"])
        key = f"models/{task_id or os.path.basename(os.path.dirname(stl_path))}.stl"
        print(f"  ☁️ 上传 OSS: {key} ...")
        bucket.put_object_from_file(key, stl_path)
        expire = int(c.get("url_expire_days", 7)) * 86400
        # 预签名 GET URL（bucket 保持私有，链接带时限）；slashes_safe 让 URL 直接可用
        url = bucket.sign_url("GET", key, expire, slash_safe=True)
        print(f"  ☁️ OSS 链接（{c.get('url_expire_days',7)}天有效）: {url}")
        return url
    except Exception as e:
        print(f"  ⚠️ OSS 上传失败（回退局域网）: {e}")
        return None


def _finalize(out_stl, target_mm, task_id=None):
    _normalize_size(out_stl, target_mm)
    oss_url = _oss_upload(out_stl, task_id)
    if oss_url and task_id:
        # 写进 task_state，供 /api/qr、/api/download 用（set_status 合并保留）
        try:
            import task_state
            task_state.set_status(task_id, "running", step="generating",
                                  progress=99, message="已上传云端", oss_url=oss_url)
        except Exception as e:
            print(f"  ⚠️ 写 oss_url 失败: {e}")
    print(f"✅ Generated: {out_stl}")


# ─── Meshy 升维 ─────────────────────────────────────────────
def _data_uri(png_path):
    with open(png_path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def _load_key():
    """Meshy API key：优先环境变量 MESHY_API_KEY，否则读 .meshy_key（已 gitignore）。"""
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if key:
        return key
    kf = os.path.join(BASE, ".meshy_key")
    if os.path.exists(kf):
        with open(kf, encoding="utf-8") as f:
            return f.read().strip()
    _fail("缺少 API key：设 MESHY_API_KEY 或写进 OC3D/.meshy_key（开发请加 --mock）")


def _meshy_generate(image_paths, out_path, task_id=None):
    """真调 Meshy multi-image-to-3D，下 STL 到 out_path，途中回传进度。"""
    import requests
    api_key = _load_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    image_urls = [_data_uri(p) for p in image_paths]

    payload = {"image_urls": image_urls, "should_texture": True,
               "target_formats": ["stl", "glb"]}
    r = requests.post(f"{MESHY_BASE}/multi-image-to-3d", headers=headers,
                      json=payload, timeout=60)
    if r.status_code not in (200, 201, 202):
        _fail(f"Meshy 建任务失败 HTTP {r.status_code}: {r.text[:300]}")
    meshy_id = r.json().get("result") or r.json().get("id")
    if not meshy_id:
        _fail(f"Meshy 未返回 task id: {r.text[:300]}")
    print(f"  Meshy task: {meshy_id}")
    _progress(task_id, 10, "升维生成中 10%")

    deadline = time.time() + 600
    stl_url = None
    while time.time() < deadline:
        time.sleep(8)
        rs = requests.get(f"{MESHY_BASE}/multi-image-to-3d/{meshy_id}",
                          headers=headers, timeout=30)
        if rs.status_code != 200:
            print(f"  轮询 HTTP {rs.status_code}，重试中…")
            continue
        data = rs.json()
        status = data.get("status")
        prog = data.get("progress", 0)
        print(f"  Meshy {status} {prog}%")
        # 把 Meshy 的 0~100 映射到 10~95，留头尾给下载/收尾
        _progress(task_id, 10 + int(prog) * 0.85, f"升维生成中 {prog}%")
        if status == "SUCCEEDED":
            stl_url = (data.get("model_urls") or {}).get("stl")
            break
        if status in ("FAILED", "CANCELED"):
            _fail(f"Meshy 任务 {status}: {json.dumps(data.get('task_error', {}))[:300]}")
    if not stl_url:
        _fail("Meshy 轮询超时或未返回 STL 链接")

    _progress(task_id, 96, "下载模型中…")
    dl = requests.get(stl_url, timeout=120)
    if dl.status_code != 200:
        _fail(f"下载 STL 失败 HTTP {dl.status_code}")
    with open(out_path, "wb") as f:
        f.write(dl.content)
    print(f"  已下载 STL: {out_path} ({len(dl.content)//1024} KB)")


# ─── 主流程 ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="换装升维：搭配合成图 → STL")
    ap.add_argument("--combo", help="搭配 id，形如 3_2（衣3+配2）")
    ap.add_argument("--image", help="单张图片路径，直接升维（快速验证用）")
    ap.add_argument("--task-id", dest="task_id", help="任务 id，用于把进度写进 task_state")
    ap.add_argument("--out-dir",
                    help="输出目录；不填默认 ~/Desktop/OC3D_generated/<combo或图名>")
    ap.add_argument("--mock", action="store_true", help="不调 Meshy，出占位 STL（零额度）")
    ap.add_argument("--max-mm", type=float, default=100.0,
                    help="等比缩放到最长边≈此毫米数（默认 100 = 约 10cm）")
    args = ap.parse_args()

    if not args.combo and not args.image:
        _fail("需要 --combo 或 --image 其一")

    if args.out_dir:
        out_dir = os.path.abspath(args.out_dir)
    else:
        name = args.combo or os.path.splitext(os.path.basename(os.path.abspath(args.image)))[0]
        out_dir = os.path.expanduser(os.path.join("~/Desktop/OC3D_generated", name))
    print(f"  输出目录: {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    out_stl = os.path.join(out_dir, "model.stl")
    mock = args.mock or os.environ.get("MESHY_MOCK") == "1"

    _progress(args.task_id, 5, "升维生成中…")

    # 缓存命中（按 combo）→ 零额度
    if args.combo:
        cached = os.path.join(PRESETS_DIR, f"{args.combo}.stl")
        if os.path.exists(cached):
            shutil.copyfile(cached, out_stl)
            print(f"  缓存命中: {cached}")
            _finalize(out_stl, args.max_mm, args.task_id)
            return

    # 确定输入图（combo → 预渲染合成图；或直接 --image）
    if args.image:
        img = os.path.abspath(args.image)
        if not os.path.exists(img):
            _fail(f"图片不存在: {img}")
    else:
        img = _composite_path(args.combo)

    if mock:
        _mock_stl(out_stl)
    else:
        _meshy_generate([img], out_stl, task_id=args.task_id)

    if not os.path.exists(out_stl):
        _fail("未产出 STL")
    _finalize(out_stl, args.max_mm, args.task_id)


if __name__ == "__main__":
    main()
