#!/usr/bin/env python3
"""Role test: DO-160G Environmental Qualification Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the example LRU produces a complete
   qualification report with no blank sections.
4. When the skills checkout is present, the core's numeric anchors are
   CROSS-CHECKED against the bound leaves' own *_logic.py files.
5. cli.py build --bundle works (evidence JSON written, gates pass).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "do160-environmental-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "environmental-qualification-plan-template.md")

EXPECTED_BOUND = [
    "avionics/do160/environmental-qualification",
    "avionics/do160/lightning-protection",
    "avionics/do160/electrostatic-discharge",
    "avionics/do160/power-input",
    "avionics/do160/radio-frequency-susceptibility",
    "avionics/do160/radio-frequency-emissions",
]

EXPECTED_STAGES = [
    "Environmental scope", "Lightning plan", "ESD levels",
    "Power input quality", "RF immunity", "RF emissions",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


def load_leaf_logic(leaf):
    """Import a bound leaf's *_logic.py (first one found). Returns module
    or None when the leaf or its logic file is unavailable."""
    logic_dir = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for f in sorted(os.listdir(logic_dir)):
        if f.endswith("_logic.py"):
            path = os.path.join(logic_dir, f)
            spec = importlib.util.spec_from_file_location(
                leaf.replace("/", "_"), path)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            return mod
    return None


class TestDo160Role(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            f"bound skill not found in aero-agent-skills: "
                            f"{leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role, f"missing in ROLE.md skills_bound: "
                                      f"{leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "environmental-qualification-plan-template.md missing")
        text = open(TEMPLATE, encoding="utf-8").read()
        # all 9 numbered sections present
        for n in range(1, 10):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            f"section {n} missing")
        # zero blank fillers
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("15 kv air discharge", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue qualification approval", "regulatory sign-off",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_cli_build_bundle_exits_zero(self):
        """cli build --bundle -> exit 0, evidence JSON valid, gates pass."""
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "eqpr.md")
            r = subprocess.run([sys.executable, os.path.join(ROLE_DIR, "cli.py"),
                                "build", "--out", out, "--bundle"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(out))
            ev = os.path.join(td, "evidence")
            for f in ["model.json", "gates.json", "provenance.json"]:
                self.assertTrue(os.path.exists(os.path.join(ev, f)),
                                f"evidence/{f} missing")
            gates = json.load(open(os.path.join(ev, "gates.json")))
            self.assertTrue(gates["all_pass"])
            self.assertEqual(gates["exit_code"], 0)
            model = json.load(open(os.path.join(ev, "model.json")))
            self.assertIn("temperature_category", model)
            prov = json.load(open(os.path.join(ev, "provenance.json")))
            self.assertEqual(prov["role"], "do160-environmental-engineer")
            # no local paths in the bundle
            blob = json.dumps(model) + json.dumps(prov)
            self.assertNotIn("/Users/", blob)
            self.assertNotIn(AEROSKILLS if not AEROSKILLS.startswith("~")
                             else "/nonexistent", blob)

    def test_cli_build_standalone_bad_skills_env(self):
        """AEROSKILLS_DEV=/nonexistent -> core still builds correctly."""
        env = dict(os.environ)
        env["AEROSKILLS_DEV"] = "/nonexistent"
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "eqpr.md")
            r = subprocess.run([sys.executable, os.path.join(ROLE_DIR, "cli.py"),
                                "build", "--out", out],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            text = open(out).read()
            self.assertIn("draft", text.lower())
            self.assertIn("not an approval", text.lower())

    def test_cli_check_gate(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "eqpr.md")
            subprocess.run([sys.executable, os.path.join(ROLE_DIR, "cli.py"),
                            "build", "--out", out],
                           capture_output=True, text=True, check=True)
            r = subprocess.run([sys.executable,
                                os.path.join(ROLE_DIR, "cli.py"),
                                "check", "--file", out, "--category", "B1"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("RESULT: PASS", r.stdout)


class TestDo160LeafCrossCheck(unittest.TestCase):
    """Core numeric anchors vs the bound leaves' logic files (dev check,
    skipped when the skills checkout is absent)."""

    @classmethod
    def setUpClass(cls):
        if not HAS_SKILLS:
            raise unittest.SkipTest("Aero Skills checkout not present")

    def _core(self):
        sys.path.insert(0, os.path.join(ROLE_DIR, "core"))
        import do160_environmental_core as core
        return core

    def test_esd_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/electrostatic-discharge")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertAlmostEqual(
            mod.category_test_level_kv("A"),
            core.esd_category_test_level_kv("A"), places=6)
        self.assertAlmostEqual(
            mod.stored_energy_joules(150.0, 15.0),
            core.esd_stored_energy_joules(150.0, 15.0), places=9)
        self.assertAlmostEqual(mod.peak_current_amps(15.0),
                               core.esd_peak_current_amps(15.0), places=6)
        self.assertAlmostEqual(
            mod.rc_time_constant_ns(330.0, 150.0),
            core.esd_rc_time_constant_ns(330.0, 150.0), places=6)
        self.assertEqual(mod.pass_verdict(True, True),
                         core.esd_pass_verdict(True, True))

    def test_lightning_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/lightning-protection")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertEqual(mod.test_level_in_range(3),
                         core.lightning_level_valid(3))
        self.assertEqual(mod.waveform_supported("C"),
                         core.lightning_waveform_valid("C"))
        self.assertEqual(mod.pass_verdict(False, False, False),
                         core.lightning_pass_verdict(False, False, False))

    def test_power_input_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/power-input")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertAlmostEqual(mod.sag_depth_percent(28.0, 21.0),
                               core.sag_depth_percent(28.0, 21.0), places=6)
        self.assertAlmostEqual(mod.surge_height_percent(28.0, 32.2),
                               core.surge_height_percent(28.0, 32.2),
                               places=6)
        ok1, d1, p1 = mod.transient_check(80.0, 20.0, 100.0, 25.0)
        ok2, d2, p2 = core.transient_check(80.0, 20.0, 100.0, 25.0)
        self.assertEqual((ok1, d1, p1), (ok2, d2, p2))
        self.assertAlmostEqual(mod.ripple_percent(29.0, 27.0, 28.0),
                               core.ripple_percent(29.0, 27.0, 28.0),
                               places=6)

    def test_rf_susceptibility_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/radio-frequency-susceptibility")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertAlmostEqual(
            mod.required_amp_power_for_test(100.0, 3.0, 3.0, 3.0, 6.0),
            core.required_amp_power_for_test(100.0, 3.0, 3.0, 3.0, 6.0),
            delta=1.0)
        self.assertAlmostEqual(mod.cs114_limit_dbu_a("B"),
                               core.cs114_limit_dbu_a("B"), places=6)
        m1, o1 = mod.margin_check_dbu(60.0, 65.7)
        m2, o2 = core.margin_check_dbu(60.0, 65.7)
        self.assertAlmostEqual(m1, m2, places=6)
        self.assertEqual(o1, o2)

    def test_rf_emissions_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/radio-frequency-emissions")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertAlmostEqual(mod.ce102_limit_db(150e3, "A"),
                               core.ce102_limit_db(150e3, "A"), places=6)
        self.assertAlmostEqual(mod.re102_limit_db(100e6, "A"),
                               core.re102_limit_db(100e6, "A"), places=6)
        self.assertEqual(mod.worst_case_frequency([50e3, 150e3], [8.0, 5.0])[0],
                         core.worst_case_frequency([50e3, 150e3],
                                                   [8.0, 5.0])[0])

    def test_environmental_leaf_agrees(self):
        mod = load_leaf_logic("avionics/do160/environmental-qualification")
        core = self._core()
        self.assertIsNotNone(mod)
        self.assertEqual(mod.section_name(25), core.section_name(25))
        self.assertEqual(mod.temperature_category_range("B1"),
                         core.temperature_category_range("B1"))
        self.assertEqual(mod.matrix_complete(sorted(core.SECTIONS), "B1"),
                         core.matrix_complete(sorted(core.SECTIONS), "B1"))


if __name__ == "__main__":
    unittest.main()
