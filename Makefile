# Role gates (mirror AeroSkills 5-gate discipline, role-sized)
#   gate 1 role-lint     structure + frontmatter + bound-skill resolution
#   gate 2 role-tests    every role's offline test suite passes
#   gate 3 no-verbatim   templates/SOURCES never reproduce proprietary text
#   gate 4 security      no local info / creds / machine paths (tripwire)
#   gate 5 manifest      manifest.json matches tree (no hand-carried drift)
#   gate 6 independence  verifier is not the generator (no self-graded output)
# growth gates (wave doctrine)
#   coverage-check       COVERAGE-MATRIX.md up to date (numbers-via-script)
#   release-law          reports milestone / due release (non-blocking)

validate: role-lint role-tests no-verbatim security manifest independence
	@echo "Aero Agent Roles validate: PASS (6/6 REAL gates)"

growth: coverage-check release-law stale-guard
	@echo "Aero Agent Roles growth: coverage + release law + stale stats checked"

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

independence:
	@bash scripts/gate-verify-independence.sh

coverage-check:
	@python3 scripts/coverage-matrix.py --check

release-law:
	@python3 scripts/release-law.py

visuals:
	@python3 scripts/gen_visuals.py
	@python3 scripts/gen_npm_manifest.py
	@python3 scripts/gen_jetbrains_catalog.py

visuals-check:
	@python3 scripts/gen_visuals.py --check
	@python3 scripts/gen_npm_manifest.py --check
	@python3 scripts/gen_jetbrains_catalog.py --check

package-test:
	@node packages/aero-agent-roles/test/smoke.mjs

about:
	@bash ops/automation/update-about.sh

stale-guard:
	@bash scripts/roles-stale-guard.sh

.PHONY: validate growth role-lint role-tests no-verbatim security manifest independence coverage-check release-law visuals visuals-check package-test about stale-guard
