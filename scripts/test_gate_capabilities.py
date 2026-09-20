#!/usr/bin/env python3
"""gate-capabilities goes red on each defect it claims to catch.

Mirrors the skills corpus's negative-control doctrine: baseline green, one
planted defect at a time, and the red must NAME the planted defect. A red for
an unrelated reason proves the gate runs, not that it works.

The gate reads this repository's own tree, so each case runs against a COPY
in a temp dir and the working tree is never modified.

Offline, stdlib only.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class GateRed(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="aero-capgate-")
        self.root = os.path.join(self.work, "roles-repo")
        os.makedirs(os.path.join(self.root, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "gate-capabilities.py"),
                    os.path.join(self.root, "scripts"))
        os.makedirs(os.path.join(self.root, "ops", "contracts"))
        shutil.copy(
            os.path.join(ROOT, "ops", "contracts", "capability-map.json"),
            os.path.join(self.root, "ops", "contracts"))
        # Two synthetic roles using exactly the shipped terms.
        self.roles = os.path.join(self.root, "roles")
        for name, terms in (("alpha", "[stdlib, offline-file-processing]"),
                            ("beta", "[stdlib, cea-cli]")):
            d = os.path.join(self.roles, name)
            os.makedirs(d)
            io.open(os.path.join(d, "ROLE.md"), "w", encoding="utf-8").write(
                "---\ntype: role\nname: %s\ntools_allowed: %s\n---\n\n# %s\n"
                % (name, terms, name))
        self.gate = os.path.join(self.root, "scripts", "gate-capabilities.py")
        self.map = os.path.join(self.root, "ops", "contracts",
                                "capability-map.json")

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def run_gate(self):
        return subprocess.run([sys.executable, self.gate],
                              capture_output=True, text=True)

    def set_map(self, caps):
        doc = json.load(io.open(self.map, encoding="utf-8"))
        doc["capabilities"] = caps
        json.dump(doc, io.open(self.map, "w", encoding="utf-8"))

    def used_terms(self):
        return {"stdlib": ["fs_read"],
                "offline-file-processing": ["fs_read", "fs_write"],
                "cea-cli": ["shell_rw", "fs_read", "fs_write"]}

    def test_baseline_is_green(self):
        self.set_map(self.used_terms())
        r = self.run_gate()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASS gate-capabilities", r.stdout)
        self.assertIn("2 role(s)", r.stdout)

    def test_the_shipped_map_covers_the_shipped_roles(self):
        """The real check, against the real tree, run once."""
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts",
                                          "gate-capabilities.py")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_role_declaring_an_undefined_term(self):
        caps = self.used_terms()
        del caps["cea-cli"]
        self.set_map(caps)
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("cea-cli", r.stderr)
        self.assertIn("empty grant", r.stderr)

    def test_a_defined_term_no_role_uses(self):
        caps = self.used_terms()
        caps["ghost-cli"] = ["fs_read"]
        self.set_map(caps)
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost-cli", r.stderr)
        self.assertIn("dead entry", r.stderr)

    def test_a_term_requiring_nothing(self):
        caps = self.used_terms()
        caps["stdlib"] = []
        self.set_map(caps)
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("requires nothing", r.stderr)

    def test_a_role_declaring_no_capabilities(self):
        io.open(os.path.join(self.roles, "alpha", "ROLE.md"), "w",
                encoding="utf-8").write("---\nname: alpha\n---\n\n# alpha\n")
        self.set_map(self.used_terms())
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("declares no tools_allowed", r.stderr)

    def test_a_missing_map_is_a_failure_not_a_skip(self):
        os.remove(self.map)
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing", r.stderr)

    def test_an_empty_roles_tree_is_a_failure_not_a_pass(self):
        shutil.rmtree(self.roles)
        os.makedirs(self.roles)
        self.set_map(self.used_terms())
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("checked nothing", r.stderr)

    def test_a_map_with_the_wrong_context(self):
        doc = json.load(io.open(self.map, encoding="utf-8"))
        doc["context"] = "not-a-capability-map"
        doc["capabilities"] = self.used_terms()
        json.dump(doc, io.open(self.map, "w", encoding="utf-8"))
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("context", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
