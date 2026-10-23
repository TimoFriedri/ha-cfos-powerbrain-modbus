"""Check the integration against Home Assistant's quality scale rules.

hassfest checks the quality scale of core integrations only. This runs the
same checks against this custom integration, using hassfest from a checkout of
Home Assistant core (the version the tests pin), and adds the ones hassfest
leaves to review but a script can see:

- ``quality_scale.yaml`` matches hassfest's schema;
- every rule of the target tiers, plus strict-typing, is done or exempt;
- hassfest's own checks pass for the rules marked done;
- parallel-updates: every platform sets ``PARALLEL_UPDATES``;
- config-entry-unloading: ``__init__.py`` has ``async_unload_entry``;
- integration-owner: the manifest names a code owner.

strict-typing itself is enforced by mypy (see pyproject.toml): hassfest's
check for it reads core's ``.strict-typing`` file, which does not apply here.

Usage: python script/check_quality_scale.py <home-assistant/core checkout>
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

INTEGRATION = Path(__file__).parents[1] / "custom_components" / "cfos_powerbrain"
TARGET_TIERS = ("bronze", "silver")
EXTRA_RULES = {"strict-typing"}
CHECKED_BY_MYPY = {"strict-typing"}


def _defines(module: ast.Module, name: str) -> bool:
    """Whether a module defines ``name`` at its top level."""
    for node in module.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return True
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == name:
                return True
    return False


def _own_checks(rules_done: set[str], manifest: dict[str, object]) -> list[str]:
    """The rules hassfest leaves to review, as far as a script can tell."""
    from homeassistant.const import Platform

    errors: list[str] = []
    if "parallel-updates" in rules_done:
        for platform in Platform:
            path = INTEGRATION / f"{platform.value}.py"
            if path.is_file() and not _defines(
                ast.parse(path.read_text()), "PARALLEL_UPDATES"
            ):
                errors.append(
                    f"[parallel-updates] {path.name} sets no PARALLEL_UPDATES"
                )
    if "config-entry-unloading" in rules_done and not _defines(
        ast.parse((INTEGRATION / "__init__.py").read_text()), "async_unload_entry"
    ):
        errors.append("[config-entry-unloading] __init__.py has no async_unload_entry")
    if "integration-owner" in rules_done and not manifest.get("codeowners"):
        errors.append("[integration-owner] manifest.json names no codeowners")
    return errors


def main(core: Path) -> int:
    """Print every problem found; return the exit code."""
    sys.path.insert(0, str(core))
    import probatio
    from script.hassfest.model import Config, Integration, ScaledQualityScaleTiers
    from script.hassfest.quality_scale import SCALE_RULES, SCHEMA, VALIDATORS

    from homeassistant.util.yaml import load_yaml_dict

    config = Config(
        specific_integrations=[INTEGRATION],
        root=core,
        action="validate",
        requirements=False,
    )
    integration = Integration(INTEGRATION, _config=config)
    integration.load_manifest()

    data = load_yaml_dict(str(INTEGRATION / "quality_scale.yaml"))
    try:
        SCHEMA(data)
    except probatio.Invalid as err:
        print(f"quality_scale.yaml: {err}")
        return 1

    rules_met: set[str] = set()
    rules_done: set[str] = set()
    for name, value in data["rules"].items():
        status = value["status"] if isinstance(value, dict) else value
        if status in {"done", "exempt"}:
            rules_met.add(name)
        if status == "done":
            rules_done.add(name)

    errors: list[str] = []
    required = EXTRA_RULES.union(
        *(SCALE_RULES[ScaledQualityScaleTiers[tier.upper()]] for tier in TARGET_TIERS)
    )
    errors += [f"[{rule}] required, but todo" for rule in sorted(required - rules_met)]
    for rule in sorted(rules_done - CHECKED_BY_MYPY):
        if (validator := VALIDATORS.get(rule)) is not None:
            found = validator.validate(config, integration, rules_done=rules_done)
            errors += [f"[{rule}] {error}" for error in found or []]
    errors += _own_checks(rules_done, integration.manifest)
    errors += [str(error) for error in integration.errors]

    for error in errors:
        print(error)
    if not errors:
        print(
            f"Quality scale: {', '.join(TARGET_TIERS)} and "
            f"{', '.join(sorted(EXTRA_RULES))} met"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]).resolve()))
