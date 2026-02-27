#!/bin/bash
# 옵시디언 뷰어 서버 시작
# 사용법: ./web/run.sh [볼트경로]
# 예시:  ./web/run.sh ~/Documents/MyVault

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=${PORT:-8101}

if [ -n "$1" ]; then
  export OBSIDIAN_VAULT_PATH="$1"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Obsidian Vault Viewer"
echo " http://localhost:${PORT}"
if [ -n "$OBSIDIAN_VAULT_PATH" ]; then
  echo " Vault: ${OBSIDIAN_VAULT_PATH}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$SCRIPT_DIR"
python3 -m web.main
