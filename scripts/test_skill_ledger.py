#!/usr/bin/env python3
"""The ledger, and the lint that reads it, go red where they should.

The defect these pin is a SKIP that read as a pass: role-lint resolved
bound leaves against a checkout in the developer's home directory and
skipped when it was absent -- which is public CI, an npm tarball, and every
fresh clone. Each case below is one way that could come back.

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
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen_skill_ledger as L   # noqa: E402


class TheShippedLedger(unittest.TestCase):
    def test_it_exists_and_is_self_consistent(self):
        doc = L.load()
        self.assertIsNotNone(doc, "the ledger is missing")
        self.assertGreater(doc["leaf_count"], 100)
        self.assertEqual(doc["leaf_count"], len(doc["leaves"]))

    def test_the_digest_covers_the_list(self):
        doc = L.load()
        self.assertEqual(L.digest(doc["leaves"]), doc["leaf_set_digest"])

    def test_every_binding_in_this_corpus_resolves_against_it(self):
        """The invariant, checked here and not only by the lint."""
        import re
        pinned = set(L.load()["leaves"])
        total = unresolved = 0
        rdir = os.path.join(ROOT, "roles")
        for name in sorted(os.listdir(rdir)):
            p = os.path.join(rdir, name, "ROLE.md")
            if not os.path.isfile(p):
                continue
            text = io.open(p, encoding="utf-8").read()
            m = re.search(r"^skills_bound:\s*\n((?:\s+-\s+.+\n)+)", text, re.M)
            if not m:
                continue
            for line in m.group(1).splitlines():
                slug = line.strip().lstrip("- ").strip()
                total += 1
                if slug not in pinned:
                    unresolved += 1
        self.assertGreater(total, 100, "0 bindings read: the parser missed")
        self.assertEqual(unresolved, 0)


class LedgerRefusals(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="aero-ledger-")
        self.saved = L.LEDGER
        L.LEDGER = os.path.join(self.work, "skills-leaves.json")

    def tearDown(self):
        L.LEDGER = self.saved
        shutil.rmtree(self.work, ignore_errors=True)

    def corpus(self, *slugs):
        root = os.path.join(self.work, "skills-corpus")
        for slug in slugs:
            d = os.path.join(root, "skills", *slug.split("/"))
            os.makedirs(d, exist_ok=True)
            io.open(os.path.join(d, "SKILL.md"), "w",
                    encoding="utf-8").write("# %s\n" % slug)
        return root

    def test_an_empty_corpus_produces_no_ledger(self):
        empty = os.path.join(self.work, "empty")
        os.makedirs(os.path.join(empty, "skills"))
        self.assertEqual(L.write(empty), 1)
        self.assertFalse(os.path.isfile(L.LEDGER))

    def test_a_round_trip(self):
        root = self.corpus("fam/pack/one", "fam/pack/two")
        self.assertEqual(L.write(root), 0)
        self.assertEqual(sorted(L.load()["leaves"]),
                         ["fam/pack/one", "fam/pack/two"])
        self.assertEqual(L.check(root), 0)

    def test_a_hand_edited_ledger_is_caught(self):
        root = self.corpus("fam/pack/one")
        L.write(root)
        doc = json.load(io.open(L.LEDGER, encoding="utf-8"))
        doc["leaves"].append("fam/pack/smuggled")
        json.dump(doc, io.open(L.LEDGER, "w", encoding="utf-8"))
        with self.assertRaises(ValueError):
            L.load()

    def test_an_emptied_ledger_is_refused_not_treated_as_zero_leaves(self):
        root = self.corpus("fam/pack/one")
        L.write(root)
        doc = json.load(io.open(L.LEDGER, encoding="utf-8"))
        doc["leaves"] = []
        json.dump(doc, io.open(L.LEDGER, "w", encoding="utf-8"))
        with self.assertRaises(ValueError):
            L.load()

    def test_a_retired_leaf_fails_the_check(self):
        root = self.corpus("fam/pack/one", "fam/pack/two")
        L.write(root)
        shutil.rmtree(os.path.join(root, "skills", "fam", "pack", "two"))
        self.assertEqual(L.check(root), 1)

    def test_a_new_leaf_is_stale_not_broken(self):
        """Adding leaves cannot break a binding -- renaming can."""
        root = self.corpus("fam/pack/one")
        L.write(root)
        self.corpus("fam/pack/three")
        self.assertEqual(L.check(root), 0)

    def test_a_missing_ledger_fails_the_check(self):
        root = self.corpus("fam/pack/one")
        self.assertEqual(L.check(root), 1)

    def test_a_ledger_with_the_wrong_context(self):
        root = self.corpus("fam/pack/one")
        L.write(root)
        doc = json.load(io.open(L.LEDGER, encoding="utf-8"))
        doc["context"] = "something-else"
        json.dump(doc, io.open(L.LEDGER, "w", encoding="utf-8"))
        with self.assertRaises(ValueError):
            L.load()


class TheLintNeverSkips(unittest.TestCase):
    """The defect itself: no corpus used to mean no check."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="aero-lint-")
        self.repo = os.path.join(self.work, "roles-repo")
        shutil.copytree(os.path.join(ROOT, "scripts"),
                        os.path.join(self.repo, "scripts"))
        shutil.copytree(os.path.join(ROOT, "roles"),
                        os.path.join(self.repo, "roles"))
        os.makedirs(os.path.join(self.repo, "ops", "contracts"))

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def lint(self):
        env = dict(os.environ)
        env.pop("AEROSKILLS_DEV", None)
        return subprocess.run(
            [sys.executable, os.path.join(self.repo, "scripts",
                                          "role-lint.py")],
            capture_output=True, text=True, env=env, cwd=self.repo)

    def test_with_no_corpus_and_no_ledger_it_fails(self):
        r = self.lint()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refusing to pass a check that examined nothing",
                      r.stdout)

    def test_with_the_ledger_alone_it_checks_and_passes(self):
        shutil.copy(os.path.join(ROOT, "ops", "contracts",
                                 "skills-leaves.json"),
                    os.path.join(self.repo, "ops", "contracts"))
        r = self.lint()
        self.assertEqual(r.returncode, 0, r.stdout[-1500:])
        self.assertIn("resolved against the pinned ledger", r.stdout)

    def test_a_broken_binding_is_caught_against_the_ledger_alone(self):
        """The whole point: the ledger is a CHECK, not a formality."""
        src = json.load(io.open(os.path.join(
            ROOT, "ops", "contracts", "skills-leaves.json"), encoding="utf-8"))
        src["leaves"] = [s for s in src["leaves"]
                         if not s.startswith("space-systems/adcs/")]
        src["leaf_count"] = len(src["leaves"])
        src["leaf_set_digest"] = L.digest(src["leaves"])
        json.dump(src, io.open(os.path.join(
            self.repo, "ops", "contracts", "skills-leaves.json"), "w",
            encoding="utf-8"))
        r = self.lint()
        self.assertEqual(r.returncode, 1)
        self.assertIn("unresolved against the pinned ledger", r.stdout)

    def test_the_verdict_states_its_denominator(self):
        shutil.copy(os.path.join(ROOT, "ops", "contracts",
                                 "skills-leaves.json"),
                    os.path.join(self.repo, "ops", "contracts"))
        r = self.lint()
        self.assertRegex(r.stdout, r"\d+ binding\(s\) resolved against")

    def test_no_developer_home_path_is_shipped(self):
        """The default used to broadcast the developer's directory layout."""
        src = io.open(os.path.join(ROOT, "scripts", "role-lint.py"),
                      encoding="utf-8").read()
        # split so this assertion does not itself contain the string
        self.assertNotIn("~/comp" + "any-ops", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
