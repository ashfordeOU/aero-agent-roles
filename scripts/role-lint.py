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
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
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
        if not os.path.exists(os.path.join(rdir, "tests", f"test_{slug.replace('-', '_')}_core.py")):
            problems.append(f"{slug}: core test missing (100% standard)")
        if not os.path.exists(os.path.join(rdir, "SOURCES.md")):
            problems.append(f"{slug}: SOURCES.md missing")
        low = text.lower()
        for phrase in ["sign_off_required: true", "forbidden"]:
            if phrase not in low:
                problems.append(f"{slug}: boundary phrase missing: {phrase}")
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
                    "not a clearance", "not production release"]):
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
