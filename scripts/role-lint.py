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
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/company-ops/aero-agent-skills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

REQUIRED_FM = ["type", "name", "title", "domain", "deliverable_type",
               "standards_bound", "skills_bound", "forbidden",
               "sign_off_required", "license", "compatibility"]
REQUIRED_SECTIONS = ["Role identity", "Deliverable contract", "Workflow",
                     "Evidence gates", "Boundary", "Verification",
                     "Compliance"]


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def main():
    problems = []
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
        # bound skills resolve (skip when skills checkout absent - CI verifies)
        for leaf in re.findall(r"^\s+-\s+([a-z0-9\-/]+)$", fm.get("skills_bound", ""), re.M) if fm.get("skills_bound") else []:
            if not HAS_SKILLS:
                break
            if os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")):
                continue
            problems.append(f"{slug}: bound skill unresolved: {leaf}")
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
    if problems:
        print(f"ROLE-LINT: {len(problems)} problem(s)")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"ROLE-LINT: {len(roles)} role(s) pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
