# DIY 下载二维码

每个 PNG 的文件名为搭配编号：`{衣}_{配}.png`。二维码内容是对应 ZIP 的固定公开下载 URL。

已上传或待验证的对象映射维护在 `manifest.json`。当前含完整 36 组（`0_0`～`5_5`）；未上传的搭配不会生成二维码。

生成命令：

```bash
python3 -m pip install "qrcode[pil]"
python3 scripts/generate_diy_qr.py \
  --manifest static/qr/manifest.json --verify
```

其余对象上传后，只需在 `manifest.json` 添加搭配编号与固定公开 URL，再重复运行命令。不要把临时签名 URL 写入二维码。
