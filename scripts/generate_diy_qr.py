#!/usr/bin/env python3
"""Generate static PNG QR assets for the DIY package downloads.

Usage:
  python3 -m pip install "qrcode[pil]"
  python3 scripts/generate_diy_qr.py \
    --entry '0_0=https://metax-waic-3d.oss-cn-shanghai.aliyuncs.com/METAX_3D_0047853.zip'

Repeat --entry once for each confirmed OSS object.  The generated PNG files are
served locally by the demo, so the QR display has no runtime CDN dependency.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


COMBO_RE = re.compile(r"^[0-5]_[0-5]$")
DEFAULT_OUT_DIR = Path("static/qr")


def parse_entry(value: str) -> tuple[str, str]:
    combo, separator, url = value.partition("=")
    if not separator or not COMBO_RE.fullmatch(combo) or not url.startswith("https://"):
        raise argparse.ArgumentTypeError(
            "格式应为 0_0=https://<公开 OSS 下载地址>（衣/配编号均为 0-5）"
        )
    return combo, url


def load_manifest(path: Path) -> list[tuple[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise argparse.ArgumentTypeError(f"无法读取映射文件 {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("映射文件必须是 {\"衣_配\": \"https://...\"} 对象")
    return [parse_entry(f"{combo}={url}") for combo, url in payload.items()]


def verify_download(combo: str, url: str) -> None:
    request = Request(url, method="HEAD")
    context = ssl.create_default_context()
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        with urlopen(request, timeout=15, context=context) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            content_type = response.headers.get_content_type()
            if content_type != "application/zip":
                raise RuntimeError(f"Content-Type 为 {content_type}，不是 application/zip")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 DIY 下载二维码 PNG")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--entry",
        action="append",
        type=parse_entry,
        metavar="COMBO=URL",
        help="搭配编号及对应的固定公开下载 URL；可重复传入",
    )
    source.add_argument(
        "--manifest",
        type=Path,
        help="JSON 映射文件，格式为 {\"衣_配\": \"固定公开下载 URL\"}",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="生成前逐个验证 URL 返回 200 和 application/zip",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"输出目录（默认：{DEFAULT_OUT_DIR}）",
    )
    args = parser.parse_args()

    try:
        import qrcode
        from qrcode.image.pil import PilImage
    except ImportError:
        print("缺少 qrcode/Pillow：请先运行 python3 -m pip install \"qrcode[pil]\"", file=sys.stderr)
        return 1

    entries = args.entry if args.entry else load_manifest(args.manifest)
    seen: set[str] = set()
    for combo, _ in entries:
        if combo in seen:
            print(f"重复的搭配编号：{combo}", file=sys.stderr)
            return 2
        seen.add(combo)

    if args.verify:
        failed = False
        for combo, url in entries:
            try:
                verify_download(combo, url)
                print(f"已验证 {combo}: {url}")
            except RuntimeError as exc:
                print(f"无法下载 {combo}: {exc}", file=sys.stderr)
                failed = True
        if failed:
            return 3

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for combo, url in entries:
        code = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=16,
            border=4,
            image_factory=PilImage,
        )
        code.add_data(url)
        code.make(fit=True)
        output = args.out_dir / f"{combo}.png"
        code.make_image(fill_color="black", back_color="white").save(output)
        print(f"生成 {output}: {url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
