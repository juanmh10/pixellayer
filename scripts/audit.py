#!/usr/bin/env python3
"""Automated Quality Gate & Security Audit for img-cut.

Enforces:
1. Gitleaks / Secret scanning (API keys, private keys, tokens)
2. Path leakage scanning (no host absolute paths like /home/..., C:\\Users\\...)
3. Code quality & style (Ruff check + Ruff format check)
4. Contract & functionality verification (Pytest test suite)
5. Conventional Commit message standards (English only, concise, non-conversational)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Files and directories monitored
SCANNED_EXTENSIONS = {
    ".py",
    ".json",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".sh",
    ".cfg",
    ".ini",
}
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "models_cache",
    ".venv",
    "venv",
    "env",
    "trash",
    "logs",
}

# 1. Gitleaks & Secret Detection Patterns
SECURITY_PATTERNS = [
    (
        "AWS Access Key / Secret Key",
        re.compile(r"(?i)(aws_access_key_id|aws_secret_access_key|AKIA[0-9A-Z]{16})"),
    ),
    (
        "GitHub Personal Access Token",
        re.compile(r"ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82}"),
    ),
    (
        "Private Key",
        re.compile(r"-----BEGIN (RSA|OPENSSH|EC|DSA|PGP|PRIVATE) KEY-----"),
    ),
    (
        "HuggingFace Token",
        re.compile(r"hf_[a-zA-Z0-9]{34}"),
    ),
    (
        "OpenAI / Anthropic API Key",
        re.compile(r"sk-[a-zA-Z0-9]{20,}|sk-ant-[a-zA-Z0-9-_]{20,}"),
    ),
    (
        "Google Cloud API Key",
        re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    ),
    (
        "Slack Token",
        re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),
    ),
    (
        "Generic Secret Assignment",
        re.compile(
            r'(?i)(api[_-]?key|secret|password|bearer|auth[_-]?token)\s*=\s*["\'][A-Za-z0-9_\-\.]{16,}["\']'
        ),
    ),
]

# 2. Host Absolute Path Leakage Patterns
PATH_PATTERNS = [
    (
        "Hardcoded User Home Directory",
        re.compile(
            r"(/home/[a-zA-Z0-9_\-]+|/Users/[a-zA-Z0-9_\-]+|[a-zA-Z]:\\Users\\[a-zA-Z0-9_\-]+)"
        ),
    ),
    (
        "WSL UNC Absolute Path",
        re.compile(r"\\\\wsl(\$|\.localhost)\\[a-zA-Z0-9_\-]+"),
    ),
]

# 3. Conventional Commit Regex
CONVENTIONAL_COMMIT_REGEX = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([a-z0-9_\-\./]+\))?(!)?:\s+([a-z0-9].{3,70})$"
)

# Portuguese / Conversational phrases to reject in commit messages
CONVERSATIONAL_WORDS = {
    "ajuste",
    "ajustes",
    "adicionado",
    "adicionando",
    "arrumado",
    "atualizado",
    "atualizando",
    "corrigido",
    "fiz",
    "fizemos",
    "teste",
    "testando",
    "arrumei",
    "alterado",
    "removido",
    "conversa",
    "conversas",
    "relatorio",
    "relatório",
    "acho",
    "talvez",
    "modificado",
    "subindo",
    "commitando",
    "projeto",
}


def find_python_tool(tool_name: str) -> str:
    """Find executable path for tool within venv, PATH, or local pip."""
    venv_tool = ROOT_DIR / ".venv" / "bin" / tool_name
    if venv_tool.exists():
        return str(venv_tool)

    which_result = subprocess.run(["which", tool_name], capture_output=True, text=True)
    if which_result.returncode == 0 and which_result.stdout.strip():
        return which_result.stdout.strip()

    user_tool = Path.home() / ".local" / "bin" / tool_name
    if user_tool.exists():
        return str(user_tool)

    return tool_name


def scan_security_and_paths() -> bool:
    """Scan all tracked and monitored files for secrets and absolute paths."""
    print("🔍 [1/4] Running Security, Secrets (Gitleaks) & Path Leakage Audit...")
    issues = []

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix not in SCANNED_EXTENSIONS:
                continue
            # Skip this audit script itself for self-contained pattern definitions
            if file_path.resolve() == Path(__file__).resolve():
                continue

            rel_path = file_path.relative_to(ROOT_DIR)

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    # Secrets scan
                    for rule_name, pattern in SECURITY_PATTERNS:
                        if pattern.search(line):
                            issues.append(
                                (str(rel_path), line_idx, f"SECRET: {rule_name}", line.strip())
                            )
                    # Absolute paths scan
                    for rule_name, pattern in PATH_PATTERNS:
                        # Allow docs explanation about policy exception
                        if "docs/general.md" in str(rel_path) and "veta caminhos absolutos" in line:
                            continue
                        if pattern.search(line):
                            issues.append(
                                (str(rel_path), line_idx, f"PATH LEAK: {rule_name}", line.strip())
                            )
            except Exception as e:
                issues.append((str(rel_path), 0, "ReadError", str(e)))

    if issues:
        print("❌ Security audit failed! Issues detected:")
        for rel_p, line_no, rule, snippet in issues:
            print(f"  - [{rule}] {rel_p}:{line_no} -> {snippet[:90]}")
        return False

    print("✅ No secrets, credentials, or host absolute paths detected.")
    return True


def run_code_quality() -> bool:
    """Run Ruff linter and format checker."""
    print("\n🐍 [2/4] Running Code Quality Checks (Ruff)...")
    ruff_bin = find_python_tool("ruff")

    # Linting
    res_lint = subprocess.run(
        [ruff_bin, "check", "src/", "tests/", "scripts/"],
        cwd=str(ROOT_DIR),
    )
    if res_lint.returncode != 0:
        print("❌ Ruff linter found code issues.")
        return False

    # Formatting check
    res_fmt = subprocess.run(
        [ruff_bin, "format", "--check", "src/", "tests/", "scripts/"],
        cwd=str(ROOT_DIR),
    )
    if res_fmt.returncode != 0:
        print("❌ Code formatting does not conform to Ruff format standards.")
        return False

    print("✅ Code quality and formatting approved!")
    return True


def run_unit_tests(fast_only: bool = True) -> bool:
    """Run test suite."""
    print("\n🧪 [3/4] Running Automated Test Suite (Pytest)...")
    pytest_bin = find_python_tool("pytest")
    cmd = [pytest_bin, "-k", "not slow"] if fast_only else [pytest_bin]

    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print("❌ Pytest test suite failed.")
        return False

    print("✅ All automated tests passed!")
    return True


def validate_commit_message(message: str) -> tuple[bool, str]:
    """Validate a commit message according to Conventional Commits standards."""
    clean_msg = message.strip()
    lines = clean_msg.splitlines()
    if not lines or not lines[0].strip():
        return False, "Commit message cannot be empty."

    header = lines[0].strip()

    # Check length
    if len(header) > 72:
        return False, f"Header line is too long ({len(header)} chars). Maximum is 72 chars."

    # Check Conventional Commit regex
    match = CONVENTIONAL_COMMIT_REGEX.match(header)
    if not match:
        return False, (
            f"Commit message does not follow Conventional Commits format:\n"
            f"  Received: '{header}'\n"
            f"  Expected: '<type>(<optional-scope>): <lowercase imperative subject>'\n"
            f"  Valid types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
        )

    # Check trailing period
    if header.endswith("."):
        return False, "Header line must not end with a period ('.')."

    # Reject conversational / non-English words in subject
    words = re.findall(r"\b[a-zA-ZáéíóúãõçÁÉÍÓÚÃÕÇ]+\b", header.lower())
    for w in words:
        if w in CONVERSATIONAL_WORDS:
            return False, (
                f"Conversational or non-English word '{w}' detected in commit message. "
                "Commit messages must be concise, professional, and in English only."
            )

    return True, "Valid conventional commit message."


def validate_commit_msg_file(file_path: Path) -> bool:
    """Validate commit message file from git commit-msg hook."""
    print(f"📝 Validating commit message in: {file_path}")
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")
    # Filter out git comment lines starting with '#'
    non_comment_lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
    raw_msg = "\n".join(non_comment_lines).strip()

    ok, reason = validate_commit_message(raw_msg)
    if not ok:
        print(f"❌ Commit message rejected: {reason}")
        return False

    print("✅ Commit message adheres to Conventional Commits standard.")
    return True


def audit_git_history() -> bool:
    """Check recent git commit messages in repository."""
    print("\n📜 [4/4] Auditing Git Commit Message Standards...")
    res = subprocess.run(
        ["git", "log", "-n", "10", "--format=%s"],
        capture_output=True,
        text=True,
        cwd=str(ROOT_DIR),
    )
    if res.returncode != 0:
        # Repository may not have commits yet
        print("ℹ️ No commit history found yet. Ready for initial commit.")
        return True

    messages = [m.strip() for m in res.stdout.splitlines() if m.strip()]
    all_ok = True
    for idx, msg in enumerate(messages, start=1):
        ok, reason = validate_commit_message(msg)
        if not ok:
            print(f"  ❌ Commit {idx}: '{msg}' -> {reason}")
            all_ok = False
        else:
            print(f"  ✅ Commit {idx}: '{msg}'")

    return all_ok


def main():
    parser = argparse.ArgumentParser(
        description="CI Quality Gate & Security Audit Scanner for img-cut"
    )
    parser.add_argument(
        "--commit-msg-file",
        type=Path,
        help="Path to commit message file (for git commit-msg hook)",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test execution (fast lint + security check)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run full CI suite including commit history audit",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Run pre-commit quality gate",
    )

    args = parser.parse_args()

    # Hook mode: commit-msg
    if args.commit_msg_file:
        success = validate_commit_msg_file(args.commit_msg_file)
        sys.exit(0 if success else 1)

    print("=" * 64)
    print("🚀 img-cut Quality Gate & Security Scanner")
    print("=" * 64)

    sec_ok = scan_security_and_paths()
    lint_ok = run_code_quality()
    tests_ok = True if args.skip_tests else run_unit_tests()
    history_ok = audit_git_history() if args.ci else True

    print("\n" + "=" * 64)
    if sec_ok and lint_ok and tests_ok and history_ok:
        print("🎉 QUALITY GATE PASSED! ALL CHECKS ARE HEALTHY.")
        print("=" * 64)
        sys.exit(0)
    else:
        print("⚠️ QUALITY GATE FAILED! Please resolve the reported issues.")
        print("=" * 64)
        sys.exit(1)


if __name__ == "__main__":
    main()
