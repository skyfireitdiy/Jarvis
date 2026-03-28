#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="$ROOT_DIR/src/jarvis/jarvis_vscode_extension"

if [[ ! -d "$EXT_DIR" ]]; then
  echo "[ERROR] VS Code 扩展目录不存在: $EXT_DIR" >&2
  exit 1
fi

cd "$EXT_DIR"

echo "[INFO] Working directory: $EXT_DIR"

if [[ ! -f package.json ]]; then
  echo "[ERROR] 未找到 package.json" >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  echo "[INFO] 安装依赖..."
  npm install
else
  echo "[INFO] 使用现有 node_modules"
fi

echo "[INFO] 编译 TypeScript..."
npm run build

if [[ ! -f dist/extension.js ]]; then
  echo "[ERROR] 编译完成后未找到产物 dist/extension.js" >&2
  exit 1
fi

echo "[INFO] 打包 VSIX..."
rm -f ./*.vsix
npm run package

VSIX_PATH="$(find . -maxdepth 1 -type f -name '*.vsix' | head -n 1)"
if [[ -z "$VSIX_PATH" ]]; then
  echo "[ERROR] 打包完成后未找到 .vsix 产物" >&2
  exit 1
fi

echo "[SUCCESS] TypeScript 产物: $EXT_DIR/dist/extension.js"
echo "[SUCCESS] VSIX 产物: $EXT_DIR/${VSIX_PATH#./}"
