#!/usr/bin/env bash
set -Eeuo pipefail

required=(
  AGENTS.md
  WORKFLOW.md
  harness/manifest.yaml
  harness/roster.yaml
  harness/governors.yaml
  harness/tool-policy.yaml
  harness/prompt-firewall.yaml
)

for f in "${required[@]}"; do
  if [ ! -f "$f" ]; then
    echo "missing required file: $f" >&2
    exit 1
  fi
done

if [ ! -d .git ]; then
  echo "not a git repo" >&2
  exit 1
fi

mkdir -p .worktrees
echo "harness contract valid"
