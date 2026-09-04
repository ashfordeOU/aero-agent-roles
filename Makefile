# Role gates (mirror AeroSkills 5-gate discipline, role-sized)
#   gate 1 role-lint     structure + frontmatter + bound-skill resolution
#   gate 2 role-tests    every role's offline test suite passes
#   gate 3 no-verbatim   templates/SOURCES never reproduce proprietary text
#   gate 4 security      no local info / creds / machine paths (tripwire)
#   gate 5 manifest      manifest.json matches tree (no hand-carried drift)

validate: role-lint role-tests no-verbatim security manifest
	@echo "Aero Agent Roles validate: PASS (5/5 REAL gates)"

role-lint:
	@python3 scripts/role-lint.py

role-tests:
	@bash scripts/gate-role-tests.sh

no-verbatim:
	@bash scripts/gate-no-verbatim.sh

security:
	@bash scripts/gate-security.sh

manifest:
	@python3 scripts/gen_manifest.py --check

visuals-check:
	@echo "roles repo: no visuals yet (site sync later)"

.PHONY: validate role-lint role-tests no-verbatim security manifest visuals-check
