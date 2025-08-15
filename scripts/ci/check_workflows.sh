#!/usr/bin/env bash
set -euo pipefail

# Validate GitHub Actions workflows syntax & common mistakes

echo "▶ actionlint"
if command -v actionlint >/dev/null 2>&1; then
  actionlint -color
else
  echo "⚠ actionlint not found" >&2
fi

echo "▶ yamllint"
if command -v yamllint >/dev/null 2>&1; then
  if [ -f .yamllint ]; then
    yamllint -c .yamllint -s .github/workflows
  else
    yamllint -s .github/workflows
  fi
else
  echo "⚠ yamllint not found" >&2
fi

echo "▶ shellcheck (CI helper scripts)"
if command -v shellcheck >/dev/null 2>&1; then
  find scripts -type f -name "*.sh" -print0 | xargs -0 -r shellcheck
else
  echo "⚠ shellcheck not found" >&2
fi

echo "✅ Workflows look good."
