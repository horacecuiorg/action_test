#!/bin/bash

# 检查 root 权限
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ 请使用 root 用户运行此脚本"
  exit 1
fi

# 检查参数
if [ -z "$1" ]; then
  echo "❌ 使用方法: $0 <新端口号>"
  exit 1
fi

NEW_PORT="$1"
SSHD_CONFIG="/etc/ssh/sshd_config"
BACKUP_FILE="/etc/ssh/sshd_config.bak.$(date +%Y%m%d%H%M%S)"

# 备份配置
cp "$SSHD_CONFIG" "$BACKUP_FILE"
echo "📝 已备份原始配置到 $BACKUP_FILE"

# 修改 sshd_config
sed -i \
  -e "s/^#*Port .*/Port $NEW_PORT/" \
  -e "s/^#*PermitRootLogin .*/PermitRootLogin no/" \
  -e "s/^#*PasswordAuthentication .*/PasswordAuthentication no/" \
  -e "s/^#*PermitEmptyPasswords .*/PermitEmptyPasswords no/" \
  -e "s/^#*PubkeyAuthentication .*/PubkeyAuthentication yes/" \
  "$SSHD_CONFIG"

# 如某行被删掉（没有匹配），则手动追加
for line in \
  "Port $NEW_PORT" \
  "PermitRootLogin no" \
  "PasswordAuthentication no" \
  "PermitEmptyPasswords no" \
  "PubkeyAuthentication yes"
do
  key=$(echo "$line" | cut -d' ' -f1)
  if ! grep -q "^$key" "$SSHD_CONFIG"; then
    echo "$line" >> "$SSHD_CONFIG"
  fi
done

# 重启 SSH 服务
echo "🔄 正在重启 ssh 服务..."
systemctl restart ssh

# 状态检查
if systemctl status ssh | grep -q "active (running)"; then
  echo "✅ SSH 服务已成功重启，当前端口：$NEW_PORT"
else
  echo "⚠️ SSH 服务重启失败，请检查配置文件语法"
fi
