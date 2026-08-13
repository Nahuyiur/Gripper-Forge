#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

info() {
  printf '\033[1;36m[Gripper Forge]\033[0m %s\n' "$1"
}

fail() {
  printf '\033[1;31m[启动失败]\033[0m %s\n' "$1" >&2
  exit 1
}

file_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    fail "系统缺少 shasum 或 sha256sum，无法检查依赖版本。"
  fi
}

command -v node >/dev/null 2>&1 || fail "未找到 Node.js，请先安装 Node.js 22.13 或更高版本。"
command -v npm >/dev/null 2>&1 || fail "未找到 npm，请重新安装完整的 Node.js。"

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
NODE_MINOR="$(node -p 'Number(process.versions.node.split(".")[1])')"
if (( NODE_MAJOR < 22 || (NODE_MAJOR == 22 && NODE_MINOR < 13) )); then
  fail "当前 Node.js 为 $(node --version)，需要 22.13 或更高版本。"
fi

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
    PYTHON_BIN="$candidate"
    break
  fi
done
[[ -n "$PYTHON_BIN" ]] || fail "未找到 Python 3.12 或更高版本。"

NPM_LOCK_HASH="$(file_hash package-lock.json)"
NPM_MARKER="node_modules/.gripper-forge-lock.sha256"
NPM_INSTALLED_HASH="$(cat "$NPM_MARKER" 2>/dev/null || true)"
if [[ ! -d node_modules || "$NPM_INSTALLED_HASH" != "$NPM_LOCK_HASH" ]]; then
  info "正在安装网页依赖…"
  npm ci
  printf '%s' "$NPM_LOCK_HASH" > "$NPM_MARKER"
else
  info "网页依赖已是最新。"
fi

if [[ ! -x .venv/bin/python ]]; then
  info "正在创建 Python 虚拟环境…"
  "$PYTHON_BIN" -m venv .venv
fi

REQUIREMENTS_HASH="$(file_hash requirements.txt)"
PYTHON_MARKER=".venv/.gripper-forge-requirements.sha256"
PYTHON_INSTALLED_HASH="$(cat "$PYTHON_MARKER" 2>/dev/null || true)"
if [[ "$PYTHON_INSTALLED_HASH" == "$REQUIREMENTS_HASH" ]]; then
  info "几何服务依赖已是最新。"
else
  info "正在安装几何服务依赖…"
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
  printf '%s' "$REQUIREMENTS_HASH" > "$PYTHON_MARKER"
fi

if [[ "${1:-}" == "--install-only" ]]; then
  info "依赖检查完成。"
  exit 0
fi

info "正在启动设计器：http://localhost:3000/"
info "按 Ctrl+C 可同时停止网页和几何服务。"
exec npm run dev:all
