#!/bin/bash
# 双击运行：现场打印机换网络（IP 变了）或访问码被重置时，快速更新 static/prompt.js
# 里的 PRINTER_IP / ACCESS_CODE，不用手动改代码。
#
# 打印机上查看方式：触屏 → 设置 → 局域网/网络（看 IP），设置 → 访问码（看 Access Code）。
#
# 改完不需要重启后端服务——static/prompt.js 是每次请求都现读的静态文件，
# 浏览器刷新一下换装/打印页面即可生效。

PROJECT_DIR="/Users/hefei/Desktop/MX_intern/OC3D"
PROMPT_FILE="$PROJECT_DIR/static/prompt.js"

echo "===================================="
echo " 打印机连接信息更新器"
echo "===================================="
echo

if [ ! -f "$PROMPT_FILE" ]; then
  echo "❌ 找不到文件: $PROMPT_FILE"
  echo "按任意键关闭..."
  read -n 1
  exit 1
fi

CUR_IP=$(grep -oE "PRINTER_IP\s*=\s*'[^']*'" "$PROMPT_FILE" | sed -E "s/.*'([^']*)'/\1/")
CUR_CODE=$(grep -oE "ACCESS_CODE\s*=\s*'[^']*'" "$PROMPT_FILE" | sed -E "s/.*'([^']*)'/\1/")

echo "当前配置："
echo "  打印机 IP  : $CUR_IP"
echo "  访问码     : $CUR_CODE"
echo

read -p "新的打印机 IP [当前: $CUR_IP，回车不改]: " NEW_IP
read -p "新的访问码 Access Code [当前: $CUR_CODE，回车不改]: " NEW_CODE

if [ -z "$NEW_IP" ] && [ -z "$NEW_CODE" ]; then
  echo
  echo "都没填，未做任何修改。"
  echo "按任意键关闭..."
  read -n 1
  exit 0
fi

# 简单校验 IP 格式（四段数字），避免手滑填错整个页面就打不开了
if [ -n "$NEW_IP" ]; then
  if ! [[ "$NEW_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "❌ IP 格式不对，应形如 192.168.1.100，未做任何修改。"
    echo "按任意键关闭..."
    read -n 1
    exit 1
  fi
fi

cp "$PROMPT_FILE" "$PROMPT_FILE.bak"

python3 - "$PROMPT_FILE" "$NEW_IP" "$NEW_CODE" <<'PYEOF'
import re, sys
path, new_ip, new_code = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    content = f.read()

if new_ip:
    content = re.sub(r"(PRINTER_IP\s*=\s*)'[^']*'", lambda m: m.group(1) + f"'{new_ip}'", content)
if new_code:
    content = re.sub(r"(ACCESS_CODE\s*=\s*)'[^']*'", lambda m: m.group(1) + f"'{new_code}'", content)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
PYEOF

echo
echo "✅ 已更新（旧版本备份在 prompt.js.bak）："
grep -E "PRINTER_IP|ACCESS_CODE" "$PROMPT_FILE" | head -2
echo
echo "不需要重启服务，刷新一下浏览器页面即可生效。"
echo
echo "按任意键关闭这个窗口..."
read -n 1
