#!/bin/bash

# 检查是否为 root 用户
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ 请使用 root 用户运行此脚本"
  exit 1
fi

# 检查是否提供用户名参数
if [ -z "$1" ]; then
  echo "❌ 使用方法: $0 <username>"
  exit 1
fi

USERNAME="$1"

# 创建新用户并添加到 sudo 组
if id "$USERNAME" &>/dev/null; then
  echo "⚠️ 用户 $USERNAME 已存在，跳过创建"
else
  echo "🆕 创建用户 $USERNAME..."
  adduser --disabled-password --gecos "" "$USERNAME"
  usermod -aG sudo "$USERNAME"
fi

# 创建 SSH 目录并设置权限
USER_HOME="/home/$USERNAME"
SSH_DIR="$USER_HOME/.ssh"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown "$USERNAME:$USERNAME" "$SSH_DIR"

# 下载公钥并写入 authorized_keys
# echo "🌐 下载公钥..."
# curl -fsSL -o "$SSH_DIR/authorized_keys" https://raw.githubusercontent.com/HoraceCui/githubServer/main/eu/id_rsa.pub
echo "🌐 复制公钥..."
cp "$(dirname "$0")/id_rsa.pub" "$SSH_DIR/authorized_keys"

# 设置权限
chmod 600 "$SSH_DIR/authorized_keys"
chown "$USERNAME:$USERNAME" "$SSH_DIR/authorized_keys"

# 添加免密码 sudo 权限（Debian sudoers 结构）
SUDOERS_FILE="/etc/sudoers.d/$USERNAME"
echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"

echo "✅ 用户 $USERNAME 配置完成，已启用 SSH 免密登录"
