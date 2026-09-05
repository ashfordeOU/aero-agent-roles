# SOURCES.md - State Estimation Engineer

Standards and references this role draws on. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.
No proprietary text is reproduced anywhere in this role.

| Source | Role use | Gated |
|---|---|---|
| SAE ARP4754A | development-assurance context for aircraft systems (reference-only; the estimator supports system functions whose assurance is managed at system level) | true |
| gnc-autonomy/estimation-filtering leaves (AeroSkills) | the role's equations are grounded in the leaf logic files: alpha-beta-filter (Benedict-Bordner beta = alpha^2/(2-alpha); Kalata gains from tracking index lambda = sigma_w*dt^2/sigma_v), rts-smoother (CV model F = [[1, dt],[0, 1]], discretized Q; forward Kalman recursion; backward smoothing gain G_k = P_filt F^T P_pred^-1; covariance-reduction verdict), extended-kalman-filter (central-difference Jacobians; EKF predict/update recursion; bearing/range measurement model), unscented-kalman-filter (scaled unscented transform; NEES = (x-p)^T P^-1 (x-p) with expected value n), particle-filter (bootstrap/SIR; ESS = (sum w)^2 / sum(w^2); resample when ESS < n/2), complementary-filter (Mahony-style explicit complementary filter on SO(3): cross-product innovation e = m x v, corrected rate omega_c = omega_m - b + k_p*e, bias step b <- b - k_i*e*dt, RK4 quaternion kinematics + renormalization; module gain defaults k_p = 2.0 1/s, k_i = 0.4 1/s^2; trailing-window innovation-norm tolerance 1e-3 rad), interacting-multiple-model-filter (two-mode CV/CA bank, Markov mode mixing, Bayesian mode-probability refresh) | false |
| Kalman, R. E., "A New Approach to Linear Filtering and Prediction Problems", ASME J. Basic Engineering 82 (1960) | the linear Kalman recursion the report is built on (public) | false |
| R. G. Brown & P. Y. C. Hwang, Introduction to Random Signals and Applied Kalman Filtering (Wiley) | discrete CV/CA modeling, Q discretization, steady-state behavior (public educational text) | false |
| Mahony, Hamel & Pflimlin, "Nonlinear Complementary Filters on the Special Orthogonal Group", IEEE Trans. Automatic Control 53(5), 2008 | explicit complementary filter / bias observability with two non-parallel reference vectors (public) | false |
| Kalata, P. R., "The Tracking Index: A Generalized Parameter for alpha-beta and alpha-beta-gamma Target Trackers", IEEE Trans. AES 20(2), 1984 | tracking-index gain selection (public) | false |

The complementary-filter gain defaults (k_p = 2.0 1/s, k_i = 0.4
1/s^2), the steady-state innovation tolerance (1e-3 rad), the
uncompensated-bias drift anchor |b|*t, the discrete sampling-lag bound
|omega|*dt, the SIR ESS threshold n/2, and the NEES expected-value n
criterion are documented module defaults and worked-example anchors of
the bound leaf SKILL.md files - reproduced as numbers, not as text.
Noise-model values in the report (q, r, bias vector, rates) are DESIGN
INPUTS that trace to the item's sensor datasheets; the report labels
them as inputs.

The report template in `templates/` is an original structure produced
by the role core for the reference item.
