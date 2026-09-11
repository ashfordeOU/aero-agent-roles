#!/usr/bin/env python3
"""test_growth_guard.py — fail-first test for ops/automation/growth-guard.sh.

WHY (VEDA-0053, 2026-09-11): the guard exists because the committed coverage
matrix and generated visuals rot silently at a clean HEAD whenever the
AeroSkills leaf count moves (796 -> 974 leaves in nine hours, twice in one
day). The test must prove BOTH halves on a real tree: the guard is RED when a
generated stat is stale, and GREEN when it is current. It runs on a throwaway
git worktree, so the live tree is never touched or dirtied.

Run: python3 scripts/test_growth_guard.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = "ops/automation/growth-guard.sh"

PASSED = []
FAILED = []


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    print(f"{'OK  ' if ok else 'FAIL'} {name}{(': ' + detail) if detail else ''}")


def guard(root):
    """Run the guard (from the LIVE repo) against the given tree root."""
    return run(["bash", os.path.join(REPO, GUARD), root], REPO)


def main():
    tmp = tempfile.mkdtemp(prefix="growth-guard-test-")
    worktree = os.path.join(tmp, "wt")
    live_before = run(["git", "status", "--porcelain"], REPO).stdout
    added = False
    try:
        r = run(["git", "worktree", "add", "--detach", worktree, "HEAD"], REPO)
        if r.returncode != 0:
            print("cannot create worktree:", r.stderr.strip())
            return 2
        added = True

        # Case 0 — a fresh worktree at HEAD passes the guard.
        r = guard(worktree)
        check("GREEN: clean HEAD passes the guard",
              r.returncode == 0 and "PASS growth-guard" in r.stdout,
              f"rc={r.returncode} out={r.stdout.strip()!r} err={r.stderr.strip()!r}")

        # Case 1 — a stale coverage matrix must be caught, loudly.
        matrix = os.path.join(worktree, "docs", "COVERAGE-MATRIX.md")
        with open(matrix) as fh:
            original = fh.read()
        with open(matrix, "w") as fh:
            fh.write(original.replace("AeroSkills leaves: **", "AeroSkills leaves: **1", 1))
        r = guard(worktree)
        check("RED: stale coverage matrix blocks",
              r.returncode != 0 and "FAIL growth-guard" in r.stderr
              and "coverage-matrix.py" in r.stderr,
              f"rc={r.returncode} err={r.stderr.strip().splitlines()[0] if r.stderr.strip() else ''!r}")
        run(["git", "checkout", "--", "docs/COVERAGE-MATRIX.md"], worktree)

        # Case 2 — a stale generated visual must be caught too. docs/metrics.json
        # is written byte-for-byte by gen_visuals.py, so one extra byte is a
        # guaranteed mismatch whatever the current leaf count is.
        metrics = os.path.join(worktree, "docs", "metrics.json")
        with open(metrics) as fh:
            original_metrics = fh.read()
        with open(metrics, "w") as fh:
            fh.write(original_metrics + "\n")
        r = guard(worktree)
        check("RED: stale generated visual blocks",
              r.returncode != 0 and "FAIL growth-guard" in r.stderr
              and "gen_visuals.py" in r.stderr,
              f"rc={r.returncode} err={r.stderr.strip().splitlines()[0] if r.stderr.strip() else ''!r}")
        run(["git", "checkout", "--", "docs/metrics.json"], worktree)

        # Case 3 — the guard is non-mutating: a red run leaves the tree clean.
        with open(matrix, "w") as fh:
            fh.write(original.replace("AeroSkills leaves: **", "AeroSkills leaves: **1", 1))
        run(["bash", GUARD], worktree)
        st = run(["git", "status", "--porcelain"], worktree)
        dirty = [ln for ln in st.stdout.splitlines() if "COVERAGE-MATRIX" not in ln]
        check("CLEAN: a red run mutates nothing but the file under test",
              dirty == [], f"unexpected dirt={dirty}")

        # Case 4 — the live repo is untouched by this test (same dirt as when
        # the test started: the worktree work happens on the throwaway copy).
        st = run(["git", "status", "--porcelain"], REPO)
        check("ISOLATION: live repo working tree unchanged",
              st.stdout == live_before,
              f"before={live_before!r} after={st.stdout!r}")
    finally:
        if added:
            run(["git", "worktree", "remove", "--force", worktree], REPO)
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(PASSED)} OK, {len(FAILED)} FAILED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
