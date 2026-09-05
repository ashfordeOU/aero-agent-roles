#!/usr/bin/env python3
"""cli.py - run the Space Systems Engineer role.

Usage:
  python3 cli.py build --out <file.md>              # build the mission +
                                                    # subsystem design report
  python3 cli.py build --out alt.md --altitude 500  # variant orbit
  python3 cli.py build --out r.md --bundle          # also write
                                                    # evidence/{model,gates,
                                                    # provenance}.json
                                                    # (docs/PROTOCOL.md v1)
  python3 cli.py build --out r.md --bundle \
      --profile profiles/example-airframer.json     # program profile context
                                                    # header (customer
                                                    # tailoring, docs/
                                                    # PROFILE-SCHEMA.md)
  python3 cli.py check --file <file.md>             # gate-check a report

The role ENGINE (core/space_systems_core.py) does the work standalone;
bound AeroSkills space-systems leaves deepen individual stages when
present, but the core never depends on them.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import space_systems_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "space-systems-engineer"


def cmd_build(args):
    mission = core.example_mission()
    if args.altitude:
        mission.altitude_km = args.altitude
    if args.name:
        mission.name = args.name
    if args.dry_mass:
        mission.dry_mass_kg = args.dry_mass
    if args.isp:
        mission.isp_s = args.isp
    if args.dv_margin:
        mission.dv_margin_fraction = args.dv_margin
    model = core.build_report(mission)
    md = core.render_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print(f"error: bad profile: {e}")
        return 1
    if profile:
        model["profile"] = {
            "customer": profile.get("customer"),
            "program": profile.get("program"),
            "basis": profile.get("basis"),
            "authority": profile.get("authority"),
            "der": profile.get("der"),
            "document_prefix": profile.get("document_prefix"),
            "revision": profile.get("revision"),
        }
        md = evidence.profile_header_block(profile) + md

    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        dv = model["delta_v"]
        print(f"built report -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"  orbit: {mission.altitude_km:.0f} km circular, "
              f"period {model['power']['eclipse']['period_min']:.1f} min")
        print(f"  delta-v: {dv['nominal_dv_m_s']:.1f} m/s nominal / "
              f"{dv['budgeted_dv_m_s']:.1f} m/s budgeted; "
              f"propellant {dv['propellant_mass_kg']:.1f} kg")
        print(f"  wheel: {model['adcs']['wheel_momentum_capacity_nms']:.1f} N m s "
              f"at {model['adcs']['wheel_speed_max_rpm']:.0f} rpm; "
              f"array {model['power']['array_area_m2']:.2f} m^2; "
              f"battery {model['power']['battery_sized_wh']:.0f} Wh")
        print(f"  pointing {model['pointing']['rss_deg']:.3f} deg; "
              f"link down {model['comms']['downlink']['margin_db']:.1f} dB / "
              f"up {model['comms']['uplink']['margin_db']:.1f} dB")
        print(f"  gates: all_pass={gates['all_pass']}")
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Spacecraft Mission and Subsystem Design Report",
                model, gates, _provenance())
            print(f"  bundle: model={paths['model']}")
            print(f"          gates={paths['gates']}")
            print(f"          provenance={paths['provenance']}")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def _provenance():
    """PROTOCOL.md v1 provenance row.

    The role core computed every number in the model standalone; no
    bound-skill logic file was dispatched, so skills is honestly empty
    and cross_checked is False.
    """
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/space_systems_core.py",
            "functions": ["build_report", "mission_delta_v_budget",
                          "power_and_thermal", "reaction_wheel_sizing",
                          "comms_link_budget", "check_report"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="Space Systems Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--name", default="", help="spacecraft/mission name")
    b.add_argument("--altitude", type=float, default=0.0,
                   help="circular orbit altitude in km (default 600)")
    b.add_argument("--dry-mass", type=float, default=0.0,
                   help="spacecraft dry mass in kg (default 150)")
    b.add_argument("--isp", type=float, default=0.0,
                   help="propulsion specific impulse in s (default 220)")
    b.add_argument("--dv-margin", type=float, default=0.0,
                   help="delta-v margin fraction (default 0.15)")
    b.add_argument("--bundle", action="store_true",
                   help="also write evidence/{model,gates,provenance}.json "
                        "(docs/PROTOCOL.md v1)")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="report markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
