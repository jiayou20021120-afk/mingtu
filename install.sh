#!/usr/bin/env bash
# Install mingtu: the Python package, plus the SKILL.md bundle into whichever
# AI agents you actually have. Everything is optional and nothing is overwritten
# without asking.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLUE=$'\033[34m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'

say() { printf '%s%s%s\n' "$BLUE" "$1" "$OFF"; }
ok()  { printf '%s  ✓ %s%s\n' "$GREEN" "$1" "$OFF"; }
warn(){ printf '%s  ! %s%s\n' "$YELLOW" "$1" "$OFF"; }

# ----------------------------------------------------------------- package

say "1/2  安装 mingtu 命令"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "找不到 python3。先装 Python 3.9 以上版本。" >&2
  exit 1
fi

# Each strategy is tried in turn and allowed to fail. A machine that already
# has mingtu installed must not abort the run — the skill step below is
# independent and still worth doing.
install_package() {
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force "$HERE" >/dev/null 2>&1 && return 0
    pipx uninstall mingtu >/dev/null 2>&1 || true
    pipx install "$HERE" >/dev/null 2>&1 && return 0
    warn "pipx 安装失败，回退到 pip --user"
  fi
  "$PYTHON" -m pip install --user --upgrade "$HERE" >/dev/null 2>&1 && return 0
  "$PYTHON" -m pip install --user --upgrade --break-system-packages "$HERE" \
    >/dev/null 2>&1 && return 0
  return 1
}

if install_package; then
  ok "包安装完成"
else
  warn "自动安装失败。手动跑：$PYTHON -m pip install --user '$HERE'"
fi

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) [ -x "$HOME/.local/bin/mingtu" ] &&
       warn "把 \$HOME/.local/bin 加进 PATH 才能直接用 mingtu 命令" ;;
esac

if command -v mingtu >/dev/null 2>&1; then
  ok "$(mingtu --version)"
elif [ -x "$HOME/.local/bin/mingtu" ]; then
  ok "$("$HOME/.local/bin/mingtu" --version)（在 ~/.local/bin 下）"
else
  warn "mingtu 不在 PATH 里，可用 '$PYTHON -m mingtu.cli' 代替"
fi

# ----------------------------------------------------------------- skill

say "2/2  安装 SKILL 包（给 AI agent 用，可跳过）"

# SKILL.md is an open standard; these are the directories the major agents read.
TARGETS=(
  "$HOME/.claude/skills/mingtu"        # Claude Code / Claude Desktop
  "$HOME/.cursor/skills/mingtu"        # Cursor
  "$HOME/.codex/skills/mingtu"         # Codex
  "$HOME/.agents/skills/mingtu"        # OpenClaw and friends
)

installed=0
for dst in "${TARGETS[@]}"; do
  parent="$(dirname "$(dirname "$dst")")"
  [ -d "$parent" ] || continue          # that agent isn't installed; skip quietly
  # Replace rather than merge: a stale SKILL.md or leftover scripts/ from an
  # older layout would send the agent down a path that no longer exists.
  case "$dst" in */skills/mingtu) rm -rf "$dst" ;; esac
  mkdir -p "$dst"
  cp -R "$HERE/skill/." "$dst/"
  ok "$dst"
  installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
  warn "没检测到任何 agent 目录。手动装：把 skill/ 的内容拷进你的 agent 技能目录"
fi

printf '\n%s试一下：%s\n' "$DIM" "$OFF"
printf '  mingtu full --solar 1995-3-12 --time 14:20 --gender 女 --city 杭州 --today\n'
printf '%s或者在 AI agent 里直接说「帮我算一下八字」。%s\n' "$DIM" "$OFF"
