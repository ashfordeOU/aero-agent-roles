#!/usr/bin/env python3
"""test_release_law.py — regression for release-law inside a tagless export.

Pitfall (2026-09-10): `make validate` runs INSIDE the `git archive` export
built by ops/automation/publish-public.sh. That export has no .git, so the
gate read an empty tag list and blocked the hourly publish with
"RELEASE DUE: v1.1.0 (highest milestone crossed, no tag)" — while the dev
repo had that exact tag. The publish job then fails every hour.

Law under test (tag source, in order):
  1. RELEASE_TAG env var (comma-separated) — used by the publish script,
     which resolves the real tags in the dev repo before exporting.
  2. `git tag -l` when the tree IS a work tree.
  3. Neither available -> the gate FAILS. Teeth are never removed: an
     unverifiable tag set must not pass as "tagged".

Usage: python3 scripts/test_release_law.py   (exit 0 = all pass)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "release-law.py")

fails: list[str] = []
temps: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"{'PASS' if ok else 'FAIL'}: {name}{suffix}")
    if not ok:
        fails.append(name)


def run(tree: str, release_tag: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("RELEASE_TAG", None)
    if release_tag is not None:
        env["RELEASE_TAG"] = release_tag
    copied = os.path.join(tree, "scripts", "release-law.py")
    return subprocess.run([sys.executable, copied, "--check"], cwd=tree,
                          env=env, capture_output=True, text=True)


def make_export(count: int) -> str:
    """Minimal tagless tree, exactly what `git archive` leaves on disk."""
    tree = tempfile.mkdtemp(prefix="release-law-export-")
    temps.append(tree)
    os.makedirs(os.path.join(tree, "scripts"))
    shutil.copy2(SCRIPT, os.path.join(tree, "scripts", "release-law.py"))
    with open(os.path.join(tree, "manifest.json"), "w") as fh:
        json.dump({"count": count}, fh)
    return tree


def make_git_repo(count: int, tag: str | None) -> str:
    tree = make_export(count)
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=tree, check=True)
    if tag:
        subprocess.run(["git", "tag", tag], cwd=tree, check=True)
    return tree


def main() -> int:
    if not os.path.exists(SCRIPT):
        print(f"FAIL: gate script missing at {SCRIPT}")
        return 1

    # 1. export + RELEASE_TAG: the publish path. Current milestone tagged -> pass.
    r = run(make_export(38), "v1.1.0")
    check("export + RELEASE_TAG=v1.1.0 (38 roles) -> OK", r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:120])

    # 2. export without any tag source -> must FAIL (unverifiable, not "tagged").
    r = run(make_export(38), None)
    check("export + no RELEASE_TAG -> FAIL (teeth kept)", r.returncode != 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    # 3. export + stale tag only: v1.1.0 is due and absent -> FAIL.
    r = run(make_export(38), "v1.0.0")
    check("export + RELEASE_TAG=v1.0.0 (v1.1.0 due) -> FAIL", r.returncode != 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    # 4. export at the v1.0.0 milestone -> pass on that tag.
    r = run(make_export(12), "v1.0.0")
    check("export + RELEASE_TAG=v1.0.0 (12 roles) -> OK", r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    # 5. multiple tags in the env list are all considered.
    r = run(make_export(38), "v1.0.0, v1.1.0")
    check("export + multi-tag RELEASE_TAG -> OK", r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    # 6. real work tree: git remains the source of truth (no env needed).
    r = run(make_git_repo(38, "v1.1.0"), None)
    check("git work tree, tag v1.1.0 -> OK (git source intact)",
          r.returncode == 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    # 7. git work tree with no tag at a crossed milestone -> FAIL.
    r = run(make_git_repo(38, None), None)
    check("git work tree, no tag (38 roles) -> FAIL", r.returncode != 0,
          r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

    for tree in temps:
        shutil.rmtree(tree, ignore_errors=True)

    if fails:
        print(f"\nrelease-law regression: {len(fails)} FAILED")
        return 1
    print("\nrelease-law regression: 7/7 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
