# MPC-based Adaptive Hello Interval Control for OLSR

## What this project is

A research paper. We keep the **standard OLSR core completely unchanged**
(MPR selection, TC messages, routing table computation — all RFC 3626 / stock
ns-3). The single intervention point is the **HELLO interval**, which becomes
dynamic under Model Predictive Control instead of fixed at 2s.

This "single intervention point" constraint is load-bearing. If you find
yourself modifying MPR selection or TC message format, stop and ask — that
breaks the ablation study and makes the results unattributable.

## The control inputs

**LinkScore** = a·s_RSSI + b·s_slope + c·s_MACretry   (a+b+c = 1, all inputs in [0,1])

**NodeScore** = built from queue occupancy and remaining battery (not started yet)

Weights a, b, c are **fitted from data**, never hand-tuned. That is the main
methodological contribution versus prior work (OLSR+, FBCR), which derive
link quality formulas analytically and never validate them against measured
ground truth.

## Non-negotiable methodology rules

1. **Features from the past, labels from the future.**
   Features come from window `[t-Δ, t]`. The PDR label comes from window
   `[t, t+τ]`. Never the same window — MAC retry rate and PDR are nearly the
   same quantity, so contemporaneous fitting is tautological and produces a
   fake R² above 0.9.

2. **Per-link fitting, never path-level.**
   End-to-end PDR is confounded by hop count and the objective is
   piecewise-constant in (a,b,c) because of the argmax over paths. Path-level
   comparison is a *validation* experiment, not a fitting method.

3. **No binarization of the label.**
   Each unicast frame is a Bernoulli trial. Feed per-frame success/failure to
   logistic regression. Do not threshold links into "good/bad" at PDR ≥ 0.95 —
   that discards the gradient information and hits a ceiling effect.

4. **Separate seed batches.**
   Calibration (percentile thresholds) / Training (weight fitting) /
   Evaluation must use disjoint seed sets. Split train/test **by seed**, never
   by row — rows from one run are correlated.

5. **Fixed rate, never adaptive.**
   `ConstantRateWifiManager` only. Rate adaptation compensates for degrading
   links and erases the signal we are measuring.

6. **Fading must be on.**
   Without `NakagamiPropagationLossModel`, RSSI is a deterministic function of
   distance and LinkScore degenerates into a distance estimator.

7. **The dataset must be probed, not merely observed.**
   Application traffic only crosses links OLSR routed over, so retry and the
   PDR label are censored to on-path links — while RSSI, riding on broadcast
   HELLO/TC, is not. The censoring is therefore asymmetric and invisible in a
   quick sanity check. Every node must unicast a probe frame to every node it
   has recently heard. Send it with `NetDevice::Send` at layer 2, never over
   UDP: an IP-routed probe can be forwarded via a different next hop (breaking
   attribution) or dropped for want of a route (restoring the censoring). The
   probe belongs to instrumentation only and never to the deployed controller.

8. **Never fit at saturation.**
   MAC retry has two causes, bad channel and collision. At saturation it is
   almost entirely collision, so the fitted `c` measures congestion and will
   not transfer. Choose the operating load empirically: sweep offered load and
   pick where `corr(retry_rate, rssi_mean)` is most strongly negative. It is
   near zero both when under-loaded (no retries anywhere) and when saturated
   (retries everywhere regardless of RSSI).

## Phases

- **Phase 0** — ns-3 built, `link-probe.cc` runs, instrumentation verified on 2 nodes
- **Phase 1** — frozen simulation config (one file, loaded by every script)
- **Phase 2** — instrumentation for 30-node scenario: per-link RSSI / slope / retry / future PDR
- **Phase 3** — percentile calibration (p20/p80) → `normalization_config.json`
- **Phase 4** — training dataset, 20–30 disjoint seeds
- **Phase 5** — logistic fit → (a,b,c) + VIF check + bootstrap CI + validation scatter
- **Phase 6** — package `LinkScore()` as a standalone module with unit tests
- **Phase 7** — path-level validation (top-1 match rate + regret vs empirically best path)
- Then repeat 1–6 for NodeScore, then build the MPC controller

Currently at: **Phase 0** (ns-3 not yet built — no cmake).
`scratch/link-dataset.cc` (Phase 2) is written but has never been compiled.

## Acceptance gate — check before spending seeds

Every dataset run prints these. A run that fails the gate is not a weak run,
it is an unusable one, and 25 seeds of it are 25 unusable seeds.

- **`rows w/ retry>0` below ~10%** — retry has no variance, so it cannot carry
  a coefficient. Raise offered load or path loss exponent.
- **`rows w/ fails>0` at zero** — the label is constant; the logistic fit has
  nothing to separate. Push more links into the waterfall region.
- **`rows w/o retry_rate` large** — these have a label but no retry feature
  (the route only just moved onto the link). The GLM drops them *silently*, so
  the effective training set is smaller than the row count suggests.
- **`median trials` very low** — each row's PDR is then estimated from a
  handful of Bernoulli trials and is mostly noise.

## Environment

- ns-3.45, pinned, **plus one local patch** — see below. Do not track master.

### The local ns-3 patch (must be declared in the paper)

`src/wifi/model/phy-entity.cc`, the `WifiPhyState::IDLE` branch of
`StartReceivePreamble`. Upstream asserts `!m_currentEvent` there. It can be
non-null: `ResetReceive` clears it but is scheduled at the event's *end* time,
while the state can reach IDLE earlier when a reception fails. A PPDU arriving
in that window aborts the run — about 1 run in 10 at 120 s, 1 in 4 at 300 s, in
dense ad-hoc scenarios. Others have hit the same assert in aerial ad-hoc work:
[ns-3-users thread](https://groups.google.com/g/ns-3-users/c/Mr8zHHqEUko)

The patch drops the incoming preamble instead of asserting, which is exactly
what the `CCA_BUSY` branch above already does for the identical condition.
Verified benign: a run that does not hit the race is byte-identical to the
unpatched build (degree 5.30 / 14425 rows / 57.4% loss / 72.1% pinned, both
before and after). After patching, 10 seeds x 300 s all exit cleanly.

### Everything else

Simulation setup lives in `sim-config/*.conf`, not in the .cc files.
Precedence is built-in default < config file < command-line flag.

- Build: `./ns3 configure --enable-examples && ./ns3 build`
- Run: `./ns3 run "link-dataset-fanet -- --seed=1"`
- Build tree is `~/ns3` inside WSL, edited from `d:\intern\ns3\ns-3-dev`.
  Sync with `cp` before building; they are two copies, not one.
- Experimental scenarios live in `scratch/`. Only promote to `contrib/` once
  LinkScore is frozen.
- Trace callback signatures are version-specific. Verify against
  `src/wifi/model/` before assuming a signature is correct.

## Known traps

- `HelloInterval` is an ns-3 Attribute, but `m_helloInterval` is only read when
  `HelloTimerExpire()` reschedules. Changing it mid-run takes effect at the
  next expiry, not immediately. Cancelling and rescheduling the timer has been
  reported to perturb throughput even when the value is unchanged — write a
  regression test that sets the interval to its current value and asserts
  results are identical.
- `OLSR_NEIGHB_HOLD_TIME` is a compile-time macro in
  `olsr-routing-protocol.cc`, not derived from `m_helloInterval`. If the hello
  interval changes and hold time does not follow, links expire incorrectly.
  Must be fixed before any MPC results are meaningful.
- ns-3's OLSR has **no MAC layer feedback** (unlike the NS-2 version). The
  retry metric must be hooked manually via `WifiRemoteStationManager` traces.
- Check RSSI vs RSSI-slope collinearity (VIF) before trusting fitted weights.
  A node approaching has both high RSSI and positive slope.
