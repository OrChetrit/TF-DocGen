"""
TF-DocGen | Created by Or Chetrit | MIT License
Purpose: Automated HCL parsing and documentation governance.
"""

# Usage:
#     tf-docgen --dir ./modules/vpc
#     tf-docgen --dir ./modules/vpc --output ./modules/vpc/README.md
#     tf-docgen --dir ./modules/vpc --strict   # exit 1 on governance violations

from __future__ import annotations

import sys
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader, select_autoescape

from parser import ModuleData, parse_module


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _get_template_env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape([]),  # plain Markdown — no HTML escaping
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_readme(data: ModuleData, template_path: Path) -> str:
    """Render the README content using the Jinja2 template."""
    env = _get_template_env(template_path.parent)
    template = env.get_template(template_path.name)
    return template.render(module=data)


# ---------------------------------------------------------------------------
# Governance report
# ---------------------------------------------------------------------------

def _print_governance_report(data: ModuleData) -> int:
    """
    Print a governance compliance summary to stderr.

    Returns the number of non-compliant variables found.
    """
    non_compliant = data.non_compliant_variables
    total = len(data.variables)

    if data.governance_passed:
        click.secho(
            f"  [PASS] Governance check passed — all {total} variable(s) are compliant.",
            fg="green",
            err=True,
        )
        return 0

    click.secho(
        f"  [FAIL] Governance check failed — {len(non_compliant)}/{total} variable(s) have issues:",
        fg="yellow",
        err=True,
    )
    for var in non_compliant:
        issues = ", ".join(var.governance_issues)
        click.secho(f"         • {var.name}: {issues}", fg="yellow", err=True)
    return len(non_compliant)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command(name="tf-docgen")
@click.option(
    "--dir", "-d",
    "module_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    help="Path to the Terraform module directory to document.",
)
@click.option(
    "--output", "-o",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Destination file for the generated README. Defaults to <module_dir>/README.md.",
)
@click.option(
    "--template", "-t",
    "template_path",
    default=None,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="Path to a custom Jinja2 template (.j2). Defaults to the built-in template.j2.",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit with code 1 if any governance violations are detected.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the generated README to stdout instead of writing to a file.",
)
@click.version_option(version="1.0.0", prog_name="tf-docgen")
def cli(
    module_dir: str,
    output_path: str | None,
    template_path: str | None,
    strict: bool,
    dry_run: bool,
) -> None:
    """
    TF-DocGen — Terraform Module Documentation Generator.

    Scans a Terraform module directory and generates a standardised README.md
    from its variables, outputs, and resources. Includes a governance check that
    flags variables missing required `description` or `type` attributes.

    Example:
        python main.py --dir ./my-terraform-module --strict
    """
    module_path = Path(module_dir).resolve()

    # Resolve template
    if template_path:
        tmpl = Path(template_path).resolve()
    else:
        tmpl = Path(__file__).parent / "template.j2"
        if not tmpl.is_file():
            click.secho(
                f"ERROR: Default template not found at {tmpl}. "
                "Please provide a --template path.",
                fg="red",
                err=True,
            )
            sys.exit(2)

    # Resolve output destination
    if output_path:
        dest = Path(output_path).resolve()
    else:
        dest = module_path / "README.md"

    click.secho(f"\ntf-docgen  ›  {module_path.name}", bold=True, err=True)
    click.secho("─" * 50, err=True)

    # Parse
    click.secho("  Parsing HCL files...", err=True)
    try:
        data = parse_module(module_path)
    except NotADirectoryError as exc:
        click.secho(f"ERROR: {exc}", fg="red", err=True)
        sys.exit(2)
    except Exception as exc:
        click.secho(f"ERROR: Failed to parse module — {exc}", fg="red", err=True)
        sys.exit(2)

    click.secho(
        f"  Found {len(data.variables)} variable(s), "
        f"{len(data.outputs)} output(s), "
        f"{len(data.resources)} resource(s).",
        err=True,
    )

    # Governance check — always printed to stderr; exits 1 in --strict mode
    click.secho("  Running governance checks...", err=True)
    violations = _print_governance_report(data)

    # Render
    click.secho("  Rendering template...", err=True)
    try:
        content = render_readme(data, tmpl)
    except Exception as exc:
        click.secho(f"ERROR: Template rendering failed — {exc}", fg="red", err=True)
        sys.exit(2)

    # Output
    if dry_run:
        click.secho("─" * 50, err=True)
        click.echo(content)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        click.secho(f"  README written → {dest}", fg="cyan", err=True)

    click.secho("─" * 50, err=True)
    click.secho("  Done.\n", bold=True, err=True)

    if strict and violations > 0:
        click.secho(
            "ERROR: Strict mode enabled — governance violations detected. "
            "Resolve all [FAIL] items above and re-run.",
            fg="red",
            err=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    cli()
