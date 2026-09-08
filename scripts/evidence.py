#!/usr/bin/env python3
"""evidence.py - shared evidence-bundle writer for role CLIs.

Implements docs/PROTOCOL.md v1: every role emits
  deliverable.md + evidence/{model.json, gates.json, provenance.json}
so any harness can consume results programmatically.

Usage (from a role cli.py):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "scripts"))
    import evidence
    evidence.write_bundle(out_dir, role_slug, model, gates, provenance)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_profile(path: str) -> dict | None:
    """Load and validate a program profile JSON (docs/PROFILE-SCHEMA.md)."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        p = json.load(f)
    if not isinstance(p, dict) or not p.get("customer"):
        raise ValueError("profile must be a JSON object with 'customer'")
    return p


def profile_header_block(profile: dict) -> str:
    """Render a markdown header block for a program profile.

    Returns "" when profile is None. NEVER an approval — always a DRAFT
    context header for human review.
    """
    if not profile:
        return ""
    lines = [
        "## Program context (profile)",
        "",
        f"- Customer: {profile.get('customer', '')}",
        f"- Program: {profile.get('program', '')}",
        f"- Basis: {profile.get('basis', '')}  ·  "
        f"Authority: {profile.get('authority', '')}",
    ]
    if profile.get("der"):
        lines.append(f"- DER/CVE: {profile['der']}")
    if profile.get("document_prefix"):
        rev = profile.get("revision", "")
        lines.append(f"- Document: {profile['document_prefix']}"
                     + (f" {rev}" if rev else ""))
    if profile.get("standards"):
        lines.append("- Standards: " + ", ".join(profile["standards"]))
    if profile.get("notes"):
        lines.append(f"- Notes: {profile['notes']}")
    lines += [
        "",
        "> This document is a DRAFT for human review within the program "
        "sign-off chain. It is not an approval and carries no regulatory "
        "authority.",
        "",
    ]
    return "\n".join(lines)


def dispatch_crosscheck(leaf: str, skill_fn: str, core_fn,
                        tolerance: float = 1e-6,
                        skills_root: str = "") -> dict | None:
    """Run a bound AeroSkills leaf's logic fn and compare to the core fn.

    Both functions are called with the same kwargs. Returns a provenance
    row: {leaf, logic_file, function, dispatched, core_value,
    skill_value, delta, agrees}. Returns None if the skill logic file or
    function is unavailable.

    leaf         e.g. 'structures/loads/gust-maneuver-loads'
    skill_fn     the function name inside the leaf's *logic.py
    core_fn      a zero-arg callable returning the core's computed value
    skills_root  AeroSkills root (default: AEROSKILLS_DEV or ~/company-ops/aero-agent-skills)
    """
    import importlib.util  # local import (stdlib)
    root = skills_root or os.environ.get(
        "AEROSKILLS_DEV", os.path.expanduser("~/company-ops/aero-agent-skills"))
    logic_dir = os.path.join(root, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    if not logic_files:
        return None
    # try each logic file until one exposes the requested fn
    for lf in logic_files:
        path = os.path.join(logic_dir, lf)
        spec = importlib.util.spec_from_file_location("role_dispatch", path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        if not hasattr(mod, skill_fn):
            continue
        try:
            skill_value = getattr(mod, skill_fn)()
            core_value = core_fn()
            if not isinstance(skill_value, (int, float)) or \
               not isinstance(core_value, (int, float)):
                continue
            delta = abs(float(core_value) - float(skill_value))
            return {
                "leaf": leaf,
                "logic_file": lf,
                "function": skill_fn,
                "dispatched": True,
                "core_value": round(float(core_value), 6),
                "skill_value": round(float(skill_value), 6),
                "delta": round(delta, 9),
                "agrees": delta <= tolerance,
                "tolerance": tolerance,
            }
        except Exception:
            continue
    return None


def write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def write_bundle(out_md: str, role: str, deliverable_type: str,
                 model: dict, gates: dict, provenance: dict) -> dict:
    """Write the evidence bundle next to the markdown deliverable.

    out_md       path of the deliverable .md (evidence/ goes beside it)
    role         role slug, e.g. "structures-loads-engineer"
    model        the computed content model (build_<deliverable>() result)
    gates        gates dict from check_<deliverable>() (has 'all_pass')
    provenance   provenance dict (core + skills + disclaimer)

    Returns the paths written: {"model": ..., "gates": ..., "provenance": ...}
    """
    ev_dir = os.path.join(os.path.dirname(os.path.abspath(out_md)), "evidence")
    os.makedirs(ev_dir, exist_ok=True)

    # Normalize gates into the protocol shape
    gate_rows = []
    for k, v in gates.items():
        if k in ("all_pass", "exit_code", "checker"):
            continue
        if isinstance(v, dict):
            gate_rows.append({"gate": k, "pass": bool(v.get("pass", v.get("ok", False))),
                              "detail": str(v.get("detail", ""))})
        else:
            gate_rows.append({"gate": k, "pass": bool(v)})
    gates_payload = {
        "schema_version": 1,
        "role": role,
        "checker": gates.get("checker", "check_<deliverable>"),
        "gates": gate_rows,
        "all_pass": bool(gates.get("all_pass", all(r["pass"] for r in gate_rows))),
        "exit_code": 0 if gates.get("all_pass", all(r["pass"] for r in gate_rows)) else 1,
        "checked_at": _utcnow(),
    }

    model_payload = dict(model or {})
    model_payload.setdefault("schema_version", 1)
    model_payload.setdefault("role", role)
    model_payload.setdefault("deliverable_type", deliverable_type)
    model_payload.setdefault("generated", _utcnow())
    model_payload.setdefault("status", "draft-for-review")

    prov_payload = dict(provenance or {})
    prov_payload.setdefault("schema_version", 1)
    prov_payload.setdefault("role", role)
    prov_payload.setdefault("disclaimer",
                            "DRAFT for human review. Not an approval document.")

    model_path = os.path.join(ev_dir, "model.json")
    gates_path = os.path.join(ev_dir, "gates.json")
    prov_path = os.path.join(ev_dir, "provenance.json")
    write_json(model_path, model_payload)
    write_json(gates_path, gates_payload)
    write_json(prov_path, prov_payload)

    return {"model": model_path, "gates": gates_path, "provenance": prov_path}
