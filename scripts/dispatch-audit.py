#!/usr/bin/env python3
"""dispatch-audit.py — cross-check every role core against its bound
AeroSkills logic where a matching computation exists.

This is the compounding power verification: as the skills repo grows
logic files, more role computations become cross-checkable. Each row
records: core value, skill value, delta, agrees. Roles with no
dispatchable pair (or no AeroSkills present) report honestly.

The dispatch map is explicit per role: (leaf, skill module fn, core
module fn, kwargs for both, param-name translation when signatures
differ). Extend the map as more pairs are identified.

Usage: python3 scripts/dispatch-audit.py [--json]
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

ROLES_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))


def load_core(role_slug: str):
    """Load role core via sys.path (same way role tests import it)."""
    core_dir = os.path.join(ROLES_ROOT, "roles", role_slug, "core")
    files = [f for f in os.listdir(core_dir) if f.endswith("_core.py")]
    if not files:
        return None
    mod_name = files[0][:-3]
    sys.path.insert(0, core_dir)
    try:
        mod = importlib.import_module(mod_name)
        return mod
    except Exception:
        return None


def load_skill_logic(leaf: str, fn_name: str):
    logic_dir = os.path.join(SKILLS_ROOT, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for lf in sorted(os.listdir(logic_dir)):
        if lf.endswith("_logic.py"):
            spec = importlib.util.spec_from_file_location(
                "skill_logic", os.path.join(logic_dir, lf))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            if hasattr(mod, fn_name):
                return mod
    return None


# dispatch map: role -> list of cross-check pairs.
# Each pair: leaf (skill leaf), skill_fn, core_fn (name in role core),
# kwargs (values), skill_param_map (core kwarg -> skill kwarg when names
# differ), tolerance. Only pairs verified to exist in BOTH modules.
DISPATCH_MAP = {
    "flight-mechanics-engineer": [
        {
            "leaf": "flight-mechanics/performance/breguet-range",
            "skill_fn": "breguet_range",
            "core_fn": "breguet_range",
            "kwargs": {"v_ms": 235.0, "tsfc_kg_per_n_s": 1.5e-5,
                       "ld": 18.0, "m0_kg": 70000.0, "m1_kg": 50000.0},
            "skill_param_map": {},
        },
    ],
    "structures-loads-engineer": [
        {
            "leaf": "structures/loads/gust-maneuver-loads",
            "skill_fn": "gust_alleviation_factor",
            "core_fn": "gust_alleviation_factor",
            "kwargs": {"ws": 100.0, "cbar": 11.18, "a": 5.7,
                       "rho": 0.0023769},
            "skill_param_map": {},
        },
    ],
    "guidance-engineer": [
        {
            "leaf": "gnc-autonomy/guidance/proportional-navigation",
            "skill_fn": "commanded_acceleration",
            "core_fn": "commanded_acceleration",
            "kwargs": {"rx": 1000.0, "ry": 100.0, "vx": -200.0, "vy": 0.0,
                       "n_nav": 4.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/guidance/augmented-proportional-navigation",
            "skill_fn": "apn_command",
            "core_fn": "apn_command",
            "kwargs": {"navigation_ratio": 4.0,
                       "closing_velocity": 199.007438041998,
                       "los_rate": 0.019801980198,
                       "target_lateral_accel": 20.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/guidance/pursuit-guidance",
            "skill_fn": "heading_error",
            "core_fn": "heading_error",
            "kwargs": {"psi": 0.0, "rx": 1000.0, "ry": 100.0},
            "skill_param_map": {},
        },
    ],
    "state-estimation-engineer": [
        {
            "leaf": "gnc-autonomy/estimation-filtering/complementary-filter",
            "skill_fn": "steady_state_verdict",
            "core_fn": "steady_state_verdict",
            "kwargs": {"innovation_norms": [5e-4, 3e-4, 2e-4, 1e-4],
                       "tolerance": 1e-3},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/estimation-filtering/unscented-kalman-filter",
            "skill_fn": "nees",
            "core_fn": "nees",
            "kwargs": {"x_est": [300.0, 40.0],
                       "p_est": [[100.0, 0.0], [0.0, 100.0]],
                       "x_true": [295.0, 42.0]},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/estimation-filtering/particle-filter",
            "skill_fn": "effective_sample_size",
            "core_fn": "effective_sample_size",
            "kwargs": {"weights": [0.25, 0.25, 0.25, 0.25]},
            "skill_param_map": {},
        },
    ],
}


def run() -> int:
    results = []
    for role_slug in sorted(DISPATCH_MAP):
        core_mod = load_core(role_slug)
        if core_mod is None:
            results.append({"role": role_slug, "error": "core not loadable"})
            continue
        role_rows = []
        for pair in DISPATCH_MAP[role_slug]:
            skill_mod = load_skill_logic(pair["leaf"], pair["skill_fn"])
            if skill_mod is None:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": False,
                    "reason": "skill logic unavailable"})
                continue
            core_fn = getattr(core_mod, pair["core_fn"], None)
            if core_fn is None:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": False,
                    "reason": "core fn missing"})
                continue
            try:
                # call core with its params
                core_val = core_fn(**pair["kwargs"])
                # call skill, translating param names
                skill_kwargs = dict(pair["kwargs"])
                for core_k, skill_k in pair.get("skill_param_map", {}).items():
                    if core_k in skill_kwargs:
                        skill_kwargs[skill_k] = skill_kwargs.pop(core_k)
                skill_val = getattr(skill_mod, pair["skill_fn"])(**skill_kwargs)
                delta = abs(float(core_val) - float(skill_val))
                role_rows.append({
                    "leaf": pair["leaf"],
                    "function": pair["skill_fn"],
                    "dispatched": True,
                    "core_value": round(float(core_val), 6),
                    "skill_value": round(float(skill_val), 6),
                    "delta": round(delta, 9),
                    "agrees": delta <= pair.get("tolerance", 1e-6),
                })
            except Exception as e:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": True,
                    "error": str(e)[:150], "agrees": False})
        results.append({"role": role_slug, "checks": role_rows})

    if "--json" in sys.argv:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            for c in r.get("checks", []):
                if c.get("dispatched") and "error" not in c:
                    mark = "AGREE" if c["agrees"] else "DISAGREE"
                    print(f"{r['role']}: {c['leaf']} {mark} "
                          f"core={c['core_value']} skill={c['skill_value']} "
                          f"delta={c['delta']}")
                else:
                    print(f"{r['role']}: {c.get('leaf')} not dispatched "
                          f"({c.get('reason', c.get('error', '?'))})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
