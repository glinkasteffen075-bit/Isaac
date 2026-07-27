#!/usr/bin/env bash
# In Termux ausführen: autorisiert den SSH-Pubkey aus dem Kali-Chroot
# (liegt auf /sdcard/isaac_termux_bridge.pub).
set -euo pipefail

PUB="${1:-/sdcard/isaac_termux_bridge.pub}"
AUTH="$HOME/.ssh/authorized_keys"
MARKER="# isaac-chroot-bridge"

if [ ! -f "$PUB" ]; then
  echo "Pubkey fehlt: $PUB"
  echo "Im Chroot muss existieren: /sdcard/isaac_termux_bridge.pub"
  exit 1
fi

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$AUTH"
chmod 600 "$AUTH"

LINE="$(tr -d '\r\n' < "$PUB")"
if grep -Fq "$LINE" "$AUTH" 2>/dev/null; then
  echo "Pubkey bereits in authorized_keys."
else
  echo "$LINE $MARKER" >> "$AUTH"
  echo "Pubkey eingetragen."
fi

# ensure sshd
if ! pgrep -x sshd >/dev/null 2>&1; then
  sshd || true
fi

echo "Fertig. Im Chroot testen:"
echo "  ssh -i data/termux_bridge_id -p 8022 -o BatchMode=yes u0_a10197@127.0.0.1 'echo OK'"
