# Security Policy

Aero Agent Roles takes security and trust seriously. This policy covers
the repository code and automation (scripts/, ops/, core/) and the role
content it ships.

## Reporting a vulnerability

Report suspected vulnerabilities PRIVATELY. Do not open a public issue
or pull request that describes the vulnerability before a fix is
available.

- Preferred: a GitHub private security advisory — this repository's
  "Security" tab → "Report a vulnerability".
- Alternative: email the maintainers (contact@ashforde.org) with
  "SECURITY" in the subject.

You will receive a response within 5 business days. Please do not
disclose the issue publicly until a fix has been released.

## Roles are code

A role is an executable worker: `core/*_core.py` runs on your machine
when you invoke `cli.py`. Review the core engine, cli.py, and any
bound-skill logic before you run a role, the same way you would review
any code dependency you install. Roles carry the same trust model as
the skills they bind: content is folders that can carry scripts, and
agent hosts execute what they load.

## What this repo never contains

- No secrets, credentials, or token values (the security gate enforces
  this on every commit — `make validate` gate 4).
- No local machine paths or user info that could identify a private
  environment (paths derive from `$HOME` at runtime where needed).
- No proprietary standards text (see STANDARDS.md — summary only).

## Reporting unsafe content

If a role, template, or bound skill references controlled data, appears
to reproduce proprietary standard text, or behaves unexpectedly at
runtime, report it through the same private channels above.

## Scope

In scope: repository code, automation, role cores, cli.py, templates,
and published packages. Out of scope: upstream Aero Agent Skills leaf
logic (report those to the skills repository), and the behavior of
third-party agent hosts that load this content.
