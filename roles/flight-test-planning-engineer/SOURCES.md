# SOURCES.md - Flight Test Planning Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR-25) | transport category airworthiness context for the certification flight test (flight instruments, airplane performance, noise interface) | false |
| EASA CS-25 (CS-25) | EASA mirror of the transport category certification context | false |
| FAR 36 (14 CFR Part 36) | noise certification measurement procedure - named and summarized at reference level by the noise-certification-test leaf (flyover 6500 m, sideline 450 m lateral, approach 1200 m at 120 m on a 3 degree glide slope; EPNL 10 dB down integration, 10 s normalization; per-point and cumulative margin acceptance). Table values are NOT reproduced; applicable limits remain program inputs. | false |
| ICAO Annex 16 Volume I | international mirror of the noise certification measurement procedure (named at reference level by the noise-certification-test leaf, summary only) | false |

No proprietary standard text is reproduced. The planning content of the
deliverable is common-knowledge flight test, measurement and telemetry
methodology as summarized by the bound AeroSkills leaves (all under
flight-test-operations/planning), each acquired and verified in the
AeroSkills tree at the pinned `skills_release` band:

| Bound leaf | Rule it contributes (summary) |
|---|---|
| flight-test-instrumentation | Nyquist criterion (fs >= 2*fmax), required sample rate fs = margin * 2 * fmax with default margin 2.5, sensor range verdict (|value| <= range), ADC quantization step R/2^N, calibration currency verdict |
| flight-test-planning | build-up ordering by ascending risk with prerequisite flagging, instrumentation completeness check, test matrix coverage check, go/no-go gate (weather/aircraft/instrumentation/safety review all pass) |
| noise-certification-test | FAR 36 reference geometry constants (6500/450/1200 m, 120 m, 3 degrees), EPNL = 10*log10((1/T0)*sum(10^(PNLT/10))*dt) over the 10 dB down interval with T0 = 10 s, margin to limit = limit - EPNL, cumulative rule: sum of three margins >= 10 EPNdB and no negative individual margin (typical chapter 4 / stage 4 check at reference level) |
| pcm-telemetry-decommutation | frame period in words = 1 + data words + idle words; fixed channel one value per locked frame, supercommutated one value per slot per frame, subcommutated keyed by subframe id (per-subframe value lists) |
| position-error-calibration | compressible calibrated airspeed relations (a0 = 340.294 m/s, p0 = 101325 Pa, q_c and V_cas inverse pair), tower fly-by reduction (dp_s = rho*g0*dh via the altimeter scale, V_cas = V_isa(qc(V_ias) + dp_s)), GPS ground speed doublet (V_tas = (V1g+V2g)/2, V_cas = V_tas*sqrt(rho/rho0)), PEC curve/table, data quality verdict (coverage >= 0.95, residual RMS <= 1.0 m/s) |
| telemetry-data-acquisition | PCM frame size = words * bits, bit rate = frame_rate * frame size, supercommutation ratio (channel rate / frame rate, integer > 1), subcommutation ratio (frame rate / channel rate, integer > 1), IRIG-B seconds of year = (day-1)*86400 + seconds of day, conditioning span vs ADC range, latency = acquisition + processing + link, link margin = received power - sensitivity, quality verdict (BER and dropout limits) |
| test-point-matrix-design | grid = cartesian product of altitude/speed/weight sweeps across configurations (altitude-major), repeat every N-th point (interval >= 2), efficiency sequence (configuration blocks, altitude then speed), steady state check (|observed - planned| <= tolerance per condition) |

The plan template in `templates/` is an original structure informed by
public-domain guidance and paraphrase-level process knowledge; the
worked values in its method validation cards are the bound leaves'
documented reference worked examples (e.g. fly-by reduction
+0.88 m/s at 500 m / 490 m / 288.15 K, EPNL 93.0103 EPNdB for the
constant 90 dB run, cumulative margins [3, 4, 4] summing to 11.0 EPNdB),
recomputed by the role core pre-flight to validate the reduction chain.
Applicable noise limits shown in the example are program inputs, not
derived regulation table values.
