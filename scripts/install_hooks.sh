#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "❌ Error: Not a git repository ($REPO_ROOT/.git not found)."
    exit 1
fi

mkdir -p "$HOOKS_DIR"

# 1. pre-commit hook
cat << 'EOF' > "$HOOKS_DIR/pre-commit"
#!/usr/bin/env bash
set -e

# Run security, path scan, ruff lint, and tests
python3 scripts/audit.py --pre-commit
EOF
chmod +x "$HOOKS_DIR/pre-commit"

# 2. commit-msg hook
cat << 'EOF' > "$HOOKS_DIR/commit-msg"
#!/usr/bin/env bash
set -e

# Validate Conventional Commits format and clean English standard
python3 scripts/audit.py --commit-msg-file "$1"
EOF
chmod +x "$HOOKS_DIR/commit-msg"

echo "✅ Git hooks installed successfully in .git/hooks/:"
echo "   - pre-commit (Gitleaks, path leakage, Ruff lint, Pytest)"
echo "   - commit-msg (Conventional Commits, English-only validation)"
