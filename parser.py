"""
TF-DocGen | Created by Or Chetrit | MIT License
Purpose: Automated HCL parsing and documentation governance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import hcl2


# ---------------------------------------------------------------------------
# Sensitive keyword masking
# ---------------------------------------------------------------------------

_SENSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {"key", "password", "secret", "token", "credential"}
)
_SENSITIVE_MAX_LEN: int = 32


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TerraformVariable:
    name: str
    type: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = None
    nullable: Optional[bool] = None
    sensitive: bool = False

    @property
    def has_default(self) -> bool:
        return self.default is not None

    @property
    def governance_issues(self) -> list[str]:
        """Return a list of governance rule violations for this variable."""
        issues = []
        if not self.description:
            issues.append("missing `description`")
        if not self.type:
            issues.append("missing `type`")
        return issues

    @property
    def is_compliant(self) -> bool:
        return len(self.governance_issues) == 0

    def _is_sensitive_by_name(self) -> bool:
        """Return True if the variable name contains any sensitive keyword."""
        name_lower = self.name.lower()
        return any(kw in name_lower for kw in _SENSITIVE_KEYWORDS)

    def default_display(self) -> str:
        """Raw display of the default value — no masking applied."""
        if self.default is None:
            return "*required*"
        if self.default == "":
            return '`""`'
        if isinstance(self.default, str):
            return f'`"{self.default}"`'
        if isinstance(self.default, bool):
            return f"`{str(self.default).lower()}`"
        return f"`{self.default}`"

    def sensitive_default_display(self) -> str:
        """
        Display the default value with sensitive data masking.

        A default value is redacted if any of the following apply:
        - The variable is declared with ``sensitive = true`` in HCL.
        - The variable **name** contains a sensitive keyword
          (key, password, secret, token, credential).
        - The default is a string longer than _SENSITIVE_MAX_LEN characters,
          which may indicate an embedded secret.

        Returns ``<REDACTED>`` for sensitive values, otherwise delegates
        to :meth:`default_display`.
        """
        if self.default is None:
            return "*required*"

        should_redact = (
            self.sensitive
            or self._is_sensitive_by_name()
            or (isinstance(self.default, str) and len(self.default) > _SENSITIVE_MAX_LEN)
        )

        if should_redact:
            return "`<REDACTED>`"

        return self.default_display()

    def type_display(self) -> str:
        return f"`{self.type}`" if self.type else "*untyped*"


@dataclass
class TerraformOutput:
    name: str
    description: Optional[str] = None
    value: Optional[str] = None
    sensitive: bool = False


@dataclass
class TerraformResource:
    resource_type: str
    resource_name: str


@dataclass
class ModuleData:
    module_name: str
    variables: list[TerraformVariable] = field(default_factory=list)
    outputs: list[TerraformOutput] = field(default_factory=list)
    resources: list[TerraformResource] = field(default_factory=list)
    required_providers: dict[str, Any] = field(default_factory=dict)
    terraform_required_version: Optional[str] = None

    @property
    def non_compliant_variables(self) -> list[TerraformVariable]:
        return [v for v in self.variables if not v.is_compliant]

    @property
    def governance_passed(self) -> bool:
        return len(self.non_compliant_variables) == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_load_hcl(path: Path, module_root: Path) -> dict:
    """
    Load an HCL file and return its parsed contents, or {} if missing.

    Performs a path traversal check: the resolved file path must be
    contained within ``module_root``.  Any file that escapes the module
    directory (e.g. via symlinks or ``../`` segments) is silently skipped.
    """
    if not path.is_file():
        return {}

    try:
        resolved = path.resolve()
    except OSError:
        return {}

    # Security: ensure the file is inside the declared module root.
    try:
        resolved.relative_to(module_root)
    except ValueError:
        # File resolved outside the module directory — skip it.
        return {}

    with resolved.open("r", encoding="utf-8") as fh:
        return hcl2.load(fh)


def _stringify_type(raw: Any) -> Optional[str]:
    """
    Convert HCL2-parsed type expressions to a readable string.

    python-hcl2 returns type constraints as either plain strings (e.g. "string")
    or as nested structures for complex types. We flatten these to a single string
    for display purposes.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # e.g. {"list": "string"} → "list(string)"
        for k, v in raw.items():
            inner = _stringify_type(v)
            return f"{k}({inner})" if inner else k
    if isinstance(raw, list):
        parts = [_stringify_type(item) for item in raw]
        return ", ".join(p for p in parts if p)
    return str(raw)


def _parse_variables(parsed: dict) -> list[TerraformVariable]:
    variables = []
    for block in parsed.get("variable", []):
        for var_name, attrs in block.items():
            variables.append(
                TerraformVariable(
                    name=var_name,
                    type=_stringify_type(attrs.get("type")),
                    description=attrs.get("description"),
                    default=attrs.get("default"),
                    nullable=attrs.get("nullable"),
                    sensitive=bool(attrs.get("sensitive", False)),
                )
            )
    return variables


def _parse_outputs(parsed: dict) -> list[TerraformOutput]:
    outputs = []
    for block in parsed.get("output", []):
        for out_name, attrs in block.items():
            # Value may be an expression string or a dict; we stringify for display.
            raw_value = attrs.get("value")
            value_str = str(raw_value) if raw_value is not None else None
            outputs.append(
                TerraformOutput(
                    name=out_name,
                    description=attrs.get("description"),
                    value=value_str,
                    sensitive=bool(attrs.get("sensitive", False)),
                )
            )
    return outputs


def _parse_resources(parsed: dict) -> list[TerraformResource]:
    resources = []
    for block in parsed.get("resource", []):
        for res_type, res_names in block.items():
            for res_name in res_names.keys():
                resources.append(TerraformResource(resource_type=res_type, resource_name=res_name))
    return resources


def _parse_terraform_block(parsed: dict) -> tuple[Optional[str], dict]:
    """Extract required_version and required_providers from the terraform{} block."""
    required_version = None
    required_providers: dict[str, Any] = {}

    for block in parsed.get("terraform", []):
        required_version = required_version or block.get("required_version")
        for rp_block in block.get("required_providers", []):
            required_providers.update(rp_block)

    return required_version, required_providers


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_module(module_dir: str | Path) -> ModuleData:
    """
    Parse a Terraform module directory and return a populated ModuleData object.

    Reads variables.tf, outputs.tf, and main.tf. Additional .tf files in the
    directory are also scanned for resource blocks.

    Security: all .tf files are resolved and validated to reside within
    ``module_dir`` before being opened, preventing path traversal attacks.

    Args:
        module_dir: Path to the root of the Terraform module.

    Returns:
        A ModuleData instance with all extracted attributes.

    Raises:
        NotADirectoryError: If module_dir does not exist or is not a directory.
    """
    module_path = Path(module_dir).resolve()
    if not module_path.is_dir():
        raise NotADirectoryError(f"Module directory not found: {module_path}")

    module_name = module_path.name

    # Parse dedicated files (path traversal guard is inside _safe_load_hcl)
    variables_data = _safe_load_hcl(module_path / "variables.tf", module_path)
    outputs_data = _safe_load_hcl(module_path / "outputs.tf", module_path)
    main_data = _safe_load_hcl(module_path / "main.tf", module_path)

    variables = _parse_variables(variables_data)
    outputs = _parse_outputs(outputs_data)
    resources = _parse_resources(main_data)
    required_version, required_providers = _parse_terraform_block(main_data)

    # Scan remaining .tf files for additional resources (e.g. resources split across files)
    known_files = {"variables.tf", "outputs.tf", "main.tf"}
    for tf_file in sorted(module_path.glob("*.tf")):
        if tf_file.name in known_files:
            continue
        extra = _safe_load_hcl(tf_file, module_path)
        resources.extend(_parse_resources(extra))
        if required_version is None:
            rv, rp = _parse_terraform_block(extra)
            required_version = rv
            required_providers.update(rp)

    return ModuleData(
        module_name=module_name,
        variables=variables,
        outputs=outputs,
        resources=resources,
        required_providers=required_providers,
        terraform_required_version=required_version,
    )
