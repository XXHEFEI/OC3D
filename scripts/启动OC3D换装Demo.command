#!/bin/bash
# 双击运行：启动 OpenClaw Gateway + OC3D 后端（换装升维 demo），并打开换装页。
# 用 8080 端口，与打印 demo(8000) 互不干扰。

OPENCLAW_BIN="/Users/hefei/Desktop/MX_intern/openclaw/bin/openclaw"
OPENCLAW_HOME_DIR="/Users/hefei/Desktop/openclaw-home"
PROJECT_DIR="/Users/hefei/Desktop/MX_intern/OC3D"
PORT=8080

# 让后端也能定位 OpenClaw 配置（/api/gateway-token 读它拿 token）
export OPENCLAW_HOME="$OPENCLAW_HOME_DIR"

echo "===================================="
echo " OC3D 换装升维 Demo 启动器 (端口 $PORT)"
echo "===================================="
echo

# ── 1. 启动 OpenClaw Gateway ──────────────────────────────
if lsof -i :18789 >/dev/null 2>&1; then
  echo "✅ Gateway 已经在运行（18789）"
else
  echo "🚀 启动 Gateway..."
  export OPENCLAW_HOME="$OPENCLAW_HOME_DIR"
  export MODEL_PACK_API_KEY=$(python3 -c "
import json
with open('$OPENCLAW_HOME_DIR/.openclaw/agents/main/agent/models.json') as f:
    print(json.load(f)['providers']['modelpack']['apiKey'])
")
  nohup "$OPENCLAW_BIN" gateway run > /tmp/openclaw-gateway.log 2>&1 &
  disown

  for i in $(seq 1 20); do
    if lsof -i :18789 >/dev/null 2>&1; then
      echo "✅ Gateway 启动成功"
      break
    fi
    sleep 1
  done

  if ! lsof -i :18789 >/dev/null 2>&1; then
    echo "❌ Gateway 启动失败，最后日志："
    tail -15 /tmp/openclaw-gateway.log
    echo
    echo "按任意键关闭窗口..."
    read -n 1
    exit 1
  fi
fi

# ── 2. 启动 OC3D 后端 ─────────────────────────────────────
if lsof -i :$PORT >/dev/null 2>&1; then
  echo "✅ 后端已经在运行（$PORT）"
else
  echo "🚀 启动 OC3D 后端..."
  cd "$PROJECT_DIR"
  # 绑 0.0.0.0，方便手机同 Wi-Fi 扫二维码；本机走 localhost
  nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT > /tmp/oc3d-web.log 2>&1 &
  disown
  sleep 2

  if ! lsof -i :$PORT >/dev/null 2>&1; then
    echo "❌ 后端启动失败，最后日志："
    tail -15 /tmp/oc3d-web.log
    echo
    echo "按任意键关闭窗口..."
    read -n 1
    exit 1
  fi
  echo "✅ 后端启动成功"
fi

# ── 3. 打开换装页 ─────────────────────────────────────────
echo
echo "🌐 打开 http://localhost:$PORT/customize.html ..."
open "http://localhost:$PORT/customize.html"

echo
echo "全部启动完成！服务在后台运行，关闭本窗口不影响它们。"
echo "流程：换装 → 封装 → 预览(真实进度) → 扫码带走。"
echo "提示：手机扫码需与本机同 Wi-Fi，并用本机局域网 IP 访问（非 localhost）。"
echo "彻底停止：运行 停止OC3D换装Demo.command"
echo
echo "按任意键关闭这个窗口..."
read -n 1
