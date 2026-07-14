#!/usr/bin/env bash
# 一键：把一张图片传到一体机 → 容器内 TripoSG 升维 → 拉回 Mac 文件夹
# 用法:
#   ./aio_upscale.sh <图片文件> [输出文件夹] [目标面数]
# 例:
#   ./aio_upscale.sh ~/Desktop/testCat1.png                          # 默认不减面(完整网格,~60MB)
#   ./aio_upscale.sh ~/Desktop/cat.png ~/Desktop/triposg_out 100000  # 传面数才减面(~5MB)
# 不传第三个参数=不减面；传了才调用减面脚本。
#
# 说明：容器里的 docker exec 需要一体机 sudo 密码，脚本用 ssh -t 让你在本地
# 终端输入一次（不修改一体机权限）。SSH 免密只免登录，不免 sudo，属正常。
set -euo pipefail

# ---------- 固定配置（一体机环境，已验证）----------
KEY="$HOME/.ssh/id_ed25519_aio"
AIO="user@192.168.100.2"
REMOTE_BASE="/home/user/triposg_transfer"   # 宿主机目录 ↔ 容器 /workspace
CONTAINER="triposg-dev"
PYTHON="/opt/conda/bin/python"              # 容器里正确的解释器（别用 python3）
SCRIPT_FULL="/workspace/run_test.py"        # 原始脚本：完整网格，不减面
SCRIPT_LITE="/workspace/run_test_lite.py"   # 带减面脚本：减到指定面数

# ---------- 参数 ----------
IMG="${1:-}"
OUT_DIR="${2:-$HOME/Desktop/triposg_out}"
FACES="${3:-}"                              # 留空=不减面；给数值才减面 (20万≈10MB,10万≈5MB,5万≈2.5MB)

if [[ -z "$IMG" || ! -f "$IMG" ]]; then
  echo "用法: $0 <图片文件> [输出文件夹(默认~/Desktop/triposg_out)] [目标面数(默认200000)]" >&2
  exit 1
fi

TASK="task_$(date +%Y%m%d_%H%M%S)"
EXT="${IMG##*.}"
BASENAME="$(basename "${IMG%.*}")"
# 两套路径：宿主机视角(scp/mkdir/rm 用) 与 容器视角(docker exec 用)——同一挂载，别混
REMOTE_DIR="$REMOTE_BASE/inbox/$TASK"       # 宿主机：/home/user/triposg_transfer/...
REMOTE_IMG="$REMOTE_DIR/input.$EXT"
REMOTE_STL="$REMOTE_DIR/output.stl"
CTR_DIR="/workspace/inbox/$TASK"            # 容器：/workspace/...（= 上面那个挂载）
CTR_IMG="$CTR_DIR/input.$EXT"
CTR_STL="$CTR_DIR/output.stl"
LOCAL_STL="$OUT_DIR/${BASENAME}_${TASK}.stl"

echo "▶ 任务 $TASK"
echo "  输入图 : $IMG"
if [[ -n "$FACES" ]]; then
  echo "  减面到 : $FACES 面  (≈ $((FACES/20000)) MB)"
else
  echo "  减面   : 否（完整网格，文件较大 ~60MB）"
fi
echo "  输出到 : $LOCAL_STL"

# ---------- 0. 连通性检查 ----------
if ! ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$AIO" 'true' 2>/dev/null; then
  echo "❌ 连不上一体机 $AIO —— 检查网线/SSH（可先 ping 192.168.100.2）" >&2
  exit 2
fi

# ---------- 1. 上传 ----------
echo "⬆  上传图片..."
ssh -i "$KEY" "$AIO" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" "$IMG" "$AIO:$REMOTE_IMG"

# ---------- 2. 容器内推理（sudo 需要密码，用 -t 交互）----------
# 传了面数走减面脚本，否则走原始脚本（不减面）
echo "🧠 一体机模型推理中（约 30~40 秒，若提示则输入一体机 sudo 密码）..."
if [[ -n "$FACES" ]]; then
  ssh -t -i "$KEY" "$AIO" \
    "sudo docker exec '$CONTAINER' '$PYTHON' '$SCRIPT_LITE' '$CTR_IMG' '$CTR_STL' '$FACES'"
else
  ssh -t -i "$KEY" "$AIO" \
    "sudo docker exec '$CONTAINER' '$PYTHON' '$SCRIPT_FULL' '$CTR_IMG' '$CTR_STL'"
fi

# ---------- 3. 拉回结果 ----------
echo "⬇  拉回 STL..."
mkdir -p "$OUT_DIR"
scp -i "$KEY" "$AIO:$REMOTE_STL" "$LOCAL_STL"

# ---------- 4. 清理远程任务目录（结果已拉回）----------
ssh -i "$KEY" "$AIO" "rm -rf '$REMOTE_DIR'" 2>/dev/null || true

SIZE=$(du -h "$LOCAL_STL" | cut -f1)
echo "✅ 完成: $LOCAL_STL  ($SIZE)"

# ---------- 5. 自动用 BambuStudio 打开预览 ----------
if [[ -d "/Applications/BambuStudio.app" ]]; then
  open -a BambuStudio "$LOCAL_STL"
fi
