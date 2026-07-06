#!/bin/bash
# 双击运行：停止 OC3D 后端（8080）。
# 注意：Gateway(18789) 与打印 demo 共用，默认一并停止；若打印 demo 还在用，
# 请把下面 STOP_GATEWAY 改成 0。

STOP_GATEWAY=1
PORT=8080

echo "停止 OC3D 后端 ($PORT)..."
BE_PID=$(lsof -ti :$PORT)
if [ -n "$BE_PID" ]; then
  kill $BE_PID && echo "✅ 已停止 (PID $BE_PID)"
else
  echo "（未在运行）"
fi

if [ "$STOP_GATEWAY" = "1" ]; then
  echo "停止 Gateway (18789)..."
  GW_PID=$(lsof -ti :18789)
  if [ -n "$GW_PID" ]; then
    kill $GW_PID && echo "✅ 已停止 (PID $GW_PID)"
  else
    echo "（未在运行）"
  fi
else
  echo "（按设置保留 Gateway 运行）"
fi

echo
echo "按任意键关闭这个窗口..."
read -n 1
