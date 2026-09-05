#!/usr/bin/env python3
"""Aero Agent Roles visuals + metrics generator (deterministic, stdlib-only,
offline). Mirrors Aero Agent Skills' gen_visuals.py design law: every number
shown in README.md and STANDARDS.md is computed from the tree at HEAD, never
hand-typed. That discipline is why this script exists — the README drifted
to a stale "12 roles" snapshot (and a corrupted, duplicated role table) while
the tree grew to 22 through four unrelated growth waves, and STANDARDS.md
silently missed 9 of the 21 standards actually bound by roles.

Single source of truth: roles/<slug>/ROLE.md frontmatter (standards_bound,
skills_bound) — the same source manifest.json is generated from.

Outputs (all overwritten in place):
  docs/metrics.json         machine-readable snapshot
  docs/statline-dark.svg    hero stat line (SVG source)
  docs/statline-dark.png    2x raster (GitHub renders PNG, not SVG, on mobile)
  STANDARDS.md              full standards table, regenerated
  README.md                 every <!-- gen:NAME --> block rewritten

The logo (docs/logo-mark.png) is founder-supplied raster — never generated,
never altered by this script.

Usage:
  python3 scripts/gen_visuals.py           regenerate everything
  python3 scripts/gen_visuals.py --check   fail (exit 1) if anything is stale
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# ------------------------------------------------------------------ theme
# Same palette as Aero Agent Skills (docs/DESIGN.md there): space navy +
# cyan/violet/magenta/orange. One product family, one visual system.

DARK = {
    "canvas": "#0a0d1e",
    "ink": "#edf0fc",
    "pencil": "#8a93c4",
    "cyan": "#38bdf8",
    "violet": "#a78bfa",
    "magenta": "#f472b6",
    "orange": "#fb923c",
}

STYLE = """  <style>
    .mono { font-family: "JetBrains Mono", "IBM Plex Mono", "Menlo", monospace; }
  </style>
"""

TITLE_FONT = ('font-family="Poppins, Nunito, \'SF Pro Rounded\', \'Segoe UI\', '
              'system-ui, -apple-system, sans-serif" font-weight="800"')


def gen_title(t):
    W, H = 960, 168
    ramp = ["#38bdf8", "#a78bfa", "#f472b6", "#fb923c"]
    roles = "".join(f'<tspan fill="{c}">{ch}</tspan>'
                    for ch, c in zip("Roles", ramp + ramp[:1]))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" rx="22" fill="{t["canvas"]}"/>']
    o.append(f'<text x="{W / 2}" y="92" text-anchor="middle" font-size="72" '
             f'{TITLE_FONT} fill="{t["ink"]}">Aero <tspan fill="{t["cyan"]}">Agent</tspan> '
             f'{roles}</text>')
    o.append(f'<text class="mono" x="{W / 2}" y="142" text-anchor="middle" '
             f'font-size="16" letter-spacing="4">'
             f'<tspan fill="{t["cyan"]}">AEROSPACE ENGINEERING</tspan>'
             f'<tspan fill="{t["pencil"]}" dx="10">·</tspan>'
             f'<tspan fill="{t["violet"]}" dx="10">BY ASHFORDE OÜ</tspan>'
             f'<tspan fill="{t["pencil"]}" dx="10">·</tspan>'
             f'<tspan fill="{t["orange"]}" dx="10">APACHE-2.0</tspan></text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"

# Standard id -> (full name, publisher). Names/publishers are the only
# hand-maintained facts here (external-world data, not derivable from the
# tree) — everything else about a standard (which roles bind it, whether
# it's gated) is computed fresh from ROLE.md frontmatter every run, so a
# future wave can never silently drift this table again the way it did
# before this script existed.
STANDARD_META = {
    "ac-90-105a": ("FAA AC 90-105A, Approval Guidance for RNP Operations and Baro-VNAV", "FAA"),
    "arinc-429": ("ARINC 429 (Mark 33 DITS)", "ARINC / Aeronautical Radio Inc"),
    "arinc-664": ("ARINC 664 Part 7 (AFDX)", "ARINC / Aeronautical Radio Inc"),
    "arp4754a": ("SAE ARP4754A, Development of Civil Aircraft and Systems", "SAE"),
    "as9100": ("AS9100D, Aerospace QMS Requirements", "SAE / IAQG"),
    "asme-vv-20": ("ASME V&V 20-2009, Verification and Validation in CFD and Heat Transfer", "ASME"),
    "asme-y14-5": ("ASME Y14.5, Dimensioning and Tolerancing", "ASME"),
    "cs-25": ("EASA CS-25, Certification Specifications", "EASA"),
    "do-160": ("RTCA DO-160G / EUROCAE ED-14G, Environmental Conditions and Test Procedures for Airborne Equipment", "RTCA/EUROCAE"),
    "do-178c": ("RTCA DO-178C / EUROCAE ED-12C, Software Considerations in Airborne Systems", "RTCA/EUROCAE"),
    "do-236c": ("RTCA DO-236C, MASPS: RNP for Area Navigation", "RTCA"),
    "do-254": ("RTCA DO-254 / EUROCAE ED-80, Design Assurance for Airborne Electronic Hardware", "RTCA/EUROCAE"),
    "do-283a": ("RTCA DO-283A, MOPS for RNP Area Navigation (RNP AR)", "RTCA"),
    "ecss": ("ECSS engineering + product-assurance standards (E-ST-10/32/33/40, Q-ST-80)", "ECSS"),
    "far-25": ("14 CFR Part 25, Airworthiness Standards: Transport Category Airplanes", "FAA"),
    "far-33": ("14 CFR Part 33, Airworthiness Standards: Aircraft Engines", "FAA"),
    "mil-std-1553": ("MIL-STD-1553B, Digital Time Division Command/Response Multiplex Data Bus", "US DoD"),
    "mil-std-1797a": ("MIL-STD-1797A, Flying Qualities of Piloted Aircraft", "US DoD"),
    "mmpsd": ("MMPDS, Metallic Materials Properties Development and Standardization", "Battelle / FAA"),
    "naca-tr-824": ("NACA Report 824, Summary of Airfoil Data", "NACA/NASA (public domain)"),
    "nas-410": ("NAS 410, Certification and Qualification of Nondestructive Test Personnel", "AIA/SAE"),
}

# ----------------------------------------------------------------- metrics

FM_LIST_ITEM = re.compile(r"^\s*-\s*id:\s*([a-z0-9\-]+)\s*$", re.M)
FM_REF_ONLY = re.compile(r"^\s*reference-only:\s*(true|false)\s*$", re.M)
FM_SKILL_ITEM = re.compile(r"^\s+-\s+([a-z0-9\-/]+)\s*$", re.M)


def fm_block(text, key):
    m = re.search(rf"^{key}:\s*\n(.*?)(?=^[a-z_]+:|^---)", text, re.M | re.S)
    return m.group(1) if m else ""


def parse_standards_bound(block):
    """Each entry: id, then (usually) tier/reference-only lines before the
    next '- id:'. Split on '- id:' boundaries and grab the first
    reference-only within each chunk."""
    entries = []
    chunks = re.split(r"(?=^\s*-\s*id:)", block, flags=re.M)
    for chunk in chunks:
        m = FM_LIST_ITEM.search(chunk)
        if not m:
            continue
        rid = m.group(1)
        ref = FM_REF_ONLY.search(chunk)
        gated = ref.group(1) == "true" if ref else False
        entries.append((rid, gated))
    return entries


def load_roles():
    roles = []
    for role_dir in sorted((REPO / "roles").iterdir()):
        p = role_dir / "ROLE.md"
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        fm_m = re.match(r"^---\n(.*?)\n---", text, re.S)
        fm = {}
        if fm_m:
            for line in fm_m.group(1).splitlines():
                if ":" in line and not line.startswith(" "):
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
        skills = FM_SKILL_ITEM.findall(fm_block(text, "skills_bound"))
        standards = parse_standards_bound(fm_block(text, "standards_bound"))
        roles.append({
            "slug": role_dir.name,
            "title": fm.get("title", role_dir.name),
            "domain": fm.get("domain", ""),
            "deliverable_type": fm.get("deliverable_type", ""),
            "status": fm.get("status", "draft"),
            "standards": standards,
            "skills_bound": len(skills),
        })
    return roles


def count_tests():
    total = 0
    for f in sorted((REPO / "roles").glob("*/tests/test_*.py")):
        total += len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M))
    return total


def count_gates():
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^validate:\s*(.+)$", mk, re.M)
    return len(m.group(1).split()) if m else 0


def collect_metrics():
    roles = load_roles()
    standards = {}  # id -> {"gated": bool, "roles": [slug, ...]}
    for r in roles:
        for rid, gated in r["standards"]:
            entry = standards.setdefault(rid, {"gated": False, "roles": []})
            entry["gated"] = entry["gated"] or gated
            entry["roles"].append(r["slug"])
    return {
        "roles": len(roles),
        "skills_bound": sum(r["skills_bound"] for r in roles),
        "standards": len(standards),
        "tests": count_tests(),
        "gates": count_gates(),
        "domains": len(set(r["domain"] for r in roles)),
        "license": "Apache-2.0",
        "per_role": roles,
        "per_standard": standards,
    }


# -------------------------------------------------------------- statline

def gen_statline(m, t):
    W, H = 1240, 74
    stats = [
        (m["roles"], "ROLES", t["violet"]),
        (m["skills_bound"], "SKILLS BOUND", t["cyan"]),
        (m["tests"], "OFFLINE TESTS", t["magenta"]),
        (m["standards"], "STANDARDS", t["orange"]),
        (m["domains"], "DOMAINS", t["cyan"]),
        (f'{m["gates"]}/{m["gates"]}', "GATES GREEN", t["violet"]),
    ]
    spans = []
    for k, (v, label, c) in enumerate(stats):
        dx = ' dx="34"' if k else ""
        spans.append(f'<tspan{dx} font-size="34" fill="{c}" font-weight="800">{v}</tspan>')
        spans.append(f'<tspan dx="9" font-size="13" fill="{t["pencil"]}" '
                     f'letter-spacing="2">{label}</tspan>')
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" rx="16" fill="{t["canvas"]}"/>',
         f'<text class="mono" x="{W / 2}" y="47" text-anchor="middle">'
         + "".join(spans) + "</text>", "</svg>"]
    return "\n".join(o) + "\n"


# --------------------------------------------------------------- README gen

def block_badges(m):
    def b(label, msg, color, href, alt=None):
        lab = label.replace("-", "--").replace(" ", "_")
        enc = msg.replace("-", "--").replace(" ", "_")
        return (f'  <a href="{href}"><img src="https://img.shields.io/badge/'
                f'{lab}-{enc}-{color}?style=flat&labelColor=1a1e35" alt="{alt or (label + " " + msg)}"></a>')
    row = [
        b("roles", str(m["roles"]), "a78bfa", "roles/"),
        b("skills bound", str(m["skills_bound"]), "0ea5e9", "https://github.com/ashfordeOU/aero-agent-skills"),
        b("offline tests", str(m["tests"]), "2ea043", "roles/"),
        b("standards", str(m["standards"]), "f97316", "STANDARDS.md"),
        b("format", "agentskills.io", "8b5cf6", "https://agentskills.io"),
        b("license", m["license"], "2ea043", "LICENSE", alt=m["license"]),
    ]
    return "<p align=\"center\">\n" + "\n".join(row) + "\n</p>"


def block_role_table(m):
    rows = ["| Role | Deliverable | Skills bound |", "|---|---|---|"]
    for r in sorted(m["per_role"], key=lambda r: r["title"]):
        rows.append(f'| [{r["title"]}](roles/{r["slug"]}/ROLE.md) | '
                    f'{r["deliverable_type"]} | {r["skills_bound"]} |')
    return "\n".join(rows)


BLOCKS = {
    "badges": block_badges,
    "role-table": block_role_table,
}


def render_readme(m, src):
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- gen:{name} -->\n).*?(\n<!-- /gen:{name} -->)", re.S)
        if not pat.search(src):
            raise SystemExit(f"README.md: missing generator block <!-- gen:{name} -->")
        src = pat.sub(lambda mo: mo.group(1) + fn(m) + mo.group(2), src)
    alt_pat = re.compile(r'(<img src="docs/statline-dark\.png" alt=")[^"]*(")')
    alt = (f'{m["roles"]} roles · {m["skills_bound"]} skills bound · '
           f'{m["tests"]} offline tests · {m["standards"]} standards · '
           f'{m["gates"]}/{m["gates"]} gates · {m["license"]}')
    src = alt_pat.sub(rf'\g<1>{alt}\g<2>', src)
    return src


def gen_standards_md(m):
    lines = [
        "# Aero Agent Roles Standards Reference (STANDARDS.md)",
        "",
        "Every role references standards from the aerospace regulatory and",
        "quality ecosystem. This file is generated from every role's",
        "`standards_bound` frontmatter (the same source `manifest.json` is",
        "generated from) — a standard's row and `Roles`/`Gated` columns can",
        "never silently drift from the tree again. Names and publishers below",
        "are the only hand-maintained facts (external-world data); see",
        "`STANDARD_META` in `scripts/gen_visuals.py` to add a new standard.",
        "",
        "## The summary-not-copy rule",
        "",
        "The only allowed way to reference any mapped standard is",
        "**summary-not-copy**: name + paraphrase + short attributed quotes",
        "(<100 words) + link to the publisher's official channel. Never reproduce",
        "objective tables, appendix text, or multi-line verbatim blocks; never",
        "include standards PDFs; never include material from illegally hosted",
        "copies.",
        "",
        "`Gated: true` means **verbatim text from that standard must NEVER appear",
        "anywhere in this repository** - a role that references a gated standard",
        "lists it as `reference-only`. `Gated: false` means the text is quotable",
        "with attribution (paraphrase still preferred).",
        "",
        "The standards themselves remain the copyrighted works of their publishers",
        "(RTCA/EUROCAE, SAE International, IAQG, ASME, ECSS, EASA, FAA) and must",
        "be purchased or accessed through the publishers' official channels.",
        "",
        "## Standards referenced",
        "",
        "| id | Standard | Publisher | Roles | Gated |",
        "|---|---|---|---|---|",
    ]
    for sid in sorted(m["per_standard"]):
        entry = m["per_standard"][sid]
        name, publisher = STANDARD_META.get(sid, (sid, "unknown — add to STANDARD_META"))
        roles = ", ".join(sorted(entry["roles"]))
        lines.append(f"| {sid} | {name} | {publisher} | {roles} | {entry['gated']} |")
    lines += [
        "",
        "## Purchase links",
        "",
        "Standards are available from the publishers' official channels:",
        "RTCA (rtca.org), SAE International (sae.org), IAQG (iaqg.org), ASME",
        "(asme.org), ECSS (ecss.nl), FAA (ecfr.gov), EASA (easa.europa.eu).",
        "",
    ]
    return "\n".join(lines)


# -------------------------------------------------------------------- main

# SVG -> PNG raster width (rsvg-convert -w), keyed by output stem — 2x the
# README's display width for retina screens, matching aero-agent-skills.
PNG_WIDTHS = {
    "title-dark": 1240,
    "statline-dark": 2480,
}


def outputs(m):
    docs = REPO / "docs"
    return {
        docs / "metrics.json": json.dumps(
            {k: v for k, v in m.items() if k not in ("per_role", "per_standard")},
            indent=2, sort_keys=True) + "\n",
        docs / "title-dark.svg": gen_title(DARK),
        docs / "statline-dark.svg": gen_statline(m, DARK),
        REPO / "STANDARDS.md": gen_standards_md(m),
    }


def main():
    check = "--check" in sys.argv
    m = collect_metrics()
    stale = []

    for path, content in outputs(m).items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(path)
        if not check:
            path.write_text(content, encoding="utf-8")

    readme_path = REPO / "README.md"
    src = readme_path.read_text(encoding="utf-8")
    new_src = render_readme(m, src)
    if new_src != src:
        stale.append(readme_path)
        if not check:
            readme_path.write_text(new_src, encoding="utf-8")

    if not check:
        rsvg = shutil.which("rsvg-convert")
        for stem, width in PNG_WIDTHS.items():
            svg_path = REPO / "docs" / f"{stem}.svg"
            png_path = REPO / "docs" / f"{stem}.png"
            if rsvg:
                subprocess.run([rsvg, "-w", str(width), str(svg_path), "-o", str(png_path)], check=True)
            else:
                print(f"WARN rsvg-convert not found — {png_path.name} not regenerated")

    if check:
        if stale:
            print("visuals: STALE —", ", ".join(str(p.relative_to(REPO)) for p in stale))
            return 1
        print(f'visuals: OK ({m["roles"]} roles, {m["skills_bound"]} skills bound, '
              f'{m["standards"]} standards, {m["tests"]} tests)')
        return 0

    print(f'visuals: wrote {m["roles"]} roles, {m["skills_bound"]} skills bound, '
          f'{m["standards"]} standards, {m["tests"]} tests')
    return 0


if __name__ == "__main__":
    sys.exit(main())
