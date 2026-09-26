#!/usr/bin/env python3
"""release-law.py — role-count release law (v1.0 @12, v1.1 @25, v1.2 @50).

Deterministic: reads manifest.json role count, checks thresholds, and
when crossed prints the target version. Does NOT push or tag by itself
(CI/gate decides); --apply prints the tag command for the operator.

Tag source (first one that answers):
  1. RELEASE_TAG env var, comma-separated. The publish script resolves the
     real tags in the dev repo and hands them to the gate, because
     `git archive` exports carry no .git and therefore no tags.
  2. `git tag -l` when this tree is a work tree.
  3. Neither -> the check FAILS with "tag source unknown". An unverifiable
     tag set is not a tagged milestone.

Usage:
  python3 scripts/release-law.py            # report current status
  python3 scripts/release-law.py --check    # exit 1 if a release is due
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")

# env var carrying the dev repo's tag list into a tagless export
TAG_ENV = "RELEASE_TAG"
TAG_PREFIXES = ("roles-v", "v")

# role-count -> version milestone (same style as the skills 100-law)
THRESHOLDS = [
    (12, "v1.0.0"),
    (25, "v1.1.0"),
    (50, "v1.2.0"),
    (75, "v1.3.0"),
    (100, "v2.0.0"),
]


def current_count() -> int:
    if not os.path.exists(MANIFEST):
        # fall back to counting role dirs
        return len([d for d in os.listdir(os.path.join(ROOT, "roles"))
                    if os.path.isdir(os.path.join(ROOT, "roles", d))])
    m = json.load(open(MANIFEST))
    return int(m.get("count", len(m.get("roles", []))))


def _env_tags() -> list[str] | None:
    raw = os.environ.get(TAG_ENV, "").strip()
    if not raw:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


def _git_tags() -> list[str] | None:
    """Tag list from the work tree, or None when this is not a git tree."""
    probe = subprocess.run(["git", "-C", ROOT, "rev-parse",
                            "--is-inside-work-tree"],
                           capture_output=True, text=True)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    r = subprocess.run(["git", "-C", ROOT, "tag", "-l"],
                       capture_output=True, text=True)
    return [t.strip() for t in r.stdout.splitlines() if t.strip()]


def tag_set() -> tuple[list[str] | None, str]:
    """(tags, source). tags None means no usable source."""
    tags = _env_tags()
    if tags is not None:
        return tags, TAG_ENV
    tags = _git_tags()
    if tags is not None:
        return tags, "git"
    return None, "unknown"


def _version_key(tag: str) -> tuple[int, ...]:
    name = tag
    for prefix in TAG_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    try:
        return tuple(int(x) for x in name.split("-")[0].split(".")[:3])
    except Exception:
        return (0,)


def latest_tag(tags: list[str] | None) -> str:
    if not tags:
        return "none"
    versioned = [t for t in tags if t.startswith(TAG_PREFIXES)]
    if not versioned:
        return "none"
    return max(versioned, key=_version_key)


# Every file that states the package version. They must agree with each
# other and with the newest release tag (first-principles review FP-17,
# 2026-09-26: npm said 1.2.3 while the JetBrains build said 1.1.0 and the
# Claude plugin said 0.1.0). Requiring the newest TAG, not just agreement,
# is what makes a bump land only in the release commit: a bumped file with
# no tag of its own turns this gate red until that commit is tagged.
VERSION_ANCHOR = "packages/aero-agent-roles/package.json"


def _json_version(rel: str) -> str | None:
    return json.load(open(os.path.join(ROOT, rel))).get("version")


def _gradle_version(rel: str) -> str | None:
    import re
    m = re.search(r'^version\s*=\s*"([^"]+)"',
                  open(os.path.join(ROOT, rel)).read(), re.M)
    return m.group(1) if m else None


VERSION_FILES = [
    (VERSION_ANCHOR, _json_version),
    (".claude-plugin/plugin.json", _json_version),
    ("packages/jetbrains-plugin/build.gradle.kts", _gradle_version),
]


def version_problems(tags: list[str] | None) -> list[str]:
    """Why the version files do not name the newest release ([] = fine).

    A tree without the npm package (a bare test export) has no version
    files to grade; the real repo always has it, and then every listed
    file must exist."""
    if not os.path.exists(os.path.join(ROOT, VERSION_ANCHOR)):
        return []
    found, problems = {}, []
    for rel, read in VERSION_FILES:
        if not os.path.exists(os.path.join(ROOT, rel)):
            problems.append(f"version file missing: {rel}")
            continue
        found[rel] = read(rel)
    newest = latest_tag(tags)
    want = newest[1:] if newest.startswith("v") else None
    for rel, ver in found.items():
        if want is None:
            problems.append(f"{rel} says {ver}, but no release tag is "
                            "known to compare it with")
        elif ver != want:
            problems.append(f"{rel} says {ver}, the newest release is "
                            f"{newest}")
    return problems


def main() -> int:
    count = current_count()
    due = [v for n, v in THRESHOLDS if count >= n]
    # the highest reached threshold is the current version
    current_v = due[-1] if due else "pre-v1.0"
    # next unreached threshold
    nxt = None
    for n, v in THRESHOLDS:
        if count < n:
            nxt = (n, v)
            break

    tags, source = tag_set()
    print(f"ROLE COUNT: {count}")
    # The milestone is a floor, not the version: patch and early releases
    # (v1.2.0 was cut by hand at 38 roles) sit above it, so print both.
    print(f"MILESTONE REACHED: {current_v}  "
          f"(released version: {latest_tag(tags)}, source: {source})")
    if nxt:
        early = bool(tags) and nxt[1] in tags
        print(f"NEXT MILESTONE: {nxt[1]} at {nxt[0]} roles "
              f"({nxt[0] - count} to go)"
              + ("; already tagged early, so it will not be cut again"
                 if early else ""))
    else:
        print("ALL MILESTONES REACHED")

    if "--check" not in sys.argv:
        return 0

    # The law is about the CURRENT milestone: you must have a tag for the
    # highest threshold crossed. Demanding a retroactive tag for every
    # earlier milestone is wrong — v1.0.0 was superseded by v1.1.0, so its
    # absent tag is history, not a breach.
    reached = [(n, v) for n, v in THRESHOLDS if count >= n]
    current = reached[-1][1] if reached else None
    if not current:
        print("release-law: OK — pre-v1.0, no milestone crossed")
        return 0
    if tags is None:
        print(f"RELEASE TAG SOURCE UNKNOWN: not a git work tree and "
              f"{TAG_ENV} unset — cannot verify {current} is tagged")
        return 1
    if not (current in tags or _tag_at_or_above(current, tags)):
        print(f"RELEASE DUE: {current} (highest milestone crossed, no tag)")
        return 1
    problems = version_problems(tags)
    if problems:
        for p in problems:
            print(f"VERSION DRIFT: {p}")
        print("release-law: FAIL — a version file names a version that is "
              "not the newest release; bump versions only in the tagged "
              "release commit")
        return 1
    print(f"release-law: OK — current milestone {current} is tagged, and "
          f"every version file says {latest_tag(tags)[1:]}")
    return 0


def _tag_at_or_above(version: str, tags: list[str]) -> bool:
    """True when a tag exists for this version OR any later one."""
    major, minor = _version_key(version)[:2] if _version_key(version) else (0, 0)
    for tag in tags:
        if not tag.startswith(TAG_PREFIXES):
            continue
        key = _version_key(tag)
        if len(key) >= 2 and (key[0], key[1]) >= (major, minor):
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
