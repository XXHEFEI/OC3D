#!/bin/bash
# 双击运行：通过直连网线 SSH 到一体机，拉起 TripoSG 容器（triposg-dev）。
# 用途：一体机关机重启后，容器不会自动运行，需要手动拉起一次；这个脚本代替手动 SSH 操作。
#
# 安全说明：
# - 用专用 SSH key 免密登录（~/.ssh/id_ed25519_aio），本脚本不含任何密码。
# - 一体机上只精确授权了这一条命令可以免密 sudo 执行（/etc/sudoers.d/oc3d-docker-start），
#   不涉及更大范围的 docker 组权限或 sudo 权限。
# - 网络：需要网线直连一体机（Mac 侧 USB 10/100 LAN 2，静态 IP 192.168.100.1/24；
#   一体机侧已把静态 IP 持久化进 NetworkManager 配置，重启会自动生效，不需要手动重设）。

AIO_IP="192.168.100.2"
AIO_USER="user"
SSH_KEY="$HOME/.ssh/id_ed25519_aio"
CONTAINER="triposg-dev"

echo "===================================="
echo " 一体机 TripoSG 容器启动器"
echo "===================================="
echo

echo "🔌 检查网络连通性 ($AIO_IP)..."
if ! ping -c 1 -W 2 "$AIO_IP" >/dev/null 2>&1; then
  echo "❌ 无法连接到一体机 ($AIO_IP)。"
  echo "   请确认：网线已插好、Mac 的 USB 10/100 LAN 2 是否已连接。"
  echo
  echo "按任意键关闭这个窗口..."
  read -n 1
  exit 1
fi
echo "✅ 网络连通"
echo

echo "🚀 拉起容器 ($CONTAINER)..."
ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=8 "$AIO_USER@$AIO_IP" \
  "sudo -n docker start $CONTAINER" 2>&1

if [ $? -ne 0 ]; then
  echo
  echo "❌ 启动失败，请检查上面的错误信息。"
  echo "按任意键关闭这个窗口..."
  read -n 1
  exit 1
fi

echo
echo "📋 当前容器状态："
ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=8 "$AIO_USER@$AIO_IP" \
  "sudo -n docker ps" 2>&1

echo
echo "全部完成！容器已在后台运行，可以继续测试 TripoSG。"
echo
echo "按任意键关闭这个窗口..."
read -n 1
