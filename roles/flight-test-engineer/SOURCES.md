# SOURCES.md - Flight Test Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR-25, public domain) | V-speed factors (25.107/25.125 context), flutter margin and damping (25.629), stall warning and recovery (25.203/25.207), maneuvering speed (25.335), climb gradient context (25.121) | false |
| EASA CS-25 (free download) | same context as FAR-25 for European basis | false |
| MIL-STD-1797A | handling qualities evaluation during flight test | false |
| FAA Flight Test Guide (AC) | accepted flight test methodology | false |
| Kimberlin, Flight Testing of Fixed-Wing Aircraft | flight test build-up methods (book) | true |
| Ward, Introduction to Flight Test Engineering | methods (book) | true |
| ISA atmosphere (public physics) | altitude/Mach grid reduction (sigma, speed of sound) | false |

The flight test plan and envelope expansion report in `templates/` and
the numbers produced by `core/flight_test_core.py` come from the domain
rules encoded in the bound Aero Agent Skills flight-test-operations
leaves (v-speeds, envelope-expansion, flutter-testing,
stall-characteristics-testing, climb-performance-flight-test,
flight-test-safety, flight-test-planning), which themselves paraphrase
the FAR/CS-25 context and common flight test practice. Summary-not-copy
per STANDARDS.md; no proprietary text is reproduced. Worked-example
flight data in the template is explicitly labeled simulated.
