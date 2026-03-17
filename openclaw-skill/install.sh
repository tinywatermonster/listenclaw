#!/bin/bash
# ListenClaw OpenClaw Skill 一键安装

SKILL_DIR="${HOME}/.openclaw/skills"
SKILL_FILE="${SKILL_DIR}/listenclaw.md"

mkdir -p "$SKILL_DIR"

curl -fsSL https://raw.githubusercontent.com/tinywatermonster/listenclaw/main/openclaw-skill/listenclaw.md \
  -o "$SKILL_FILE"

echo "✅ ListenClaw skill 已安装到 $SKILL_FILE"
echo "重启 OpenClaw 后生效。"
