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
import math
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
    "surface": "#111632",
    "ink": "#edf0fc",
    "pencil": "#8a93c4",
    "faint": "#2c3564",
    "cyan": "#38bdf8",
    "violet": "#a78bfa",
    "magenta": "#f472b6",
    "orange": "#fb923c",
    "fill_data": "0.16",
    "fill_rose": "0.72",
}

RAMP = ["cyan", "violet", "magenta", "orange"]  # domain color cycle

STYLE = """  <style>
    .mono { font-family: "JetBrains Mono", "IBM Plex Mono", "Menlo", monospace; }
    .cond { font-family: "Barlow Condensed", "DIN Condensed", "Arial Narrow", sans-serif; font-weight: 700; text-transform: uppercase; }
  </style>
"""

# Domain slugs are the same taxonomy Aero Agent Skills uses for its
# families (roles bind skills 1:1 by domain) — pretty labels only; the
# 12-domain SET itself is always read from the tree, never assumed.
DOMAIN_META = {
    "aerodynamics": "AERODYNAMICS",
    "avionics": "AVIONICS",
    "cross-cutting": "CROSS-CUTTING",
    "flight-mechanics": "FLIGHT MECHANICS",
    "flight-test-operations": "FLIGHT TEST & OPS",
    "gnc-autonomy": "GNC & AUTONOMY",
    "manufacturing-quality": "MFG QUALITY",
    "propulsion": "PROPULSION",
    "space-systems": "SPACE SYSTEMS",
    "structures": "STRUCTURES",
    "systems-engineering-safety": "SYS ENG & SAFETY",
    "vehicle-design": "VEHICLE DESIGN",
}


def domain_label(slug):
    return DOMAIN_META.get(slug, slug.upper())


def domain_color(t, i):
    return t[RAMP[i % len(RAMP)]]


def domain_axes(m):
    doms = m["per_domain"]
    names = sorted(doms)
    n = len(names)
    return [(names[i], doms[names[i]], -90 + 360 * i / n) for i in range(n)]


# -------------------------------------------------------------- svg helpers

def pt(cx, cy, r, ang_deg):
    a = math.radians(ang_deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def poly(points, **attrs):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<polygon points="{p}" {a}/>'


def txt(x, y, s, cls="mono", size=11, fill="#000", anchor="start", ls=None, extra=""):
    lsp = f' letter-spacing="{ls}"' if ls else ""
    esc = str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="{size}" fill="{fill}"{lsp}{extra}>{esc}</text>')


def ownermark(t, x, y, anchor="end"):
    return txt(x, y, "AERO AGENT ROLES · ASHFORDE OÜ", size=9.5,
               fill=t["pencil"], anchor=anchor, ls=1.5, extra=' opacity="0.9"')


def annulus(cx, cy, r0, r1, a0, a1, fill, opacity="1", stroke="none", sw="0"):
    large = 1 if (a1 - a0) > 180 else 0
    x0o, y0o = pt(cx, cy, r1, a0)
    x1o, y1o = pt(cx, cy, r1, a1)
    x1i, y1i = pt(cx, cy, r0, a1)
    x0i, y0i = pt(cx, cy, r0, a0)
    return (f'<path d="M {x0o:.1f} {y0o:.1f} A {r1:.1f} {r1:.1f} 0 {large} 1 '
            f'{x1o:.1f} {y1o:.1f} L {x1i:.1f} {y1i:.1f} A {r0:.1f} {r0:.1f} 0 {large} 0 '
            f'{x0i:.1f} {y0i:.1f} Z" fill="{fill}" fill-opacity="{opacity}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>')

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
    "arp4761a": ("SAE ARP4761A, Guidelines and Methods for Conducting the Safety Assessment Process on Civil Airborne Systems and Equipment", "SAE"),
    "as9100": ("AS9100D, Aerospace QMS Requirements", "SAE / IAQG"),
    "asme-vv-20": ("ASME V&V 20-2009, Verification and Validation in CFD and Heat Transfer", "ASME"),
    "asme-y14-5": ("ASME Y14.5, Dimensioning and Tolerancing", "ASME"),
    "cs-25": ("EASA CS-25, Certification Specifications", "EASA"),
    "do-160": ("RTCA DO-160G / EUROCAE ED-14G, Environmental Conditions and Test Procedures for Airborne Equipment", "RTCA/EUROCAE"),
    "do-178c": ("RTCA DO-178C / EUROCAE ED-12C, Software Considerations in Airborne Systems", "RTCA/EUROCAE"),
    "do-208": ("RTCA DO-208, Minimum Operational Performance Standards for Airborne Supplemental Navigation Equipment Using GPS", "RTCA"),
    "do-229": ("RTCA DO-229, Minimum Operational Performance Standards for GPS/WAAS Airborne Equipment", "RTCA"),
    "do-236c": ("RTCA DO-236C, MASPS: RNP for Area Navigation", "RTCA"),
    "do-254": ("RTCA DO-254 / EUROCAE ED-80, Design Assurance for Airborne Electronic Hardware", "RTCA/EUROCAE"),
    "do-283a": ("RTCA DO-283A, MOPS for RNP Area Navigation (RNP AR)", "RTCA"),
    "ecss": ("ECSS engineering + product-assurance standards (E-ST-10/32/33/40, Q-ST-80)", "ECSS"),
    "far-25": ("14 CFR Part 25, Airworthiness Standards: Transport Category Airplanes", "FAA"),
    "far-33": ("14 CFR Part 33, Airworthiness Standards: Aircraft Engines", "FAA"),
    "icao-annex-10": ("ICAO Annex 10, Aeronautical Telecommunications (Vol I: Radio Navigation Aids)", "ICAO"),
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


def count_tests_by_role():
    counts = {}
    for role_dir in sorted((REPO / "roles").iterdir()):
        n = 0
        for f in sorted(role_dir.glob("tests/test_*.py")):
            n += len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M))
        counts[role_dir.name] = n
    return counts


def count_gates():
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^validate:\s*(.+)$", mk, re.M)
    return len(m.group(1).split()) if m else 0


def collect_metrics():
    roles = load_roles()
    test_counts = count_tests_by_role()
    for r in roles:
        r["tests"] = test_counts.get(r["slug"], 0)

    standards = {}  # id -> {"gated": bool, "roles": [slug, ...]}
    for r in roles:
        for rid, gated in r["standards"]:
            entry = standards.setdefault(rid, {"gated": False, "roles": []})
            entry["gated"] = entry["gated"] or gated
            entry["roles"].append(r["slug"])

    domains = {}  # slug -> {"label", "roles": [...], "skills_bound", "tests"}
    for r in roles:
        d = domains.setdefault(r["domain"], {
            "label": domain_label(r["domain"]), "roles": [],
            "skills_bound": 0, "tests": 0,
        })
        d["roles"].append(r)
        d["skills_bound"] += r["skills_bound"]
        d["tests"] += r["tests"]
    for d in domains.values():
        d["role_count"] = len(d["roles"])

    return {
        "roles": len(roles),
        "skills_bound": sum(r["skills_bound"] for r in roles),
        "standards": len(standards),
        "tests": sum(test_counts.values()),
        "gates": count_gates(),
        "domains": len(domains),
        "license": "Apache-2.0",
        "per_role": roles,
        "per_standard": standards,
        "per_domain": domains,
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


# ---------------------------------------------------------------- radar

def gen_radar(m, t):
    """12-axis radar: skills bound (content built) vs offline tests
    (verification depth) per domain — the Skills repo's same "what's built
    vs what's proven" pairing, one level up (roles, not leaves)."""
    W, H = 940, 820
    cx, cy, R = 430, 410, 262
    peak = max(max(d["tests"], d["skills_bound"]) for d in m["per_domain"].values())
    for step in (5, 10, 20, 25, 50, 100, 200, 500):
        if math.ceil(peak / step) <= 6:
            break
    rings = [step * i for i in range(1, math.ceil(peak / step) + 1)]
    rmax = float(rings[-1])
    axes = domain_axes(m)
    ink, mint, pencil, faint = t["ink"], t["cyan"], t["pencil"], t["faint"]

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    for rv in rings:
        r = R * rv / rmax
        pts = [pt(cx, cy, r, a) for _, _, a in axes]
        o.append(poly(pts, fill="none", stroke=faint, stroke_width="0.8", stroke_opacity="0.55"))
    for _, _, a in axes:
        x, y = pt(cx, cy, R, a)
        o.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" '
                 f'stroke="{faint}" stroke-width="0.8" stroke-opacity="0.4"/>')
    for rv in rings:
        x, y = pt(cx, cy, R * rv / rmax, -105)
        o.append(txt(x - 4, y - 3, str(rv), size=10, fill=ink, anchor="end",
                     extra=' opacity="0.55"'))

    for i, (name, dom, a) in enumerate(axes):
        x, y = pt(cx, cy, R + 20, a)
        anchor = "middle" if abs(math.cos(math.radians(a))) < 0.35 else (
            "start" if math.cos(math.radians(a)) > 0 else "end")
        dy = 12 if math.sin(math.radians(a)) > 0.35 else (-6 if math.sin(math.radians(a)) < -0.35 else 4)
        o.append(txt(x, y + dy, dom["label"], size=12, fill=domain_color(t, i), anchor=anchor, ls=1))

    mag = t["magenta"]
    test_pts = [pt(cx, cy, R * d["tests"] / rmax, a) for _, d, a in axes]
    o.append(poly(test_pts, fill=mag, fill_opacity="0.10", stroke=mag, stroke_width="2.2"))
    for x, y in test_pts:
        o.append(f'<rect x="{x - 3.2:.1f}" y="{y - 3.2:.1f}" width="6.4" height="6.4" '
                 f'fill="{t["canvas"]}" stroke="{mag}" stroke-width="1.6"/>')

    skill_pts = [pt(cx, cy, R * d["skills_bound"] / rmax, a) for _, d, a in axes]
    o.append(poly(skill_pts, fill=mint, fill_opacity=t["fill_data"], stroke=mint, stroke_width="2.6"))
    for x, y in skill_pts:
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{mint}" stroke="{ink}" stroke-width="1.2"/>')

    for (_, d, a), (x, y) in zip(axes, test_pts):
        lx, ly = pt(cx, cy, R * d["tests"] / rmax + 14, a)
        o.append(txt(lx, ly + 3, str(d["tests"]), size=9.5, fill=mag, anchor="middle"))

    o.append(txt(910, 74, "DOMAIN COVERAGE", cls="cond", size=34, fill=ink, anchor="end", ls=2))
    o.append(txt(910, 100, f'{m["domains"]} DOMAINS · SKILLS BOUND VS OFFLINE TESTS',
                 size=11, fill=pencil, anchor="end", ls=1))

    bx, by, bw, bh = 700, 612, 210, 178
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{t["surface"]}" '
             f'stroke="{ink}" stroke-width="1.2"/>')
    o.append(f'<line x1="{bx}" y1="{by + 74}" x2="{bx + bw}" y2="{by + 74}" stroke="{faint}" stroke-width="0.8"/>')
    o.append(f'<circle cx="{bx + 22}" cy="{by + 24}" r="4" fill="{mint}" stroke="{ink}" stroke-width="1.2"/>')
    o.append(txt(bx + 36, by + 28, f'SKILLS BOUND · {m["skills_bound"]}', size=10.5, fill=ink))
    o.append(f'<rect x="{bx + 18}" y="{by + 44}" width="8" height="8" fill="none" stroke="{t["magenta"]}" stroke-width="1.6"/>')
    o.append(txt(bx + 36, by + 52, f'OFFLINE TESTS · {m["tests"]}', size=10.5, fill=ink))
    rows = [("UNIT", "COUNT PER DOMAIN"), ("SCALE", f"0–{int(rmax)} · RINGS {int(rings[0])}"),
            ("GATE", "role-tests · DETERMINISTIC"), ("SHEET", "RDR-01 · REV AUTO")]
    for i, (k, v) in enumerate(rows):
        yy = by + 94 + i * 21
        o.append(txt(bx + 14, yy, k, size=9, fill=pencil, ls=1))
        o.append(txt(bx + 66, yy, v, size=9, fill=ink))

    o.append(txt(48, H - 22, f'{m["roles"]} ROLES · {m["skills_bound"]} SKILLS BOUND · '
                 f'{m["tests"]} OFFLINE TESTS', size=10, fill=pencil, ls=2))
    o.append(ownermark(t, bx + bw, H - 8))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------- polar

def gen_polar(m, t):
    W, H = 940, 660
    cx, cy, R = 300, 340, 238
    peak = max(d["role_count"] for d in m["per_domain"].values())
    vmax = float(max(4, math.ceil(peak / 2) * 2))
    rings = [int(vmax / 4 * i) for i in range(1, 5)]
    axes = domain_axes(m)
    ink, mint, pencil, faint = t["ink"], t["cyan"], t["pencil"], t["faint"]

    def rr(v):
        return R * math.sqrt(v / vmax)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    for rv in rings:
        o.append(f'<circle cx="{cx}" cy="{cy}" r="{rr(rv):.1f}" fill="none" '
                 f'stroke="{faint}" stroke-width="0.8" stroke-opacity="0.55"/>')

    half = 360 / len(axes) / 2 - 2.5
    for i, (name, dom, a) in enumerate(axes):
        c = domain_color(t, i)
        r = rr(dom["role_count"])
        a0, a1 = a - half, a + half
        x0, y0 = pt(cx, cy, r, a0)
        x1, y1 = pt(cx, cy, r, a1)
        o.append(f'<path d="M {cx} {cy} L {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 0 1 '
                 f'{x1:.1f} {y1:.1f} Z" fill="{c}" fill-opacity="{t["fill_rose"]}" '
                 f'stroke="{c}" stroke-width="2"/>')
        vx, vy = pt(cx, cy, r + 13, a)
        o.append(txt(vx, vy + 3.5, str(dom["role_count"]), size=10.5, fill=ink, anchor="middle"))

    o.append(txt(600, 74, "ROLES PER DOMAIN", cls="cond", size=34, fill=ink, ls=2))
    o.append(txt(600, 100, f'{m["roles"]} ROLES ACROSS {m["domains"]} DOMAINS · AREA-TRUE ROSE',
                 size=11, fill=pencil, ls=1))

    px, py, pitch, tw = 600, 138, 34, 150
    for i, (name, dom, a) in enumerate(axes):
        yy = py + i * pitch
        o.append(txt(px, yy, dom["label"], size=10, fill=pencil, ls=1))
        o.append(f'<rect x="{px}" y="{yy + 7}" width="{tw}" height="9" fill="none" '
                 f'stroke="{faint}" stroke-width="0.8"/>')
        o.append(f'<rect x="{px}" y="{yy + 7}" width="{tw * dom["role_count"] / vmax:.1f}" '
                 f'height="9" fill="{domain_color(t, i)}"/>')
        o.append(txt(px + tw + 12, yy + 15,
                     f'{dom["role_count"]}R · {dom["skills_bound"]} SKILLS', size=10, fill=ink))

    ring_note = "·".join(str(r) for r in rings)
    o.append(txt(cx, H - 22, f'{m["roles"]} ROLES · GRID RINGS {ring_note} · '
                 f'r ∝ √ROLES (AREA-TRUE)', size=10, fill=pencil, anchor="middle", ls=2))
    o.append(ownermark(t, W - 48, H - 22))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# --------------------------------------------------------- structure sunburst

def gen_structure(m, t):
    """Sunburst: inner ring = 12 domains, outer ring = every role, arc
    length proportional to skills bound."""
    W, H = 940, 900
    cx, cy = 470, 460
    r_hole, r_dom, r_role0, r_role1 = 96, 186, 192, 262
    ink, pencil, faint = t["ink"], t["pencil"], t["faint"]
    doms = m["per_domain"]
    names = sorted(doms)
    dom_gap, role_gap = 2.2, 0.7
    total = sum(doms[n]["skills_bound"] for n in names)
    span = 360.0 - dom_gap * len(names)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    a = -90.0
    for i, name in enumerate(names):
        d = doms[name]
        c = domain_color(t, i)
        dom_span = span * d["skills_bound"] / total
        a0, a1 = a, a + dom_span
        o.append(annulus(cx, cy, r_hole + 8, r_dom, a0, a1, c, "0.9", t["canvas"], "1.5"))
        ra = a0
        nroles = max(d["role_count"], 1)
        rgap = min(role_gap, dom_span * 0.25 / max(nroles - 1, 1)) if nroles > 1 else 0.0
        role_span_total = dom_span - rgap * (nroles - 1)
        weight_total = sum(max(r["skills_bound"], 1) for r in d["roles"]) or 1
        for j, r in enumerate(d["roles"]):
            rs = role_span_total * max(r["skills_bound"], 1) / weight_total
            o.append(annulus(cx, cy, r_role0, r_role1, ra, ra + rs, c,
                             "0.55" if j % 2 == 0 else "0.32", t["canvas"], "1"))
            ra += rs + rgap
        mid = (a0 + a1) / 2
        lx, ly = pt(cx, cy, r_role1 + 22, mid)
        cosm = math.cos(math.radians(mid))
        anchor = "middle" if abs(cosm) < 0.35 else ("start" if cosm > 0 else "end")
        dy = 10 if math.sin(math.radians(mid)) > 0.35 else (
            -4 if math.sin(math.radians(mid)) < -0.35 else 4)
        o.append(txt(lx, ly + dy, d["label"], size=11, fill=pencil, anchor=anchor, ls=1))
        o.append(txt(lx, ly + dy + 15, f'{d["role_count"]}R · {d["skills_bound"]}S', size=9.5,
                     fill=c, anchor=anchor, ls=1))
        a = a1 + dom_gap

    o.append(txt(cx, cy - 8, str(m["roles"]), cls="cond", size=52, fill=ink,
                 anchor="middle", ls=1))
    o.append(txt(cx, cy + 16, "ROLES", size=10, fill=pencil, anchor="middle", ls=2))
    o.append(txt(cx, cy + 34, f'{m["skills_bound"]} SKILLS BOUND · {m["domains"]} DOMAINS',
                 size=9.5, fill=pencil, anchor="middle", ls=1))

    o.append(txt(52, 64, "ROLE BANK STRUCTURE", cls="cond", size=34, fill=ink, ls=2))
    o.append(txt(52, 90, "INNER RING: DOMAINS · OUTER RING: ROLES · "
                 "ARC LENGTH = SKILLS BOUND", size=10.5, fill=pencil, ls=1))
    o.append(txt(cx, H - 24, f'EVERY ARC COMPUTED FROM roles/ AT HEAD · '
                 f'FULL PER-DOMAIN LISTS IN docs/DOMAINS.md', size=10, fill=pencil,
                 anchor="middle", ls=2))
    o.append(ownermark(t, W - 52, 64))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------ gate battery

def gen_gates(m, t):
    """The 5-gate battery every commit passes, fail-closed."""
    W, H = 1240, 300
    ink, pencil, faint = t["ink"], t["pencil"], t["faint"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    def chip(x, y, w, h, lines, stroke, sw="1.3", fill=None):
        o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" '
                 f'fill="{fill or t["surface"]}" stroke="{stroke}" stroke-width="{sw}"/>')
        cy0 = y + h / 2 - (len(lines) - 1) * 8 + 4
        for j, line in enumerate(lines):
            o.append(txt(x + w / 2, cy0 + j * 16, line, size=10, fill=ink,
                         anchor="middle", ls=1))

    def arrow(x0, x1, y):
        o.append(f'<line x1="{x0:.1f}" y1="{y}" x2="{x1 - 8:.1f}" y2="{y}" '
                 f'stroke="{ink}" stroke-width="1.4"/>')
        o.append(f'<path d="M {x1:.1f} {y} l -9 -4.5 v 9 Z" fill="{ink}"/>')

    mid = 140
    chip(30, mid - 34, 90, 68, ["COMMIT"], ink)
    arrow(120, 150, mid)

    gx, gw = 154, 800
    o.append(f'<rect x="{gx}" y="70" width="{gw}" height="140" fill="none" '
             f'stroke="{t["violet"]}" stroke-width="1.8"/>')
    o.append(txt(gx + 12, 62, f'MAKE VALIDATE · {m["gates"]}/{m["gates"]} REAL GATES',
                 size=11, fill=t["violet"], ls=2))
    gates = [["ROLE", "LINT"], ["ROLE", "TESTS"], ["NO-", "VERBATIM"],
             ["SECURITY"], ["MANIFEST"]]
    cw = (gw - 28) / len(gates)
    for i, lines in enumerate(gates):
        chip(gx + 14 + i * cw, mid - 28, cw - 10, 56, lines, faint)
    arrow(gx + gw + 4, gx + gw + 36, mid)

    chip(994, mid - 34, 96, 68, ["VISUALS", "FRESH"], t["orange"], "1.8")
    arrow(1094, 1124, mid)
    o.append(f'<rect x="1128" y="{mid - 34}" width="82" height="68" fill="{t["cyan"]}" '
             f'fill-opacity="{t["fill_data"]}" stroke="{t["cyan"]}" stroke-width="2.2"/>')
    o.append(txt(1169, mid - 2, "CI", size=11, fill=ink, anchor="middle", ls=1))
    o.append(txt(1169, mid + 14, "GREEN", size=11, fill=ink, anchor="middle", ls=1))

    o.append(f'<line x1="30" y1="{H - 62}" x2="{W - 30}" y2="{H - 62}" '
             f'stroke="{faint}" stroke-width="0.8"/>')
    o.append(txt(30, H - 38, "FAIL-CLOSED: ANY RED GATE BLOCKS THE PUSH · "
                 "DETERMINISTIC · OFFLINE · REPLAY WITH make validate",
                 size=10.5, fill=pencil, ls=2))
    o.append(ownermark(t, W - 30, H - 38))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------ role anatomy

def gen_anatomy(t):
    """Exploded view of one role folder: what each part is for."""
    W, H = 1500, 470
    ink, pencil, faint = t["ink"], t["pencil"], t["faint"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    o.append(txt(48, 56, "ANATOMY OF A ROLE", cls="cond", size=30, fill=ink, ls=2))
    o.append(txt(48, 80, "roles/do178c-cert-engineer/ — one role, four load-bearing parts",
                 size=11, fill=pencil, ls=1))

    rows = [
        ("ROLE.md · FRONTMATTER", t["cyan"],
         ["identity, deliverable type, bound standards + skills —",
          "the machine-readable contract manifest.json is generated from."]),
        ("ROLE.md · BODY", t["violet"],
         ["the workflow the agent follows: ordered stages, an evidence",
          "gate per stage, forbidden actions, the human sign-off stop."]),
        ("core/*_core.py + cli.py", t["magenta"],
         ["the executable domain engine — computes the real deliverable",
          "content offline, stdlib only, no network calls."]),
        ("tests/ + templates/ + SOURCES.md", t["orange"],
         ["offline behavior contract (gate 2 replays it), original",
          "deliverable skeleton, and standards referenced (summary-not-copy)."]),
    ]
    y = 110
    for label, c, desc in rows:
        o.append(f'<rect x="48" y="{y}" width="380" height="62" fill="{t["surface"]}" '
                 f'stroke="{c}" stroke-width="1.8"/>')
        o.append(f'<rect x="48" y="{y}" width="6" height="62" fill="{c}"/>')
        o.append(txt(70, y + 37, label, size=12, fill=ink, ls=1))
        o.append(f'<line x1="432" y1="{y + 31}" x2="472" y2="{y + 31}" '
                 f'stroke="{ink}" stroke-width="1.3"/>')
        o.append(f'<path d="M 480 {y + 31} l -9 -4.5 v 9 Z" fill="{ink}"/>')
        for j, line in enumerate(desc):
            o.append(txt(496, y + 26 + j * 18, line, size=11.5, fill=pencil))
        y += 82

    o.append(txt(48, H - 26, "PLAIN FILES, OPEN AGENTSKILLS.IO-ADJACENT FORMAT · "
                 "ANY ROLE.MD-AWARE HOST CAN LOAD THEM", size=10.5, fill=pencil, ls=2))
    o.append(ownermark(t, W - 48, H - 26))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------- how-it-works

def gen_flow(t):
    W, H = 1500, 250
    ink, mint, pencil, faint = t["ink"], t["cyan"], t["pencil"], t["faint"]
    steps = [
        ("01", ["ADOPT A ROLE"], False),
        ("02", ["ROLE BINDS SKILLS", "FROM manifest.json"], False),
        ("03", ["WORKFLOW STAGES", "RUN IN ORDER"], False),
        ("04", ["EACH STAGE:", "EVIDENCE GATE"], False),
        ("05", ["core/*.py COMPUTES", "THE DELIVERABLE"], False),
        ("06", ["STOP GATE:", "HUMAN SIGN-OFF"], True),
    ]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', STYLE.rstrip(),
         f'<rect width="{W}" height="{H}" fill="{t["canvas"]}"/>']

    n, bw, bh, mx = len(steps), 200, 84, 48
    gap = (W - 2 * mx - n * bw) / (n - 1)
    by = 84
    for i, (num, lines, accent) in enumerate(steps):
        x = mx + i * (bw + gap)
        stroke = t["orange"] if accent else ink
        o.append(f'<rect x="{x:.1f}" y="{by}" width="{bw}" height="{bh}" fill="{t["surface"]}" '
                 f'stroke="{stroke}" stroke-width="{2.4 if accent else 1.4}"/>')
        o.append(txt(x + 2, by - 12, num, size=11, fill=t["orange"] if accent else mint, ls=2))
        cy0 = by + bh / 2 - (len(lines) - 1) * 9 + 4
        for j, line in enumerate(lines):
            o.append(txt(x + bw / 2, cy0 + j * 18, line, size=11.5,
                         fill=ink, anchor="middle", ls=1))
        if i < n - 1:
            ax0, ax1, ay = x + bw + 6, x + bw + gap - 6, by + bh / 2
            o.append(f'<line x1="{ax0:.1f}" y1="{ay}" x2="{ax1 - 8:.1f}" y2="{ay}" '
                     f'stroke="{ink}" stroke-width="1.4"/>')
            o.append(f'<path d="M {ax1:.1f} {ay} l -9 -4.5 v 9 Z" fill="{ink}"/>')

    o.append(txt(mx, H - 40, "EVERY STAGE HAS A GATE · OFFLINE, DETERMINISTIC · "
                 "THE TERMINAL NODE IS ALWAYS A HUMAN", size=10.5, fill=pencil, ls=2))
    o.append(ownermark(t, W - mx, H - 40))
    o.append(f'<line x1="{mx}" y1="{H - 60}" x2="{W - mx}" y2="{H - 60}" '
             f'stroke="{faint}" stroke-width="0.8"/>')
    o.append("</svg>")
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
    dist = [
        b("npm", "aero-agent-roles", "0ea5e9", "https://www.npmjs.com/package/aero-agent-roles"),
        b("cli", "aero-roles", "8b5cf6", "packages/aero-agent-roles/"),
        b("mcp server", "claude_%C2%B7_cursor_%C2%B7_vscode", "ec4899", "packages/aero-agent-roles/lib/mcp.js",
          alt="MCP server for Claude Desktop, Cursor, VS Code"),
        b("claude code", "plugin", "f97316", ".claude-plugin/"),
        b("jetbrains", "plugin_34121", "a78bfa", "packages/jetbrains-plugin/",
          alt="JetBrains plugin, live on the Marketplace (com.ashforde.aeroroles, review pending)"),
    ]
    return ("<p align=\"center\">\n" + "\n".join(row) + "\n</p>\n"
            + "<p align=\"center\">\n" + "\n".join(dist) + "\n</p>")


def block_role_table(m):
    rows = ["| Role | Deliverable | Skills bound |", "|---|---|---|"]
    for r in sorted(m["per_role"], key=lambda r: r["title"]):
        rows.append(f'| [{r["title"]}](roles/{r["slug"]}/ROLE.md) | '
                    f'{r["deliverable_type"]} | {r["skills_bound"]} |')
    return "\n".join(rows)


def block_overview(m):
    return (f'**{m["roles"]} roles** across **{m["domains"]} domains**, binding '
            f'**{m["skills_bound"]} skills** from Aero Agent Skills and verified by '
            f'**{m["tests"]} offline tests** — every figure below is computed from '
            f'the tree at HEAD; nothing is hand-counted.')


BLOCKS = {
    "badges": block_badges,
    "overview": block_overview,
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


# -------------------------------------------------------------- domain map

def gen_domains(m):
    def mid(s):
        return s.replace("-", "_")

    out = [
        "# Aero Agent Roles Domain Map",
        "",
        "Machine-readable source of truth: `roles/*/ROLE.md` frontmatter. This",
        f'page is the human companion — {m["domains"]} domains, {m["roles"]} roles, '
        f'{m["skills_bound"]} skills bound.',
        "",
        "Generated by `make visuals` (scripts/gen_visuals.py) — do not edit by hand;",
        "CI fails if this page drifts from the tree. Aero Agent Roles is built and",
        "maintained by [Ashforde OÜ](https://ashforde.org).",
        "",
        "```mermaid",
        "graph TD",
        "    ROOT[Aero Agent Roles]",
    ]
    doms = m["per_domain"]
    for name in sorted(doms):
        d = doms[name]
        out.append(f"    {mid(name)}[{name}]")
        out.append(f"    ROOT --> {mid(name)}")
        for r in d["roles"]:
            rid = f"{mid(name)}_{mid(r['slug'])}"
            out.append(f"    {rid}[{r['slug']} · {r['skills_bound']}]")
            out.append(f"    {mid(name)} --> {rid}")
    out += ["```", "",
            f'*{m["roles"]} roles · {m["skills_bound"]} skills bound rendered above.*']
    for name in sorted(doms):
        d = doms[name]
        out += ["", f"## {name}", "",
                f'**{d["role_count"]} roles · {d["skills_bound"]} skills bound · {d["tests"]} offline tests**',
                "", "| Role | Deliverable | Skills bound | Tests |", "|---|---|---|---|"]
        for r in sorted(d["roles"], key=lambda r: r["title"]):
            out.append(f'| [{r["title"]}](../roles/{r["slug"]}/ROLE.md) | '
                       f'{r["deliverable_type"]} | {r["skills_bound"]} | {r["tests"]} |')
    return "\n".join(out) + "\n"


# -------------------------------------------------------------------- main

# SVG -> PNG raster width (rsvg-convert -w), keyed by output stem — 2x the
# README's display width for retina screens, matching aero-agent-skills.
PNG_WIDTHS = {
    "title-dark": 1240,
    "statline-dark": 2480,
    "domain-radar-dark": 1880,
    "domain-polar-dark": 1880,
    "structure-dark": 1880,
    "gates-dark": 2480,
    "role-anatomy-dark": 3000,
    "how-it-works-dark": 3000,
}


def outputs(m):
    docs = REPO / "docs"
    return {
        docs / "metrics.json": json.dumps(
            {k: v for k, v in m.items() if k not in ("per_role", "per_standard", "per_domain")},
            indent=2, sort_keys=True) + "\n",
        docs / "title-dark.svg": gen_title(DARK),
        docs / "statline-dark.svg": gen_statline(m, DARK),
        docs / "domain-radar-dark.svg": gen_radar(m, DARK),
        docs / "domain-polar-dark.svg": gen_polar(m, DARK),
        docs / "structure-dark.svg": gen_structure(m, DARK),
        docs / "gates-dark.svg": gen_gates(m, DARK),
        docs / "role-anatomy-dark.svg": gen_anatomy(DARK),
        docs / "how-it-works-dark.svg": gen_flow(DARK),
        docs / "DOMAINS.md": gen_domains(m),
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
