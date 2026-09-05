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
