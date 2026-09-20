#!/usr/bin/env python3
"""role-lint.py — lint every role in roles/ against the ROLE-STANDARD.

Checks per role directory:
1. ROLE.md exists + frontmatter has required fields.
2. Every skills_bound path resolves to a SKILL.md in the pinned
   aero-agent-skills tree (or the manifest when --manifest).
3. templates/ has >=1 file (deliverable shape exists).
4. tests/ has a test file that imports cleanly.
5. SOURCES.md exists.
6. Forbidden lines contain the sign-off / no-approval boundary.
Exit 0 = all roles pass; exit 1 = failures (CI-blocking).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = os.path.join(ROOT, "roles")
# WHERE BOUND LEAVES ARE RESOLVED, AND WHY THERE IS NO SKIP
#
# This used to default to a path inside the developer's home directory and
# SKIP the binding check when that path was absent -- which is every
# environment except one machine: public CI, an npm tarball, a fresh clone.
# The skip was printed, which is better than silence and is still not a
# check. The default also shipped the developer's directory layout to every
# reader of this file, which is a thing this project does not do.
#
# Two sources now, in order, and no third outcome:
#   1. a LIVE corpus, handed in via AEROSKILLS_DEV -- the strongest answer,
#      because it is the corpus as it is right now;
#   2. the PINNED LEDGER at ops/contracts/skills-leaves.json -- a snapshot,
#      good everywhere, refreshed with `make skills-ledger SKILLS=<path>`.
# With neither, the lint FAILS. "I could not check" and "it checks out" must
# not print the same line.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", "").strip()
HAS_SKILLS = bool(AEROSKILLS) and os.path.isdir(
    os.path.join(AEROSKILLS, "skills"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import gen_skill_ledger
except ImportError:                     # pragma: no cover
    gen_skill_ledger = None


def _pinned_leaves():
    """The ledger, as a set, or None when there is no usable ledger."""
    if gen_skill_ledger is None:
        return None
    try:
        doc = gen_skill_ledger.load()
    except ValueError:
        return None
    return set(doc["leaves"]) if doc else None


PINNED = _pinned_leaves()

REQUIRED_FM = ["type", "name", "title", "domain", "deliverable_type",
               "standards_bound", "skills_bound", "forbidden",
               "sign_off_required", "license", "compatibility"]
REQUIRED_SECTIONS = ["Role identity", "Deliverable contract", "Workflow",
                     "Evidence gates", "Boundary", "Verification",
                     "Compliance"]


_LIST_ITEM = re.compile(r"^\s+-\s+(.+?)\s*$")
_TOP_KEY = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$")


def frontmatter(text):
    """Parse the frontmatter, keeping block lists as lists.

    The previous version split each line on ':' and kept the scalar, so a
    block list -- whose items are on following lines with no ':' -- collapsed
    to the empty string. Every consumer that iterated such a value iterated
    nothing, silently. Scalars still come back as strings so existing callers
    are unaffected; only list-valued keys change shape.
    """
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm = {}
    current = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _LIST_ITEM.match(line)
        if current is not None and item:
            fm[current].append(item.group(1).strip().strip("\"'"))
            continue
        key = _TOP_KEY.match(line)
        if key:
            k, v = key.group(1), key.group(2)
            if v == "":
                current = k
                fm[k] = []          # a block list may follow
            elif v.startswith("[") and v.endswith("]"):
                current = None
                fm[k] = [p.strip().strip("\"'")
                         for p in v[1:-1].split(",") if p.strip()]
            else:
                current = None
                fm[k] = v
    return fm


def bound_skills(fm):
    """The declared leaf slugs, whatever shape the frontmatter used."""
    value = fm.get("skills_bound")
    if isinstance(value, list):
        return [v for v in value if v]
    if isinstance(value, str) and value.strip():
        # tolerate the old single-scalar spelling
        return [value.strip()]
    return []


def main():
    problems = []
    checked = 0
    roles = sorted(d for d in os.listdir(ROLES) if os.path.isdir(os.path.join(ROLES, d)))
    for slug in roles:
        rdir = os.path.join(ROLES, slug)
        role_md = os.path.join(rdir, "ROLE.md")
        if not os.path.exists(role_md):
            problems.append(f"{slug}: ROLE.md missing")
            continue
        text = open(role_md).read()
        fm = frontmatter(text)
        for f in REQUIRED_FM:
            if f not in fm:
                problems.append(f"{slug}: frontmatter missing '{f}'")
        for sec in REQUIRED_SECTIONS:
            if sec not in text:
                problems.append(f"{slug}: section '{sec}' missing")
        if fm.get("type") != "role":
            problems.append(f"{slug}: type != role")
        # Bound skills must resolve -- against a live corpus if one was
        # handed in, otherwise against the pinned ledger. There is no skip.
        declared = bound_skills(fm)
        if not declared:
            problems.append(f"{slug}: declares no bound skills")
        elif HAS_SKILLS:
            for leaf in declared:
                if os.path.exists(os.path.join(AEROSKILLS, "skills", leaf,
                                               "SKILL.md")):
                    continue
                problems.append(f"{slug}: bound skill unresolved: {leaf}")
            checked += len(declared)
        elif PINNED:
            for leaf in declared:
                if leaf in PINNED:
                    continue
                problems.append(
                    f"{slug}: bound skill unresolved against the pinned "
                    f"ledger ({len(PINNED)} leaves): {leaf}")
            checked += len(declared)
        else:
            problems.append(
                f"{slug}: cannot resolve {len(declared)} bound skill(s) -- "
                f"no live corpus (AEROSKILLS_DEV) and no usable ledger at "
                f"ops/contracts/skills-leaves.json. Refusing to pass a check "
                f"that examined nothing.")
        if not os.path.isdir(os.path.join(rdir, "templates")) or not any(
                f.endswith(".md") for f in os.listdir(os.path.join(rdir, "templates"))):
            problems.append(f"{slug}: templates/ missing deliverable")
        if not os.path.isdir(os.path.join(rdir, "tests")) or not any(
                f.startswith("test_") for f in os.listdir(os.path.join(rdir, "tests"))):
            problems.append(f"{slug}: tests/ missing")
        # 100% standard: executable core + cli + core test present
        if not os.path.isdir(os.path.join(rdir, "core")) or not any(
                f.endswith("_core.py") for f in os.listdir(os.path.join(rdir, "core"))):
            problems.append(f"{slug}: core/ engine missing (100% standard)")
        if not os.path.exists(os.path.join(rdir, "cli.py")):
            problems.append(f"{slug}: cli.py missing (100% standard)")
        core_tests = [f for f in os.listdir(os.path.join(rdir, "tests"))
                      if f.startswith("test_") and f.endswith("_core.py")] \
            if os.path.isdir(os.path.join(rdir, "tests")) else []
        if not core_tests:
            problems.append(f"{slug}: core test missing (100% standard)")
        if not os.path.exists(os.path.join(rdir, "SOURCES.md")):
            problems.append(f"{slug}: SOURCES.md missing")
        low = text.lower()
        for phrase in ["sign_off_required: true", "forbidden"]:
            if phrase not in low:
                problems.append(f"{slug}: boundary phrase missing: {phrase}")
        # MCP access policy: optional. Absent = offline-only (the 100%
        # deterministic default). Present must be a well-formed allow list:
        #   mcp_allowed:          # optional; omit for offline-only roles
        #     - <server>:<read|write>     e.g. aero-agent-skills:read
        #     - <server>:<read|write>     e.g. github:write
        # Any server NOT listed is blocked for that role. mcp_blocked is a
        # hard deny list that wins over mcp_allowed.
        fm_block = re.match(r"^---\n(.*?)\n---", text, re.S)
        raw_fm = fm_block.group(1) if fm_block else ""
        mcp_allowed = bool(re.search(r"^mcp_allowed:", raw_fm, re.M))
        mcp_blocked = bool(re.search(r"^mcp_blocked:", raw_fm, re.M))
        if mcp_allowed:
            entries = re.findall(r"^\s+-\s+([a-z0-9][a-z0-9\-_]*):(read|write)$", raw_fm, re.M)
            if not entries:
                problems.append(f"{slug}: mcp_allowed must list '<server>:<read|write>' entries (e.g. 'aero-agent-skills:read')")
            if mcp_blocked:
                # only lines after the mcp_blocked: header, before the next top-level key
                m = re.search(r"^mcp_blocked:(.*?)(?=^[a-z_]+:|\Z)", raw_fm, re.M | re.S)
                blocked = re.findall(r"^\s+-\s+([a-z0-9][a-z0-9\-_]*)", m.group(1), re.M) if m else []
                if not blocked:
                    problems.append(f"{slug}: mcp_blocked must list server names")
                allow_names = {e[0] for e in entries}
                for b in blocked:
                    if b in allow_names:
                        problems.append(f"{slug}: mcp_blocked contradicts mcp_allowed for '{b}'")
        if mcp_blocked and not mcp_allowed:
            problems.append(f"{slug}: mcp_blocked without mcp_allowed is redundant (absent mcp_allowed already blocks all); remove or add an allow list")
        # no-approval boundary: in the role body OR its deliverable template
        tdir = os.path.join(rdir, "templates")
        template_text = ""
        if os.path.isdir(tdir):
            for tf in os.listdir(tdir):
                if tf.endswith(".md"):
                    template_text += open(os.path.join(tdir, tf)).read()
        combined = re.sub(r"\s+", " ", (text + "\n" + template_text).lower())
        if not any(p in combined for p in
                   ["not an approval", "not a finding", "not an approval document",
                    "not a certification", "supplier-approval decision",
                    "not launch readiness", "not flight software release",
                    "not a clearance", "not production release",
                    "or an approval"]):
            problems.append(f"{slug}: no-approval boundary missing")
    # A pass must state its denominator, and WHICH corpus answered.
    # "0 bindings resolved against nothing" and "597 bindings resolved
    # against 3189 leaves" are different outcomes and used to print the
    # same line.
    if HAS_SKILLS:
        against = "a live skills corpus"
    elif PINNED:
        against = "the pinned ledger (%d leaves)" % len(PINNED)
    else:
        against = "NOTHING"
    if problems:
        print(f"ROLE-LINT: {len(problems)} problem(s)")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"ROLE-LINT: {len(roles)} role(s) pass; "
          f"{checked} binding(s) resolved against {against}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
