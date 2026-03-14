# TF-DocGen

Enterprise-grade Terraform documentation and governance engine.

---

## Why TF-DocGen?

Large organisations running infrastructure at scale face a well-known documentation problem: engineers write Terraform modules that work correctly but are poorly described, making them hard to discover, reuse, or audit.

TF-DocGen solves this by treating documentation as a first-class artefact of the software-delivery pipeline:

| Problem | TF-DocGen Solution |
|---------|-------------------|
| Module interfaces are opaque | Auto-generates a variable/output table from source |
| Governance rules are ignored | Flags every variable missing `type` or `description` |
| Docs drift from code | Regenerated on every CI run. Always in sync |
| Inconsistent formatting | Single Jinja2 template enforces a house standard |

---

## Features

- **AI-Powered Architectural Overviews**: Automatically generate architectural overviews using the Claude API based on your Terraform module's resources and inputs.
- **Secure Secret Management**: Integrates `.env` files and environment variables using `python-dotenv` for secure secret handling.
- **Automated Governance Enforcement**: Ensure strict compliance across all your modules by running with the `--strict` flag.

---

## Architecture

```
TF-DocGen
├── main.py       . Click CLI + orchestration layer
├── parser.py     . python-hcl2 extraction → typed dataclasses
├── template.j2   . Jinja2 Markdown template (presentation layer)
└── requirements.txt
```

**Key design decisions:**

- **python-hcl2** is used for all HCL parsing. No regex, so the tool handles complex type constraints, heredocs, and multi-file modules without brittle string manipulation.
- **Dataclasses** (`ModuleData`, `TerraformVariable`, `TerraformOutput`, `TerraformResource`) decouple the parse stage from the render stage, making it easy to add new output formats (JSON schema, Confluence pages, etc.) without touching the parser.
- **Jinja2** keeps all Markdown structure in one template file. Teams can fork `template.j2` to enforce a company-specific layout without changing any Python code.
- **Governance logic** lives in `TerraformVariable.governance_issues`. A pure property that can be unit-tested independently of the CLI.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/OrChetrit/TF-DocGen.git
cd tf-docgen

# Create a virtual environment (recommended)
python -m venv .venv

# Activate the virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell/CMD):
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up your environment variables
# Create a .env file and add your Anthropic API key
echo "ANTHROPIC_API_KEY=your_api_key_here" > .env

# Install the package locally in editable mode
pip install -e .
```

---

## Usage

### Recommended . Generate docs and enforce governance

```bash
python main.py --dir ./my-terraform-module --strict
```

> **`--strict` mode** causes the process to exit with code `1` if any variable
> is missing a `type` or `description`, blocking merges in pull-request pipelines.

### Generating AI-Powered Architectural Overviews

```bash
python main.py --dir ./my-module --ai-summary
```

> Requires an active `ANTHROPIC_API_KEY` defined in the `.env` file or environment.

### Basic . Generate README in the module directory

```bash
python main.py --dir ./modules/vpc
```

### Custom output path

```bash
python main.py --dir ./modules/vpc --output ./docs/vpc.md
```

### Custom Jinja2 template

```bash
python main.py --dir ./modules/vpc --template ./templates/corporate.j2
```

### Preview without writing (dry-run)

```bash
python main.py --dir ./modules/vpc --dry-run
```

### Strict mode . Fail CI on governance violations

```bash
python main.py --dir ./modules/vpc --strict
echo $?   # 1 if any variable is missing type or description
```

### All options

```
Usage: tf-docgen [OPTIONS]

  TF-DocGen. Enterprise-grade Terraform documentation and governance engine.

Options:
  -d, --dir PATH       Path to the Terraform module directory.  [required]
  -o, --output PATH    Destination README file. Default: <dir>/README.md
  -t, --template PATH  Custom Jinja2 template (.j2).
  --strict             Exit 1 if governance violations are found.
  --ai-summary         Generate an architectural overview using the Claude API.
  --dry-run            Print output to stdout instead of writing a file.
  --version            Show the version and exit.
  --help               Show this message and exit.
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/docs.yml
name: Generate Terraform Docs

on:
  push:
    paths:
      - 'modules/**/*.tf'

jobs:
  tf-docgen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install -r requirements.txt

      - name: Generate README and enforce governance
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          for dir in modules/*/; do
            python main.py --dir "$dir" --strict --ai-summary
          done

      - name: Commit updated READMEs
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "docs: regenerate module READMEs [skip ci]"
```

### Pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: tf-docgen
        name: Generate Terraform module docs
        language: python
        entry: tf-docgen
        args: [--dir, ., --strict]
        files: \.tf$
        pass_filenames: false
```

---

## Governance Rules

TF-DocGen enforces the following rules on every `variable` block:

| Rule | Attribute | Rationale |
|------|-----------|-----------|
| **G-001** | `description` | Enables self-service discovery in the module registry |
| **G-002** | `type`        | Prevents type-mismatch errors and documents the contract |

Violations are printed to `stderr` with a `[FAIL]` prefix. In `--strict` mode the process exits with code `1`, blocking merges in pull-request pipelines.

Example output for a non-compliant module:

```
tf-docgen  .  vpc
..................................................
  Parsing HCL files...
  Found 4 variable(s), 2 output(s), 3 resource(s).
  Running governance checks...
  [FAIL] Governance check failed . 2/4 variable(s) have issues:
         • enable_dns_support: missing `description`
         • tags: missing `type`, missing `description`
..................................................
```

---

## Extending TF-DocGen

### Adding a new governance rule

1. Open `parser.py` and update `TerraformVariable.governance_issues`:

```python
@property
def governance_issues(self) -> list[str]:
    issues = []
    if not self.description:
        issues.append("missing `description`")
    if not self.type:
        issues.append("missing `type`")
    # Add your rule here, e.g.:
    if self.sensitive and self.default is not None:
        issues.append("sensitive variable must not have a default")
    return issues
```

### Customising the template

Copy `template.j2` and edit as required. Pass the path with `--template`:

```bash
python main.py --dir ./modules/vpc --template ./my-template.j2
```

### Adding a new output format (e.g. JSON)

The `ModuleData` dataclass is format-agnostic. Introduce a new renderer in `main.py` alongside `render_readme()`, consuming the same `ModuleData` object.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `python-hcl2` | Robust HCL/Terraform file parser |
| `jinja2` | Template engine for Markdown generation |
| `click` | CLI argument parsing and user-friendly output |
| `anthropic` | Client for Claude API integration |
| `python-dotenv` | Secure `.env` file variable management |

---

## License

MIT © 2026 Or Chetrit

---

## Author

Developed by **Or Chetrit**.
