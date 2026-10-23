"""Check the integration's version against its releases.

- Without ``--tag`` (pull requests, pushes): once the integration changed
  since the latest release tag, ``manifest.json`` must have a higher version
  than that tag. It may never be lower.
- With ``--tag`` (a release tag being pushed): the tag must equal the version.

Releases are tagged ``X.Y.Z``, without a ``v`` prefix. Needs the git history
and tags.

Usage: python script/check_version.py [--tag TAG]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).parents[1]
INTEGRATION = "custom_components/cfos_powerbrain"
RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _release(text: str) -> tuple[int, int, int] | None:
    """The version of a release tag, or None for anything else."""
    if (match := RELEASE.match(text)) is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _changed_since(tag: str) -> bool:
    """Whether the integration differs between ``tag`` and HEAD."""
    diff = subprocess.run(
        ["git", "diff", "--quiet", tag, "HEAD", "--", INTEGRATION], cwd=ROOT
    )
    if diff.returncode > 1:
        sys.exit(f"git diff against {tag} failed")
    return diff.returncode == 1


def main() -> int:
    """Print the outcome; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="the release tag being pushed")
    args = parser.parse_args()

    manifest = ROOT / INTEGRATION / "manifest.json"
    version_text = json.loads(manifest.read_text())["version"]
    if (version := _release(version_text)) is None:
        print(f"manifest.json: version {version_text} is not X.Y.Z")
        return 1

    if args.tag is not None:
        if args.tag != version_text:
            print(f"Tag {args.tag} differs from manifest.json version {version_text}")
            return 1
        print(f"Tag {args.tag} matches manifest.json")
        return 0

    tags = subprocess.run(
        ["git", "tag", "--list"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.split()
    releases = sorted(
        (release, tag) for tag in tags if (release := _release(tag)) is not None
    )
    if not releases:
        print("No release yet")
        return 0
    latest, tag = releases[-1]

    if version < latest:
        print(f"manifest.json version {version_text} is below release {tag}")
        return 1
    if version == latest and _changed_since(tag):
        print(
            f"{INTEGRATION} changed since release {tag}: raise the version in "
            f"manifest.json above {tag}"
        )
        return 1
    print(f"Version {version_text}, latest release {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
