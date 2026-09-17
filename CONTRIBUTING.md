# Contributing to img-cut

Thank you for contributing to **img-cut**! This project is an open-source MCP server designed for high performance, zero host path leakage, and clean security hygiene.

---

## 🔒 Security & Path-Only Principles

1. **No Host Absolute Paths**: Never hardcode host-specific absolute paths (such as `/home/...`, `/Users/...`, or `C:\Users\...`). Use relative workspace paths or environment configurations (`IMGCUT_ALLOWED_WORKSPACES`).
2. **Zero Secrets**: Do not commit API keys, tokens, or credentials. All commits are scanned for secrets before submission.
3. **Pure Transparency**: Background removal outputs must maintain clean 32-bit ARGB alpha transparency without solid background fills.

---

## 📝 Commit Message Guidelines

All commit messages must follow the **Conventional Commits** specification. Commit messages must be written in **English only**, concise, objective, and non-conversational.

### Format

```text
<type>(<optional-scope>): <lowercase imperative subject>
```

### Allowed Types

- `feat`: A new feature or capability
- `fix`: A bug fix
- `docs`: Documentation changes
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding or updating tests
- `build`: Changes to build system or dependencies
- `ci`: Changes to CI configuration or audit scripts
- `chore`: Maintenance tasks, repo hygiene, .gitignore

### Rules

- **English only**: Non-English, conversational, or filler words are rejected by git hooks.
- **Imperative mood**: Use "add feature", not "added feature" or "adding feature".
- **No trailing period**: Do not end the subject line with a period (`.`).
- **Length**: Maximum 72 characters for the header line.
- **Examples**:
  - `feat: add batch background removal tool`
  - `fix(engine): enforce safe workspace path confinement`
  - `docs: update visual examples in readme`
  - `ci: configure automated gitleaks and quality gate`

---

## 🛡️ Quality Gate & Local Audit

Before submitting a commit or pull request, install git hooks and run the local audit scanner:

```bash
# 1. Install local git hooks (pre-commit & commit-msg)
./scripts/install_hooks.sh

# 2. Run the full Quality Gate audit locally
uv run python scripts/audit.py
```

The Quality Gate automatically validates:
1. **Secrets & Gitleaks Scan**: API keys, private keys, tokens.
2. **Path Leakage Scan**: Detection of host-specific absolute paths.
3. **Ruff Linter & Formatter**: Code quality and formatting standards.
4. **Pytest Test Suite**: Automated tests passing with zero errors.
5. **Commit Message Validation**: Conventional Commits compliance.
