#!/usr/bin/env python3
"""Gate: every capability a role declares is defined, and nothing is dead.

This corpus declares `tools_allowed` per role. A harness turns those terms
into an effective permission by computing min(ceiling, requested). That
computation is only as good as the map in ops/contracts/capability-map.json,
and the map is only useful if it stays in step with the roles:

  * a term a role declares that the map does not define resolves to an EMPTY
    requirement in the harness -- and an empty requirement is byte-for-byte
    indistinguishable from a correctly-restrictive role. A typo would
    silently produce the most locked-down role in the corpus and pass;
  * a term the map defines that no role declares is dead weight that will be
    trusted the first time somebody copies it into a new role without
    checking whether it was ever right.

Both directions, one gate. Offline, stdlib only, no harness import: this
corpus must be checkable by someone who has only this corpus.

Exit 0 clean, 1 on a finding.
"""

import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "ops", "contracts", "capability-map.json")
CONTEXT = "aero-capability-map/v1"
KEY = "tools_allowed"

_FRONTMATTER = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
                          re.S)
_ITEM = re.compile(r"^[ \t]+-[ \t]+(.+?)[ \t]*$")
_KEY = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*?)[ \t]*$")


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def declared(text):
    m = _FRONTMATTER.match(text or "")
    if not m:
        return []
    terms, in_list = [], False
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _ITEM.match(line)
        if in_list and item:
            terms.append(unquote(item.group(1)))
            continue
        k = _KEY.match(line)
        if k:
            in_list = False
            if k.group(1) != KEY:
                continue
            v = k.group(2)
            if v.startswith("[") and v.endswith("]"):
                terms += [unquote(p) for p in v[1:-1].split(",") if p.strip()]
            elif v:
                terms.append(unquote(v))
            else:
                in_list = True
    return terms


def main():
    if not os.path.isfile(MAP):
        print("FAIL gate-capabilities: %s is missing -- with no map, every "
              "role's permissions are undefined" % MAP, file=sys.stderr)
        return 1
    try:
        doc = json.load(io.open(MAP, encoding="utf-8"))
    except ValueError as exc:
        print("FAIL gate-capabilities: %s is not valid JSON: %s" % (MAP, exc),
              file=sys.stderr)
        return 1
    if doc.get("context") != CONTEXT:
        print("FAIL gate-capabilities: %s carries context %r, not %r"
              % (MAP, doc.get("context"), CONTEXT), file=sys.stderr)
        return 1
    caps = doc.get("capabilities") or {}
    if not caps:
        print("FAIL gate-capabilities: the map defines 0 capabilities",
              file=sys.stderr)
        return 1
    for term, tools in sorted(caps.items()):
        if not isinstance(tools, list) or not tools:
            print("FAIL gate-capabilities: %r requires nothing -- an empty "
                  "requirement is indistinguishable from an unfinished one"
                  % term, file=sys.stderr)
            return 1

    roles_dir = os.path.join(ROOT, "roles")
    docs = []
    for entry in sorted(os.listdir(roles_dir)) if os.path.isdir(roles_dir) else []:
        p = os.path.join(roles_dir, entry, "ROLE.md")
        if os.path.isfile(p):
            docs.append((entry, io.open(p, encoding="utf-8").read()))
    if not docs:
        print("FAIL gate-capabilities: 0 role documents found under %s -- "
              "this run checked nothing" % roles_dir, file=sys.stderr)
        return 1

    findings, used = 0, set()
    for name, text in docs:
        terms = declared(text)
        if not terms:
            print("FAIL gate-capabilities: role %s declares no %s -- a "
                  "harness that requires a grant would give it none"
                  % (name, KEY), file=sys.stderr)
            findings += 1
            continue
        used.update(terms)
        for term in terms:
            if term not in caps:
                print("FAIL gate-capabilities: role %s declares %r, which "
                      "ops/contracts/capability-map.json does not define -- "
                      "it would resolve to an empty grant and read as a "
                      "strict role" % (name, term), file=sys.stderr)
                findings += 1

    for term in sorted(set(caps) - used):
        print("FAIL gate-capabilities: the map defines %r and no role "
              "declares it -- a dead entry is one that gets copied into a "
              "new role without ever having been right" % term,
              file=sys.stderr)
        findings += 1

    if findings:
        print("FAIL gate-capabilities: %d finding(s) across %d role(s)"
              % (findings, len(docs)), file=sys.stderr)
        return 1
    print("PASS gate-capabilities: %d role(s), %d distinct capability "
          "term(s), all defined and all used" % (len(docs), len(used)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
