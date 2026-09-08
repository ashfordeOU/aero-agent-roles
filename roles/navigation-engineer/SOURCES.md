# SOURCES.md - Navigation Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| DO-229 (WAAS MOPS) | integrity/availability context for GNSS RAIM/FDE; reference-only | true |
| DO-208 (TSO-C129 GPS MOPS) | integrity/availability context for GNSS positioning; reference-only | true |
| ICAO Annex 10 Vol I | integrity/availability context for GNSS integrity concepts; reference-only | true |
| Aero Agent Skills gnc-autonomy/navigation leaves (13) | the domain rules the core implements: frames/geodesy, inertial-navigation error growth, Kalman filter design, GNSS pseudorange positioning, RAIM/FDE, dilution of precision, carrier smoothing, Doppler velocity, RTK positioning, loosely- and tightly-coupled INS-GNSS integration, terrain-referenced navigation, bearing-only localization | false |

The navigation relations encoded in `core/navigation_engineer_core.py`
are standard engineering methodology as carried by the bound Aero
Agent Skills logic files: WGS84 geodetic/ECEF/NED frame transforms
(navigation-frames), INS coasting error-growth models from
accelerometer-bias and gyro-drift terms plus Schuler-period and
angle-random-walk relations (inertial-navigation), iterated
pseudorange least squares with dilution-of-precision geometry
(gnss-pseudorange-positioning, dilution-of-precision), a chi-square
RAIM/FDE fault-detection test with horizontal protection level
(gnss-raim-fde), Hatch-filter carrier smoothing and linearized
Doppler velocity least squares (gnss-carrier-smoothing,
gnss-doppler-velocity-positioning), double-difference RTK float
solve with integer ambiguity ratio test and fixed-baseline solve
(gnss-rtk-positioning), a psi-angle error-state Kalman predict/update
for INS-GNSS integration (kalman-filter-design,
ins-gnss-integrated-filter, tightly-coupled-ins-gnss), TERCOM
correlation-surface matching with a SITAN slope-linearized bias
filter (terrain-referenced-navigation), and Stansfield weighted
least-squares bearing-only localization with a geometry dilution
factor (bearing-only-localization). Reference-typical sensor, satellite-
geometry and terrain-profile values are documented assumptions in the
report, never vendor or classified data. No proprietary standard text
is reproduced; summaries and original structures only.
