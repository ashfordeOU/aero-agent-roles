# Software Product Assurance Compliance Matrix (ECSS-Q-ST-80C Rev.2)

> DRAFT - prepared by an agent for review. Not a statement of compliance until signed off by the responsible human.

Status: DRAFT. Human sign-off required.

## 1. Scope and basis

- Project: EXAMPLE-SAT on-board software (worked example, not a real project)
- Standard: ECSS-Q-ST-80C Rev.2 (30 April 2025), referenced summary-only (clause identifiers with topic labels of our own wording)
- Software criticality category: **B**
- Category derivation: highest function severity I gives base category A; compensating provision(s) hardware lower A to B
- Constraint: each provision must meet the system dependability and safety requirements before the lower category is claimed
- Security sensitive: no
- Project scope: reuse
- Target review: preliminary design review (PDR)
- Clause list: the full requirement list of the standard (264 clauses)
- Evidence index: example/evidence.csv (250 rows)
- Document folder: example/docs/ (14 files)
- Review pack: example/pdr-pack.csv
- Measurement set: example/metrics.csv

## 2. Coverage summary

Coverage: 264 clauses, 226 applicable; compliant 129, partially 91, not compliant 6, not applicable 38; compliant fraction 0.5708; evidenced fraction 0.9735; traced fraction 0.9646.

| Measure | Value |
|---|---|
| Clauses in the matrix | 264 |
| Applicable clauses | 226 |
| Compliant | 129 |
| Partially compliant | 91 |
| Not compliant (including no evidence) | 6 |
| Not applicable | 38 |
| Compliant fraction of applicable clauses | 0.5708 |
| Applicable clauses with a document reference | 0.9735 |
| Applicable clauses traced to a real file | 0.9646 |
| Rows with at least one gap | 36 |

Open gaps: 129.

## 3. Compliance matrix

| Clause | Topic | Tailoring | Status | Justification | Evidence | Gaps |
|---|---|---|---|---|---|---|
| 5.1.1 | assurance organisation set-up | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.2.1 | who answers for what | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.2.2 | who answers for what | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.2.3 | who answers for what | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.3.1 | staff and means | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.3.2 | staff and means | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.4.1 | the assurance lead | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.4.2 | the assurance lead | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.5.1 | skills and training | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.5.2 | skills and training | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.5.3 | skills and training | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.1.5.4 | skills and training | applicable | compliant |  | EX-SPAP-001 section 3 |  |
| 5.2.1.1 | planning and control of the programme | applicable | compliant |  | EX-SPAP-001 section 4.1 |  |
| 5.2.1.2 | planning and control of the programme | applicable | compliant |  | EX-SPAP-001 section 4.1 |  |
| 5.2.1.3 | planning and control of the programme | applicable | compliant |  | EX-SPAP-001 section 4.1 |  |
| 5.2.1.4 | planning and control of the programme | applicable | compliant |  | EX-SPAP-001 section 4.1 |  |
| 5.2.1.5 | planning and control of the programme | applicable | compliant |  | EX-SPAP-001 section 4.1 |  |
| 5.2.2.1 | assurance reporting | applicable | compliant |  | EX-SPAR-2026-Q3 section 1 |  |
| 5.2.2.2 | assurance reporting | applicable | compliant |  | EX-SPAR-2026-Q3 section 1 |  |
| 5.2.2.3 | assurance reporting | applicable | compliant |  | EX-SPAR-2026-Q3 section 1 |  |
| 5.2.3 | audit programme | applicable | compliant |  | EX-SPAP-001 section 4.3 |  |
| 5.2.4 | alert handling | applicable | partially-compliant | alert handling follows the company procedure |  | no-evidence-reference |
| 5.2.5.1 | problem reporting | applicable | compliant |  | EX-SPR-LOG section 1 |  |
| 5.2.5.2 | problem reporting | applicable | compliant |  | EX-SPR-LOG section 1 |  |
| 5.2.5.3 | problem reporting | applicable | compliant |  | EX-SPR-LOG section 1 |  |
| 5.2.5.4 | problem reporting | applicable | compliant |  | EX-SPR-LOG section 1 |  |
| 5.2.6.1 | nonconformance handling | applicable | compliant |  | EX-SPAP-001 section 4.6 |  |
| 5.2.6.2 | nonconformance handling | applicable | compliant |  | EX-SPAP-001 section 4.6 |  |
| 5.2.7.1 | quality model | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 5.2.7.2 | quality model | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 5.3.1 | risk handling | applicable | compliant |  | EX-SPAP-001 section 6 |  |
| 5.3.2.1 | critical items | applicable | compliant |  | EX-SPAP-001 section 6 |  |
| 5.3.2.2 | critical items | applicable | compliant |  | EX-SPAP-001 section 6 |  |
| 5.4.1.1 | choosing suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.1.2 | choosing suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.2.1 | what suppliers are held to | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.2.2 | what suppliers are held to | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.3.1 | watching suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.3.2 | watching suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.3.3 | watching suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.3.4 | watching suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.4 | category flow-down to suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.4.5 | security flow-down to suppliers | applicable | not-applicable | no software subcontractor on this project | EX-SPAP-001 section 7 | na-conflicts-with-tailoring |
| 5.5.1 | purchase documents | applicable | compliant |  | EX-SDP-001 section 6.1 |  |
| 5.5.2 | bought-in component list | applicable | compliant |  | EX-SDP-001 section 6.2 |  |
| 5.5.3 | purchase data | applicable | compliant |  | EX-SDP-001 section 6.3 |  |
| 5.5.4 | marking of bought items | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 6.4, evidence expected at CDR | EX-SDP-001 section 6.4 |  |
| 5.5.5 | incoming checks | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 6.4, evidence expected at CDR | EX-SDP-001 section 6.4 |  |
| 5.5.6 | export constraints | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 6.4, evidence expected at CDR | EX-SDP-001 section 6.4 |  |
| 5.6.1.1 | methods and tools chosen | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.6.1.2 | methods and tools chosen | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.6.1.3 | methods and tools chosen | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.6.2.1 | choice of development environment | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.6.2.2 | choice of development environment | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.6.2.3 | choice of development environment | applicable | compliant |  | EX-SDP-001 section 7 |  |
| 5.7.1 | capability assessment | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.2.1 | how assessments are run | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.2.2 | how assessments are run | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.2.3 | how assessments are run | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.2.4 | how assessments are run | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.3.1 | improving the process | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.3.2 | improving the process | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 5.7.3.3 | improving the process | applicable | compliant |  | EX-SPAP-001 section 9 |  |
| 6.1.1 | defining the life cycle | applicable | compliant |  | EX-SDP-001 section 2 |  |
| 6.1.2 | process targets | applicable | compliant |  | EX-SDP-001 section 2 |  |
| 6.1.3 | reviewing the life cycle | applicable | compliant |  | EX-SDP-001 | reference-without-section |
| 6.1.4 | means for the life cycle | applicable | compliant |  | EX-SDP-001 section 2 |  |
| 6.1.5 | validation timing | applicable | compliant |  | EX-SDP-001 section 2 |  |
| 6.2.1.1 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.2 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.3 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.4 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.5 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.6 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.7 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.8 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.1.9 | process documentation | applicable | compliant |  | EX-SDP-001 section 3 |  |
| 6.2.2.1 | dependability and safety of software | applicable | compliant |  | EX-DSA-001 section 2 |  |
| 6.2.2.2 | dependability and safety of software | applicable | compliant |  | EX-DSA-001 section 3 |  |
| 6.2.2.3 | dependability and safety of software | applicable | compliant |  | EX-DSA-001 section 2.2 |  |
| 6.2.2.4 | dependability and safety of software | applicable | compliant |  | EX-DSA-001 section 3.2 |  |
| 6.2.2.5 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.2.6 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.2.7 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.2.8 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.2.9 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.2.10 | dependability and safety of software | applicable | partially-compliant | software-level analysis refined at CDR; preliminary results in EX-DSA-001 4 | EX-DSA-001 section 4 |  |
| 6.2.3.2 | critical software | applicable | compliant |  | EX-SPAP-001 section 8.1 |  |
| 6.2.3.3 | critical software | applicable | compliant |  | EX-SPAP-001 section 8.2 |  |
| 6.2.3.4 | critical software | applicable | compliant |  | EX-SPAP-001 section 8.3 |  |
| 6.2.3.5 | critical software | applicable | compliant |  | EX-SPAP-001 section 8.4 |  |
| 6.2.3.6 | critical software | applicable | partially-compliant | activity falls after PDR; planned in EX-SPAP-001 8.5, evidence expected at CDR | EX-SPAP-001 section 8.5 |  |
| 6.2.3.7 | critical software | applicable | partially-compliant | activity falls after PDR; planned in EX-SPAP-001 8.5, evidence expected at CDR | EX-SPAP-001 section 8.5 |  |
| 6.2.3.8 | critical software | applicable | partially-compliant | activity falls after PDR; planned in EX-SPAP-001 8.5, evidence expected at CDR | EX-SPAP-001 section 8.5 |  |
| 6.2.4.1 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.2 | configuration management | applicable | not-compliant | internal audit: baseline register not kept current | EX-SCMP-001 section 2; EX-AUDIT-2026-01 finding F3 |  |
| 6.2.4.3 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.4 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.5 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.6 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.7 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.8 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.9 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.10 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.11 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.4.12 | configuration management | applicable | compliant |  | EX-SCMP-001 section 2 |  |
| 6.2.5.1 | process measurement | applicable | compliant |  | EX-SPAP-001 section 10 |  |
| 6.2.5.2 | process measurement | applicable | compliant |  | EX-SPAP-001 section 10 |  |
| 6.2.5.3 | process measurement | applicable | compliant |  | EX-SPAP-001 section 10 |  |
| 6.2.5.4 | process measurement | applicable | compliant |  | EX-SPAP-001 section 10 |  |
| 6.2.5.5 | process measurement | applicable | compliant |  | EX-SPAP-001 section 10 |  |
| 6.2.6.1 | verification | applicable | compliant |  | EX-SVERP-001 section 2 |  |
| 6.2.6.2 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.3 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.4 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.5 | verification | applicable | partially-compliant | downgraded from compliant: no cited document was found in the folder | EX-SVR-001 section 3 | document-not-found |
| 6.2.6.6 | verification | applicable | partially-compliant | downgraded from compliant: no cited document was found in the folder | EX-SVR-001 section 4 | document-not-found |
| 6.2.6.7 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.8 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.9 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.10 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.11 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.12 | verification | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 3, evidence expected at CDR | EX-SVERP-001 section 3 |  |
| 6.2.6.13 | verification | applicable | compliant |  | EX-SVERP-001 section 6 |  |
| 6.2.7.1 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.2 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.3 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.4 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.5 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.6 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.7 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.8 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.9 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.10 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.7.11 | reusing existing software | applicable | compliant |  | EX-SRF-001 section 2 |  |
| 6.2.8.1 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.2 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.3 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.4 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.5 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.6 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.8.7 | generated code | applicable | not-applicable | no automatic code generation is used | EX-SDP-001 section 7.3 | na-conflicts-with-tailoring |
| 6.2.9.1 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.2 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.3 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.4 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.5 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.6 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.9.7 | security | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.10.1 | security-sensitive software | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.10.2 | security-sensitive software | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.10.3 | security-sensitive software | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.2.10.4 | security-sensitive software | not-applicable | not-applicable | tailored out for software category B |  |  |
| 6.3.1.1 | system-level software requirements | applicable | compliant |  | EX-RB-001 section 2 |  |
| 6.3.1.2 | system-level software requirements | applicable | compliant |  | EX-RB-001 section 2 |  |
| 6.3.1.3 | system-level software requirements | applicable | compliant |  | EX-RB-001 section 2 |  |
| 6.3.2.1 | requirements analysis | applicable | compliant |  | EX-TS-001 section 2 |  |
| 6.3.2.2 | requirements analysis | applicable | compliant |  | EX-TS-001 section 2 |  |
| 6.3.2.3 | requirements analysis | applicable | compliant |  | EX-TS-001 section 2 |  |
| 6.3.2.4 | requirements analysis | applicable | compliant |  | EX-TS-001 section 2 |  |
| 6.3.2.5 | requirements analysis | applicable | compliant |  | EX-TS-001 section 2 |  |
| 6.3.3.1 | architecture and design | applicable | compliant |  | EX-DSTD-001 section 1 |  |
| 6.3.3.2 | architecture and design | applicable | compliant |  | EX-DSTD-001 section 2 |  |
| 6.3.3.3 | architecture and design | applicable | compliant |  | EX-SPAP-001 section 11.1 |  |
| 6.3.3.4 | architecture and design | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 4, evidence expected at CDR | EX-SDP-001 section 4 |  |
| 6.3.3.5 | architecture and design | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 4, evidence expected at CDR | EX-SDP-001 section 4 |  |
| 6.3.3.6 | architecture and design | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 4, evidence expected at CDR | EX-SDP-001 section 4 |  |
| 6.3.3.7 | architecture and design | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 4, evidence expected at CDR | EX-SDP-001 section 4 |  |
| 6.3.4.1 | coding | applicable | compliant |  | EX-CSTD-001 section 1 |  |
| 6.3.4.2 | coding | applicable | compliant |  | EX-CSTD-001 section 2 |  |
| 6.3.4.3 | coding | applicable | compliant |  | EX-SPAP-001 section 11.2 |  |
| 6.3.4.4 | coding | applicable | compliant |  | EX-CSTD-001 section 3 |  |
| 6.3.4.5 | coding | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 5, evidence expected at CDR | EX-SDP-001 section 5 |  |
| 6.3.4.6 | coding | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 5, evidence expected at CDR | EX-SDP-001 section 5 |  |
| 6.3.4.7 | coding | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 5, evidence expected at CDR | EX-SDP-001 section 5 |  |
| 6.3.4.8 | coding | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 5, evidence expected at CDR | EX-SDP-001 section 5 |  |
| 6.3.5.1 | testing and validation | applicable | compliant |  | EX-SVALP-001 section 2 |  |
| 6.3.5.2 | testing and validation | applicable | compliant |  | EX-SVALP-001 section 3 |  |
| 6.3.5.3 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.4 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.5 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.6 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.7 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.8 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.9 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.10 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.11 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.12 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.13 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.14 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.15 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.16 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.17 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.18 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.19 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.20 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.21 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.22 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.23 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.24 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.25 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.26 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.27 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.28 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.29 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.30 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.31 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.32 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.5.33 | testing and validation | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 4, evidence expected at QR | EX-SVALP-001 section 4 |  |
| 6.3.6.1 | delivery and installation | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.6.2 | delivery and installation | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.6.3 | delivery and installation | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.6.4 | delivery and installation | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.1 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.2 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.3 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.5 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.6 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.7.7 | acceptance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 8, evidence expected at AR | EX-SDP-001 section 8 |  |
| 6.3.8.1 | operations | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 9, evidence expected at ORR | EX-SDP-001 section 9 |  |
| 6.3.8.2 | operations | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 9, evidence expected at ORR | EX-SDP-001 section 9 |  |
| 6.3.8.3 | operations | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 9, evidence expected at ORR | EX-SDP-001 section 9 |  |
| 6.3.9.1 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.2 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.3 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.4 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.5 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.6 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 6.3.9.7 | maintenance | applicable | partially-compliant | activity falls after PDR; planned in EX-SDP-001 10, evidence expected at QR | EX-SDP-001 section 10 |  |
| 7.1.1 | deriving quality requirements | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.2 | quality requirements as numbers | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.3 | checking quality requirements | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.4 | product measures | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.5 | basic measures | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.6 | reporting measures | applicable | compliant |  | EX-SPAP-001 section 5 |  |
| 7.1.7 | numerical accuracy | applicable | partially-compliant | activity falls after PDR; planned in EX-SVERP-001 5, evidence expected at CDR | EX-SVERP-001 section 5 |  |
| 7.1.8 | maturity analysis | applicable | partially-compliant | maturity trend needs three reporting periods; one available | EX-SPAR-2026-Q3 section 3 |  |
| 7.2.1.1 | requirement documents | applicable | compliant |  | EX-TS-001 section 3 |  |
| 7.2.1.2 | requirement documents | applicable | compliant |  | EX-TS-001 section 3 |  |
| 7.2.1.3 | requirement documents | applicable | compliant |  | EX-TS-001 section 3 |  |
| 7.2.2.1 | design documents | applicable | compliant |  | EX-SDP-001 section 4.2 |  |
| 7.2.2.2 | design documents | applicable | compliant |  | EX-SDP-001 section 4.2 |  |
| 7.2.2.3 | design documents | applicable | compliant |  | EX-SDP-001 section 4.2 |  |
| 7.2.3.1 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.2.3.2 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.2.3.3 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.2.3.4 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.2.3.5 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.2.3.6 | test and validation documents | applicable | partially-compliant | activity falls after PDR; planned in EX-SVALP-001 5, evidence expected at CDR | EX-SVALP-001 section 5 |  |
| 7.3.1 | what the customer asks for | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.2 | own documentation set | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.3 | standalone information | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.4 | reuse requirements | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.5 | configuration of reusable items | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.6 | multi-platform testing | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.3.7 | conformance certificate | applicable | not-applicable | the software is not developed for reuse by others | EX-SPAP-001 section 12 | na-conflicts-with-tailoring |
| 7.4.1 | buying ground hardware | applicable | not-compliant | no evidence mapped; open until assessed |  | no-evidence |
| 7.4.2 | buying services | applicable | not-compliant | no evidence mapped; open until assessed |  | no-evidence |
| 7.4.3 | limits | applicable | not-compliant | no evidence mapped; open until assessed |  | no-evidence |
| 7.4.4 | choice | applicable | not-compliant | no evidence mapped; open until assessed |  | no-evidence |
| 7.4.5 | upkeep | applicable | not-compliant | no evidence mapped; open until assessed |  | no-evidence |
| 7.5.1 | programming devices | applicable | not-applicable | no programmable devices in the delivery | EX-SPAP-001 section 13 | na-conflicts-with-tailoring |
| 7.5.2 | device marking | applicable | not-applicable | no programmable devices in the delivery | EX-SPAP-001 section 13 | na-conflicts-with-tailoring |
| 7.5.3 | device calibration | applicable | not-applicable | no programmable devices in the delivery | EX-SPAP-001 section 13 | na-conflicts-with-tailoring |

## 4. Gaps

Each gap names the bound skill that resolves it.

| # | Clause | Gap | Status | Next skill |
|---|---|---|---|---|
| 1 | 5.2.4 | no-evidence-reference | partially-compliant | q80-software-product-assurance-plan |
| 2 | 5.2.4 | partially-compliant | partially-compliant | q80-software-product-assurance-plan |
| 3 | 5.4.1.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 4 | 5.4.1.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 5 | 5.4.2.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 6 | 5.4.2.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 7 | 5.4.3.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 8 | 5.4.3.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 9 | 5.4.3.3 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 10 | 5.4.3.4 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 11 | 5.4.4 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 12 | 5.4.5 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 13 | 5.5.4 | partially-compliant | partially-compliant | q80-software-product-assurance-plan |
| 14 | 5.5.5 | partially-compliant | partially-compliant | q80-software-product-assurance-plan |
| 15 | 5.5.6 | partially-compliant | partially-compliant | q80-software-product-assurance-plan |
| 16 | 6.1.3 | reference-without-section | compliant | q80-software-process-assurance |
| 17 | 6.2.2.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 18 | 6.2.2.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 19 | 6.2.2.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 20 | 6.2.2.8 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 21 | 6.2.2.9 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 22 | 6.2.2.10 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 23 | 6.2.3.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 24 | 6.2.3.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 25 | 6.2.3.8 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 26 | 6.2.4.2 | not-compliant | not-compliant | q80-software-process-assurance |
| 27 | 6.2.6.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 28 | 6.2.6.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 29 | 6.2.6.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 30 | 6.2.6.5 | document-not-found | partially-compliant | q80-software-process-assurance |
| 31 | 6.2.6.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 32 | 6.2.6.6 | document-not-found | partially-compliant | q80-software-process-assurance |
| 33 | 6.2.6.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 34 | 6.2.6.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 35 | 6.2.6.8 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 36 | 6.2.6.9 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 37 | 6.2.6.10 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 38 | 6.2.6.11 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 39 | 6.2.6.12 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 40 | 6.2.8.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 41 | 6.2.8.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 42 | 6.2.8.3 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 43 | 6.2.8.4 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 44 | 6.2.8.5 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 45 | 6.2.8.6 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 46 | 6.2.8.7 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 47 | 6.3.3.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 48 | 6.3.3.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 49 | 6.3.3.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 50 | 6.3.3.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 51 | 6.3.4.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 52 | 6.3.4.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 53 | 6.3.4.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 54 | 6.3.4.8 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 55 | 6.3.5.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 56 | 6.3.5.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 57 | 6.3.5.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 58 | 6.3.5.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 59 | 6.3.5.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 60 | 6.3.5.8 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 61 | 6.3.5.9 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 62 | 6.3.5.10 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 63 | 6.3.5.11 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 64 | 6.3.5.12 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 65 | 6.3.5.13 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 66 | 6.3.5.14 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 67 | 6.3.5.15 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 68 | 6.3.5.16 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 69 | 6.3.5.17 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 70 | 6.3.5.18 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 71 | 6.3.5.19 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 72 | 6.3.5.20 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 73 | 6.3.5.21 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 74 | 6.3.5.22 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 75 | 6.3.5.23 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 76 | 6.3.5.24 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 77 | 6.3.5.25 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 78 | 6.3.5.26 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 79 | 6.3.5.27 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 80 | 6.3.5.28 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 81 | 6.3.5.29 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 82 | 6.3.5.30 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 83 | 6.3.5.31 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 84 | 6.3.5.32 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 85 | 6.3.5.33 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 86 | 6.3.6.1 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 87 | 6.3.6.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 88 | 6.3.6.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 89 | 6.3.6.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 90 | 6.3.7.1 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 91 | 6.3.7.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 92 | 6.3.7.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 93 | 6.3.7.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 94 | 6.3.7.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 95 | 6.3.7.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 96 | 6.3.8.1 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 97 | 6.3.8.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 98 | 6.3.8.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 99 | 6.3.9.1 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 100 | 6.3.9.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 101 | 6.3.9.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 102 | 6.3.9.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 103 | 6.3.9.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 104 | 6.3.9.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 105 | 6.3.9.7 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 106 | 7.1.7 | partially-compliant | partially-compliant | q80-software-product-quality-metrics |
| 107 | 7.1.8 | partially-compliant | partially-compliant | q80-software-product-quality-metrics |
| 108 | 7.2.3.1 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 109 | 7.2.3.2 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 110 | 7.2.3.3 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 111 | 7.2.3.4 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 112 | 7.2.3.5 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 113 | 7.2.3.6 | partially-compliant | partially-compliant | q80-software-process-assurance |
| 114 | 7.3.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 115 | 7.3.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 116 | 7.3.3 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 117 | 7.3.4 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 118 | 7.3.5 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 119 | 7.3.6 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 120 | 7.3.7 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 121 | 7.4.1 | no-evidence | not-compliant | q80-software-product-assurance-plan |
| 122 | 7.4.2 | no-evidence | not-compliant | q80-software-product-assurance-plan |
| 123 | 7.4.3 | no-evidence | not-compliant | q80-software-product-assurance-plan |
| 124 | 7.4.4 | no-evidence | not-compliant | q80-software-product-assurance-plan |
| 125 | 7.4.5 | no-evidence | not-compliant | q80-software-product-assurance-plan |
| 126 | 7.5.1 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 127 | 7.5.2 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 128 | 7.5.3 | na-conflicts-with-tailoring | not-applicable | q80-software-criticality-tailoring |
| 129 | 6.3.7.4 | evidence-for-unlisted-clause | not in list | q80-compliance-matrix |

Evidence was given for clauses that are not in the clause list (a mistyped id, or an id from an older revision): 6.3.7.4.

## 5. Document trace

Folder example/docs/ holds 14 files; the evidence cites 15 documents, 14 of which resolve to a file.

| Cited document not found | Cited by clauses |
|---|---|
| EX-SVR-001 | 6.2.6.5, 6.2.6.6 |

| Cited document | File |
|---|---|
| EX-AUDIT-2026-01 | EX-AUDIT-2026-01.md |
| EX-CSTD-001 | EX-CSTD-001.md |
| EX-DSA-001 | EX-DSA-001.md |
| EX-DSTD-001 | EX-DSTD-001.md |
| EX-RB-001 | EX-RB-001.md |
| EX-SCMP-001 | EX-SCMP-001.md |
| EX-SDP-001 | EX-SDP-001.md |
| EX-SPAP-001 | EX-SPAP-001.md |
| EX-SPAR-2026-Q3 | EX-SPAR-2026-Q3.md |
| EX-SPR-LOG | EX-SPR-LOG.md |
| EX-SRF-001 | EX-SRF-001.md |
| EX-SVALP-001 | EX-SVALP-001.md |
| EX-SVERP-001 | EX-SVERP-001.md |
| EX-TS-001 | EX-TS-001.md |

## 6. Tailoring for category B

| Group | Topic | Applicable | Reduced | Not applicable |
|---|---|---|---|---|
| 5.1 | organisation | 12 | 0 | 0 |
| 5.2 | programme management | 18 | 0 | 0 |
| 5.3 | risks and critical items | 3 | 0 | 0 |
| 5.4 | suppliers | 10 | 0 | 0 |
| 5.5 | buying software | 6 | 0 | 0 |
| 5.6 | tools and environment | 6 | 0 | 0 |
| 5.7 | process capability | 8 | 0 | 0 |
| 6.1 | life cycle | 5 | 0 | 0 |
| 6.2 | cross-process obligations | 74 | 0 | 11 |
| 6.3 | per-process obligations | 76 | 0 | 0 |
| 7.1 | quality targets and measurement | 8 | 0 | 0 |
| 7.2 | product quality obligations | 12 | 0 | 0 |
| 7.3 | software built for reuse | 7 | 0 | 0 |
| 7.4 | ground hardware and services | 5 | 0 | 0 |
| 7.5 | programmable devices | 3 | 0 | 0 |

Total: 253 applicable, 0 reduced, 11 not applicable. The security clauses follow the security sensitivity (no), not the category.

## 7. Milestone evidence check

Review: preliminary design review (PDR). Software product assurance plan (SPAP) maturity owed: updated.

| Document owed | Driving clauses | Evidence state | Documents cited |
|---|---|---|---|
| coding standards and their tools | 6.3.4.1, 6.3.4.2, 6.3.4.4 | evidenced | EX-CSTD-001 |
| criticality classification of software products and components | 6.2.2.1, 6.2.2.3 | evidenced | EX-DSA-001 |
| software dependability and safety analysis report | 6.2.2.2, 6.2.2.7, 6.2.2.10 | partial | EX-DSA-001 |
| justification of design choices | 7.2.2.3 | evidenced | EX-SDP-001 |
| design and modelling standards | 6.2.8.4, 6.3.3.2 | partial | EX-SDP-001, EX-DSTD-001 |
| independent software verification and validation plan | 6.2.6.13, 6.3.5.28 | partial | EX-SVERP-001, EX-SVALP-001 |
| independent software verification and validation report | 6.2.6.13, 6.3.5.28 | partial | EX-SVERP-001, EX-SVALP-001 |
| software problem reports and their closure | 5.2.5.1, 5.2.5.2, 5.2.5.3, 6.2.6.4, 6.3.5.8 | partial | EX-SPR-LOG, EX-SVERP-001, EX-SVALP-001 |
| procedures and standards in force | 6.2.1.6, 6.2.1.7 | evidenced | EX-SDP-001 |
| software configuration management plan | 6.2.4.2, 6.2.4.5, 6.2.4.12, 7.3.5 | partial | EX-SCMP-001, EX-AUDIT-2026-01, EX-SPAP-001 |
| software development plan and project plans | 5.5.2, 5.6.2.1, 5.6.2.2, 6.3.4.5 | partial | EX-SDP-001 |
| software reuse file | 6.2.7.2, 6.2.7.3, 6.2.7.4, 6.2.7.5, 6.2.7.6, 6.2.7.7, 6.2.7.8, 6.2.7.11 | evidenced | EX-SRF-001 |
| software verification plan | 6.2.6.1 | evidenced | EX-SVERP-001 |
| software verification report | 7.1.7 | partial | EX-SVERP-001 |
| software product assurance milestone report (SPAMR) | 5.2.2.3, 5.6.1.2, 6.2.3.3, 6.2.6.12 | partial | EX-SPAR-2026-Q3, EX-SDP-001, EX-SPAP-001, EX-SVERP-001 |
| software product assurance plan (SPAP) | 5.2.1.1, 5.2.1.5, 5.2.6.2, 5.2.7.1, 5.2.7.2, 5.4.3.3, 5.4.3.4, 5.6.1.1, 6.1.1, 6.2.1.4, 6.2.2.10, 6.2.3.2, 6.2.3.4, 6.2.3.5, 6.2.4.8, 6.2.4.9, 6.2.4.11, 6.2.5.1, 6.2.5.2, 6.2.7.2, 6.2.7.3, 6.2.7.4, 6.2.7.5, 6.3.3.3, 6.3.3.5, 6.3.3.7, 6.3.4.3, 6.3.4.6, 6.3.5.1, 6.3.5.2, 7.1.3, 7.1.4, 7.1.5, 7.2.2.3, 7.5.1, 7.5.2 | partial | EX-SPAP-001, EX-SDP-001, EX-DSA-001, EX-SCMP-001, EX-SRF-001, EX-SVALP-001 |
| quality requirements in the technical specification | 6.3.2.4, 7.1.1, 7.1.2, 7.2.1.1, 7.2.1.3, 7.3.4 | partial | EX-TS-001, EX-SPAP-001 |
| test and validation plans, specifications and reports | 6.2.8.2, 6.2.8.7, 6.3.5.22, 6.3.5.23, 6.3.5.24, 6.3.5.25, 6.3.5.29 | partial | EX-SDP-001, EX-SVALP-001 |

Review pack against what is owed: 18 owed; missing: isvv-plan, isvv-report, software-verification-report; below issued maturity: software-verification-plan, spamr; submitted but not owed at this review: acceptance-documentation; pack complete: no.

## 8. Milestone report skeleton (SPAMR)

Software product assurance milestone report (SPAMR) for the preliminary design review (PDR), DRAFT - requires human review and sign-off.

| Section | Topic | Status | Draws on |
|---|---|---|---|
| 1 | purpose and scope of this milestone report | boilerplate | - |
| 2 | applicable and reference documents | boilerplate | - |
| 3 | terms and abbreviations | boilerplate | - |
| 4 | verification activities performed by product assurance | filled | EX-SVERP-001 |
| 5 | suitability of methods and tools | filled | EX-SDP-001 |
| 6 | adherence to design and coding standards | filled | EX-CSTD-001, EX-DSTD-001, EX-SDP-001, EX-SPAP-001 |
| 7 | product and process metrics against their targets | filled | EX-SPAP-001, EX-SPAR-2026-Q3, EX-SVERP-001, graded measurement set |
| 8 | testing and validation status and coverage | filled | EX-SVALP-001 |
| 9 | status of software problem reports and nonconformances | filled | EX-SPAP-001, EX-SPR-LOG |
| 10 | references to progress reports | filled | EX-SPAR-2026-Q3 |

Inputs still missing: none.

## 9. Product quality metrics

| Metric | Value | Threshold | Source | Direction | Status | Margin |
|---|---|---|---|---|---|---|
| coding_standard_violations | 3 | 0 | default | max | fail | -3 |
| comment_density | 0.27 | 0.2 | default | min | pass | 0.07 |
| cyclomatic_complexity | 12 | 10 | default | max | fail | -2 |
| decision_coverage | - | 1 | default | min | missing | - |
| function_size_loc | 55 | 80 | default | max | pass | 25 |
| nesting_depth | 3 | 4 | default | max | pass | 1 |
| open_major_nonconformances | 0 | 0 | default | max | pass | 0 |
| requirement_coverage | 1 | 1 | default | min | pass | 0 |
| requirement_test_coverage | 0.94 | 1 | default | min | fail | -0.06 |
| statement_coverage | - | 1 | default | min | missing | - |

Verdict: fail (failing: coding_standard_violations, cyclomatic_complexity, requirement_test_coverage; not measured: decision_coverage, statement_coverage). The standard fixes no threshold values: the defaults are illustrative and the values agreed in the contract and the plan replace them.

## 10. Limitations and boundaries

- This matrix is a DRAFT prepared by an agent. It is not an approval, not a certification and not a statement of compliance.
- Statuses are those the evidence index claims, combined to the weakest per clause and downgraded where a reference is missing. The role checks that each cited document exists; it does not judge what the document says.
- A not-applicable claim on a clause the tailoring keeps is a deviation and needs the customer's agreement.
- The standard is referenced, never reproduced: clause identifiers are facts, topic labels are our own wording.
- Worked example: the project, documents and evidence are invented to show the deliverable. Nothing here describes a real mission.

## 11. Human sign-off

Sign-off: none recorded.
The responsible human records the decision (see ROLE.md, Human sign-off). Approving over open gaps has to list them as accepted.

STOP: human sign-off required before submission.
