#!/usr/bin/env python3
"""Generate (or verify) the pinned ledger of skills-corpus leaves.

WHY THIS FILE EXISTS
--------------------
role-lint.py checks that every leaf a role binds actually exists. It did
that by looking for a skills checkout on disk and SKIPPING when there was
none -- so in public CI, in an npm tarball, and on any machine but the
developer's, the binding check passed by not running. The skip was printed,
which is better than nothing and is not a check.

A pinned ledger removes the reason to skip. It is the set of leaf slugs a
named skills corpus contained, with that corpus's digest, committed here.
role-lint resolves against a live corpus when one is handed to it and
against this ledger otherwise, and fails when it has neither.

WHAT IT DOES NOT COVER, SAID PLAINLY
------------------------------------
A ledger is a snapshot. If the skills corpus renames a leaf tomorrow, this
file still says the old name and role-lint still passes. That gap is closed
from the other side: the skills corpus carries the reciprocal contract
(ops/contracts/role-bindings.json there) and its own publish gate refuses
to export a tree that has stopped satisfying it. Each side catches what the
other cannot, and `make gate-bindings` in the harness catches everything
when both corpora are present at once.

Usage:
  gen_skill_ledger.py <skills-root>            write the ledger
  gen_skill_ledger.py --check <skills-root>    verify it is still accurate
"""

import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "ops", "contracts", "skills-leaves.json")
CONTEXT = "aero-skills-leaf-ledger/v1"


def leaves(skills_root):
    """family/pack/leaf for every leaf in the corpus handed in."""
    base = os.path.join(skills_root, "skills")
    if not os.path.isdir(base):
        base = skills_root
    depth = base.count(os.sep)
    out = set()
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__")]
        if "SKILL.md" in fn and dp.count(os.sep) == depth + 3:
            out.add(os.path.relpath(dp, base))
    return sorted(out)


def digest(slugs):
    """A digest of the SET, not of the tree.

    Two checkouts of the same corpus differ in mtimes, .git and build
    droppings; what this ledger is about is which leaves exist. Hashing the
    sorted slug list means a re-clone agrees and a rename does not.
    """
    return hashlib.sha256("\n".join(slugs).encode("utf-8")).hexdigest()


def load():
    if not os.path.isfile(LEDGER):
        return None
    with io.open(LEDGER, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("context") != CONTEXT:
        raise ValueError("%s carries context %r, not %r"
                         % (LEDGER, doc.get("context"), CONTEXT))
    slugs = doc.get("leaves") or []
    if not slugs:
        raise ValueError("%s lists no leaves -- every binding would read as "
                         "broken, which is louder and more misleading than "
                         "saying the ledger is empty" % LEDGER)
    if digest(slugs) != doc.get("leaf_set_digest"):
        raise ValueError("%s: the leaf list does not hash to the digest it "
                         "carries -- it was edited by hand" % LEDGER)
    return doc


def write(skills_root):
    slugs = leaves(skills_root)
    if not slugs:
        print("FAIL ledger: 0 leaves found under %s -- refusing to write a "
              "ledger that would make every binding look broken" % skills_root,
              file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    doc = {
        "_comment": [
            "The leaves a named skills corpus contained, pinned so the",
            "binding check never has to skip for want of a checkout.",
            "",
            "GENERATED -- never edit by hand. leaf_set_digest is over the",
            "sorted slug list, so a hand edit is caught on the next read.",
            "",
            "Refresh with: make skills-ledger SKILLS=<path to aero-agent-skills>",
        ],
        "context": CONTEXT,
        "leaf_count": len(slugs),
        "leaf_set_digest": digest(slugs),
        "leaves": slugs,
    }
    with io.open(LEDGER, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("PASS ledger: wrote %d leaf slug(s), digest %s"
          % (len(slugs), doc["leaf_set_digest"][:16]))
    return 0


def check(skills_root):
    try:
        doc = load()
    except ValueError as exc:
        print("FAIL ledger: %s" % exc, file=sys.stderr)
        return 1
    if doc is None:
        print("FAIL ledger: %s does not exist, so role-lint has nothing to "
              "resolve against when no skills checkout is present" % LEDGER,
              file=sys.stderr)
        return 1
    live = leaves(skills_root)
    if not live:
        print("FAIL ledger: 0 leaves found under %s -- nothing to compare"
              % skills_root, file=sys.stderr)
        return 1
    pinned = set(doc["leaves"])
    gone = sorted(pinned - set(live))
    added = sorted(set(live) - pinned)
    for slug in gone[:10]:
        print("FAIL ledger: %s is pinned here but is no longer in the skills "
              "corpus -- a retired or renamed leaf is a qualification event"
              % slug, file=sys.stderr)
    if gone:
        print("FAIL ledger: %d pinned leaf/leaves no longer exist (%d live, "
              "%d pinned)" % (len(gone), len(live), len(pinned)),
              file=sys.stderr)
        return 1
    if added:
        print("STALE ledger: %d new leaf/leaves are not pinned (%d live, %d "
              "pinned). Adding leaves cannot break a binding, so this is not "
              "a failure -- but a role bound to one of them would resolve "
              "only where a live corpus is present. Refresh with "
              "`make skills-ledger SKILLS=<path>`." % (len(added), len(live),
                                                       len(pinned)))
    print("PASS ledger: %d pinned leaf/leaves all still present in a corpus "
          "of %d" % (len(pinned), len(live)))
    return 0


def main(argv):
    args = [a for a in argv[1:] if a != "--check"]
    if len(args) != 1:
        print("usage: gen_skill_ledger.py [--check] <skills-root>",
              file=sys.stderr)
        return 2
    root = os.path.abspath(args[0])
    if not os.path.isdir(root):
        print("FAIL ledger: %s is not a directory" % root, file=sys.stderr)
        return 2
    return check(root) if "--check" in argv else write(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
