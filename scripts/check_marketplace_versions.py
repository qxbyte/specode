#!/usr/bin/env python3
"""Verify .claude-plugin/marketplace.json's plugin versions match each
plugin's own plugins/<name>/.claude-plugin/plugin.json.

Why this script exists (AI-EDS v0.9 痛点 #4)
-------------------------------------------------
pluginhub is a Claude Code marketplace — `.claude-plugin/marketplace.json`
is the **outward-facing catalog** Claude Code clients read to discover and
install plugins. Each plugin's own `.claude-plugin/plugin.json` carries its
real version. The catalog must mirror those versions — otherwise Claude
Code shows / installs stale versions even though the repo tree has the
new code. This was discovered the hard way in a real-world try-run on
2026-06-28: marketplace.json had `specode=2.0.0`/`task-swarm=0.4.1` while
the plugins were 3.1.0 / 0.6.0 — every FIX-1/2/3 improvement we'd shipped
was invisible to real users.

This script runs in CI on every PR and push, and exits 1 if any version
mismatches — making the gap impossible to silently widen.

Stdlib-only (no PyYAML / no third party). Safe to run on any Python 3.11+.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def load_marketplace() -> dict[str, str]:
    """Return {plugin_name: declared_version} from marketplace.json."""
    data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for entry in data.get("plugins") or []:
        name = entry.get("name")
        version = entry.get("version")
        if isinstance(name, str) and isinstance(version, str):
            out[name] = version
    return out


def load_plugin_versions() -> dict[str, str]:
    """Return {plugin_name: real_version} from each plugins/<name>/.claude-plugin/plugin.json."""
    out: dict[str, str] = {}
    for plugin_dir in sorted((ROOT / "plugins").iterdir()):
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        name = data.get("name")
        version = data.get("version")
        if isinstance(name, str) and isinstance(version, str):
            out[name] = version
    return out


def main() -> int:
    declared = load_marketplace()
    actual = load_plugin_versions()

    errors: list[str] = []

    # Every plugin in the tree must be listed in the marketplace.
    missing_in_marketplace = sorted(set(actual) - set(declared))
    for name in missing_in_marketplace:
        errors.append(
            f"plugins/{name}/ exists with version {actual[name]} "
            f"but is NOT listed in .claude-plugin/marketplace.json"
        )

    # Every marketplace entry must point at an existing plugin.
    orphan_in_marketplace = sorted(set(declared) - set(actual))
    for name in orphan_in_marketplace:
        errors.append(
            f".claude-plugin/marketplace.json lists {name}@{declared[name]} "
            f"but plugins/{name}/ does not exist"
        )

    # Versions must match exactly.
    for name in sorted(set(declared) & set(actual)):
        if declared[name] != actual[name]:
            errors.append(
                f"version mismatch for {name}: "
                f"marketplace.json says {declared[name]}, "
                f"plugins/{name}/.claude-plugin/plugin.json says {actual[name]}"
            )

    if errors:
        sys.stderr.write("❌ marketplace.json out of sync with plugin manifests:\n\n")
        for e in errors:
            sys.stderr.write(f"  • {e}\n")
        sys.stderr.write(
            "\nFix: bump `.claude-plugin/marketplace.json` to match each plugin's\n"
            "`plugins/<name>/.claude-plugin/plugin.json` version (or vice-versa).\n"
            "See AI-EDS v0.9 痛点 #4 for context.\n"
        )
        return 1

    print(f"✓ marketplace.json in sync with {len(actual)} plugin manifest(s):")
    for name, version in sorted(actual.items()):
        print(f"  - {name} @ {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
