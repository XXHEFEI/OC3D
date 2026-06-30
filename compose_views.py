"""
compose_views.py — 图层合成（换装方案 B）。

把基础曦曦的三视图（正/侧/后）与选中"衣服 + 配饰"的透明 PNG 图层逐视角叠加，
输出该搭配的三张合成三视图，供 generate_3d.py 喂给升维模型。

图层约定（见 combos.json）:
  layers/clothes/<clothes_id>/{front,side,back}.png
  layers/accessories/<accessory_id>/{front,side,back}.png
缺失的图层会被跳过（降级为仅基础视图），不报错——所以现在素材不全也能跑通链路。

可独立调用:
  python3 compose_views.py c3_a2 --out-dir /tmp/views
"""

import argparse
import json
import os

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
VIEWS = ("front", "side", "back")


def _load_combos():
    with open(os.path.join(BASE, "combos.json"), encoding="utf-8") as f:
        return json.load(f)


def parse_combo(combo_id, cfg):
    """combo_id 'c3_a2' -> (clothes_id, accessory_id)，校验存在。"""
    try:
        clothes_id, accessory_id = combo_id.split("_", 1)
    except ValueError:
        raise ValueError(f"非法 combo_id: {combo_id!r}（应形如 c3_a2）")
    clothes_ids = {c["id"] for c in cfg["clothes"]}
    accessory_ids = {a["id"] for a in cfg["accessories"]}
    if clothes_id not in clothes_ids:
        raise ValueError(f"未知衣服 id: {clothes_id}")
    if accessory_id not in accessory_ids:
        raise ValueError(f"未知配饰 id: {accessory_id}")
    return clothes_id, accessory_id


def _layer_path(cfg, kind, item_id, view):
    return os.path.join(BASE, cfg["layer_root"], kind, item_id, f"{view}.png")


def compose(combo_id, out_dir):
    """合成一套搭配的三视图，返回 {view: 输出路径}。"""
    cfg = _load_combos()
    clothes_id, accessory_id = parse_combo(combo_id, cfg)
    os.makedirs(out_dir, exist_ok=True)

    results = {}
    for view in VIEWS:
        base_rel = cfg["base_views"][view]
        base_path = os.path.join(BASE, base_rel)
        if not os.path.exists(base_path):
            raise FileNotFoundError(f"基础视图缺失: {base_path}")

        canvas = Image.open(base_path).convert("RGBA")

        # 依次叠加衣服、配饰图层（缺失则跳过 → 降级为仅基础视图）
        for kind, item_id in (("clothes", clothes_id), ("accessories", accessory_id)):
            lp = _layer_path(cfg, kind, item_id, view)
            if os.path.exists(lp):
                layer = Image.open(lp).convert("RGBA")
                if layer.size != canvas.size:
                    layer = layer.resize(canvas.size)
                canvas = Image.alpha_composite(canvas, layer)
            else:
                print(f"  ⚠️ 图层缺失，跳过: {os.path.relpath(lp, BASE)}")

        out_path = os.path.join(out_dir, f"{view}.png")
        canvas.convert("RGB").save(out_path)
        results[view] = out_path
        print(f"  合成 {view}: {out_path}")

    return results


def main():
    ap = argparse.ArgumentParser(description="合成换装三视图")
    ap.add_argument("combo_id", help="搭配 id，形如 c3_a2")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    paths = compose(args.combo_id, args.out_dir)
    print("✅ Composed:", ", ".join(paths.values()))


if __name__ == "__main__":
    main()
