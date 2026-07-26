# MPC-based Adaptive Hello Interval Control for OLSR in FANETs

## What this project is

A research paper. The **standard OLSR core stays completely unchanged** — MPR
selection, TC messages, routing table computation, all RFC 3626 / stock ns-3.
The single intervention point is the **HELLO interval**, which becomes dynamic
under Model Predictive Control instead of fixed at 2 s.

This "single intervention point" constraint is load-bearing. If you find
yourself modifying MPR selection or TC message format, stop and ask — that
breaks the ablation study and makes results unattributable.

**Domain: FANET, 3D, Gauss-Markov mobility.** Not ground MANET. The reason is
quantitative: at 2 m/s a node moves 4 m in a 2 s window, changing RSSI by
~0.34 dB — below the noise floor of the slope estimator. At 30 m/s it moves
60 m for ~4.4 dB. RSSI slope, and therefore the whole predictive premise, only
carries information at FANET speeds.

## Control input

    LinkScore = a·s_RSSI + b·s_slope + c·s_MACretry

Weights are **fitted from data**, never hand-tuned. That is the main
methodological contribution versus prior work (EE-Hello, OLSR+, FBCR,
OLSR-LCN), which derive link-quality formulas analytically and never validate
them against measured ground truth.

**NodeScore (queue + battery) is descoped to future work.** Queue has clean
ground truth but battery barely varies over a 300 s run — radio energy is a
rounding error against UAV propulsion energy — so β_battery would be
meaningless. One metric proven properly beats two half-proven.

## Repo documents

- `PLAN.md` — the 11-phase research plan. Read the section for the current
  phase. **This file is the authority on phases; do not duplicate the phase
  list here.**
- `WORKFLOW.md` — folder layout, provenance rules, report template. Read
  section 3 before writing any runner, section 6 before writing a report.
- `STATUS.md` — where the project currently stands. **Read first, update at
  the end of every phase.** Current phase lives there, not here.

---

## Non-negotiable methodology rules

### 1. Features from the past, labels from the future
Features from window `[t−Δ, t)`. PDR label from `[t, t+τ)`. Never the same
window — MAC retry and PDR are nearly the same physical quantity, so
contemporaneous fitting is tautological and produces a fake R² above 0.9.
Enforce structurally: emit a row only at simulation time `t+τ`, when the label
window has closed. Then it cannot be violated even deliberately.

### 2. Per-link fitting, never path-level
End-to-end PDR is confounded by hop count, and the objective is
piecewise-constant in (a,b,c) because of the argmax over paths. Path-level
comparison is a *validation* experiment (P6), not a fitting method.

### 3. Binomial GLM, not per-frame logistic, and no binarization
Each aggregation window has `trials_future` attempts and a success ratio. That
is a binomial observation. Fitting it as such is mathematically identical to
per-frame logistic regression with zero information loss, and far cheaper.

    successes = round(pdr_future * trials_future)
    failures  = trials_future - successes
    sm.GLM(np.c_[successes, failures], X, family=Binomial())

Do **not** threshold links into good/bad at some PDR τ. That discards the
difference between 0.72 and 0.94 and invents a hyperparameter to defend.

**The trial is one MAC attempt, not one frame.** Fixed in P0, measured:

    trials_future = number of data PPDUs on air        (MonitorSnifferTx)
    fails_future  = number of MacTxDataFailed events   (MAC trace)
    pdr_future    = 1 - fails_future / trials_future

Both counters at the MAC layer, never from `Send()` calls. Two consequences,
both wanted: a retransmission is a new trial, and a frame dropped in the queue
is no trial at all — queue occupancy is a property of the *node*, not of the
link, so it must not enter a link label.

Do **not** use post-ARQ delivery (`1 - final_fails/first_attempts`). With 7
retries the miss probability is (1-p)⁷, so that label reads exactly 1.000 while
the true per-attempt quality has already fallen to 0.556 — it manufactures the
"`pdr_future` piled at 1.0" ceiling this file warns about. Measured in P0 at
17 dBm: per-attempt 0.556 at 400 m against post-ARQ 1.000. It is also not
robustly countable — `first_attempts = attempts - retries` goes *negative* in
the dead region, because per-frame accounting needs each MPDU tracked from
first attempt to resolution and cannot be recovered from cumulative counters.

Per-attempt delivery is also **the quantity ETX measures** (ETX = 1/(d_f·d_r)
over one-attempt probabilities), which makes the comparison against ETX in the
paper natural rather than forced.

**Limitation to declare: attempts within one frame are not independent.** Seven
retries happen within milliseconds under near-identical channel conditions, so
`n = trials_future` overstates the information content and the binomial GLM
reports optimistic standard errors. At the boundary E[attempts] ≈ 1/p ≈ 2, so
the SE is understated by roughly √2. Not fatal, but it is one more reason the
cluster-robust SE of rule 6 is mandatory, not optional.

### 4. Do not constrain a+b+c=1 during the fit
In a logistic model the magnitude of β sets the slope of the sigmoid; the data
determines it. Forcing the sum constrains the slope and the intercept cannot
compensate. **Fit free with an intercept, report β with standard errors,
normalise only at the final export step.** Since LinkScore only ranks edges,
dividing by Σβ is a monotone transform and ordering is preserved.

A negative β is a **finding**, not a bug. Do not clip to zero.

### 5. Fit on raw features; clip only at deployment

| Used in | Features |
|---|---|
| Fitting (P5) | **Raw or z-scored, NOT clipped** |
| Deployment (P8) | Normalised and clipped to [0,1] |

Clipping at p20 makes an RSSI of −95 dBm and −88 dBm both zero — it censors
the explanatory variable exactly in the boundary region that matters most, and
biases β toward zero. Fit both variants and compare test-set predictive
quality; if clipping costs materially, widen to p5/p95.

*If the run summary reports a high fraction of values pinned at a clip
boundary, this rule is why.*

### 6. Cluster-robust standard errors, clustered by seed
Rows within one run are heavily correlated — RSSI on the same link one second
apart is nearly identical. The independent unit is closer to *one encounter*
between two nodes than to *one row*.

    .fit(cov_type='cluster', cov_kwds={'groups': df['seed']})

Without this the GLM reports p-values around 1e-50, which is a visible tell
that clustering was ignored. Cluster-robust inference wants 30–50 clusters, so
prefer **more seeds over longer runs**: 40 seeds × 300 s beats 15 seeds × 800 s
at the same compute.

### 7. Physical validation: β_slope / β_RSSI ≈ τ
If slope really acts as a linear extrapolator,

    logit(p) = γ₀ + γ₁·RSSI(t+τ) = γ₀ + γ₁·RSSI(t) + (γ₁·τ)·slope
                                          └β_RSSI┘    └─β_slope─┘

so **β_slope / β_RSSI should come out ≈ τ**, in seconds — the units work out.
This is direct evidence that slope is doing predictive work rather than being
an incidentally correlated variable. **It only appears when fitting on raw
features** (rule 5); normalising each metric independently destroys the ratio.

### 8. Slope by OLS on raw samples — no EWMA pre-filter
EWMA does not bias the slope (a filtered linear ramp has the same gradient,
shifted). But by Gauss–Markov, OLS on raw data is already the best linear
unbiased estimator of the gradient — no preprocessing beats it. Worse, EWMA
induces correlation between adjacent points while OLS assumes independent
errors, so the **reported standard error is understated**. For a project whose
whole argument rests on the p-value of β_slope, that is disqualifying.

A ~20-sample ring buffer per neighbour is a few hundred bytes. EWMA is not
needed to save memory.

If EWMA is used for the RSSI *level*: choose a time constant, not α.
`α ≈ Δt / τ_desired`. Report "τ_eff = 1 s", not "α = 0.3" — the first has
physical meaning and survives a change in beacon rate.

### 9. Train and deploy must compute features identically
If the training dataset uses a windowed mean but the deployed node uses EWMA,
the feature distributions differ and weights fitted on one are applied to the
other. Train/deploy skew, silent and hard to detect. **Consistency beats
optimality** — fix the feature definitions once in P2 and reuse verbatim in P8.

### 10. Fixed rate, never adaptive
`ConstantRateWifiManager` only. Rate adaptation compensates for degrading
links and erases the signal being measured.

### 11. Fading on — but judge it by β_slope, not by σ
`NakagamiPropagationLossModel` must be enabled. **However**, the FANET
air-to-air channel is LoS-dominated: with m = 3–8 the RSSI standard deviation
is only ~1.6–2.7 dB, well below the 3–6 dB that would be normal on the ground.
That is correct, not broken.

In FANET the information beyond distance comes from **slope**, not from
fading. So the check that LinkScore is more than a disguised distance
estimator is **the t-statistic of β_slope**, not the σ of the fading. Do not
"fix" the channel by raising fading to hit a σ target.

### 12. The dataset must be probed, not merely observed
Application traffic only crosses links OLSR routed over, so retry and the PDR
label are censored to on-path links — while RSSI, riding on broadcast
HELLO/TC, is not. The censoring is therefore **asymmetric and invisible in a
quick sanity check**.

Every node must unicast a probe frame to every node it has recently heard.
Send it with `NetDevice::Send` **at layer 2, never over UDP**: an IP-routed
probe can be forwarded via a different next hop (breaking attribution) or
dropped for want of a route (restoring the censoring).

Give probe frames the **same size as data frames**. A 64 B probe has a very
different airtime and collision probability than a 512 B data frame; mixing
sizes in one retry denominator corrupts the feature.

**Set `WifiMacQueue::MaxDelay` ≈ 100 ms on the probe interface.** Pacing the
probe does *not* stop queue backlog — measured in P0, a 10 ms interval gives an
overall retry_rate of 0.9478 and a 50 ms interval gives 0.9475, because once the
link is dead the probes keep queueing whatever the rate, and the dead region
then dominates the metric. What bounds the backlog is packet lifetime: past
`MaxDelay` the packet is discarded instead of transmitted late, so attempts stop
shortly after the link dies rather than continuing for tens of seconds. And
because a queue-dropped packet is never an attempt, it leaves both the numerator
and the denominator of the label (rule 3) — the artifact disappears from the
data even while it still happens.

**Probe while the beacon is still heard, not while unicast still succeeds.**
The "recently heard" condition solves coverage, which is a different problem
from backlog, and it has a trap: cutting the probe off when unicast stops
working removes exactly the very-bad-link tail that anchors the bottom of the
sigmoid. Beacons are broadcast and need no ARQ, so they outlive unicast
delivery — key the probe off beacon reception and let `MaxDelay` handle the
backlog. Two mechanisms, two purposes.

The probe belongs to instrumentation only and never to the deployed
controller. Its overhead does not count against paper results because it does
not exist in the evaluation tier.

### 13. Never fit at saturation
MAC retry has two causes, bad channel and collision. At saturation it is
almost entirely collision, so the fitted `c` measures congestion and will not
transfer. Choose the operating load empirically: sweep offered load and pick
where `corr(retry_rate, rssi_mean)` is most strongly negative. It is near zero
both when under-loaded (no retries anywhere) and when saturated (retries
everywhere regardless of RSSI).

### 14. Fit on one scenario; test generalisation on others
Pooling scenarios yields compromise weights optimal for none, and hides
whether weights depend on conditions. Fit on the nominal scenario only. Then
(a) apply the frozen weights to other scenarios and measure the drop, and
(b) **refit separately per scenario and report weight drift**. Stable weights
across speeds are evidence the formula captures physics. Expect `c` to drift
with offered load — that is a Discussion point if anticipated, a hole if not.

### 15. Separate seed batches, disjoint, split by seed

| Artifact | From batch |
|---|---|
| `frozen/normalization.json` (p20/p80) | calibration, 5 seeds |
| `frozen/weights.json` (a,b,c) | training, 30–40 seeds |
| All reported numbers | evaluation, 5 seeds |

Split train/test **by seed**, never by row. Never compute percentiles on
pooled data before splitting — that is silent leakage.

**`data/eval/` is off-limits until P10.** Touching it earlier invalidates
every reported number. **`frozen/` is immutable once written** — if it must
change, create a `-v2` file and record why in the phase report.

---

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
- **`pdr_future` distribution piled at 1.0** — ceiling effect, nothing to
  learn. Reduce TxPower or enlarge the area. A link at PDR 0.30 is worth more
  than a link at 1.00; the boundary region is where the formula must
  discriminate.

**Never filter rows by label value.** Filter only by sample count
(`trials ≥ 5`). Keeping only high-PDR links is the surest way to fit a useless
model: within that subset RSSI barely correlates with PDR, so β_RSSI comes out
near zero — the opposite of the truth.

**If a gate fails, stop and report. Do not loosen the threshold to pass.**

---

## Threats to the thesis — know these before P5

**Geometric LET from GPS.** UAVs have GPS, and the position-based FANET
literature (FORP, POLSR, ML-OLSR, OLSR+, 3D-position OLSR) computes link
expiration time from position, velocity and heading. A reviewer will ask why
RSSI slope instead. **Include geometric LET as a competing model in the P5
comparison table** and answer with numbers.

The defence, in strength order: position gives geometry, RSSI gives the actual
channel (a link can die at 200 m from interference and work at 800 m in the
clear); GPS-denied operation is a real UAV threat model; geometric LET assumes
constant velocity, which Gauss-Markov violates by construction; sharing
position costs bandwidth in every HELLO. Note that OLSR+ uses RSSI *together
with* position — even the position-based camp treats RSSI as informative.

**β_slope not significant.** The entire predictive premise rests on it. If it
fails after widening Δ and raising node speed, that is a **result to report**,
and LinkScore becomes a 2-metric formula.

Both threats surface at P5 — after ~30 simulation runs and an afternoon of
Python, before any controller C++ is written. That is why the phase order is
what it is.

---

## Environment

ns-3.45, pinned, **plus one local patch** — see below. Do not track master.

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
before and after). After patching, 10 seeds × 300 s all exit cleanly.

### FANET simulation parameters

Live in `sim-config/*.conf`, not in the .cc files. Precedence: built-in
default < config file < command-line flag. Every parameter carries a one-line
justification with a source — this file becomes the paper's Simulation Setup
table. **A parameter left at default without checking is a parameter that will
bite you** (see the Nakagami note below).

| Parameter | Value | Why |
|---|---|---|
| Area | 2000×2000×500 m (alt 100–600) | ~6 neighbours at 30 nodes |
| Nodes | 30 | |
| Mobility | `GaussMarkovMobilityModel`, Alpha 0.85 | FANET de-facto standard |
| MeanVelocity | Uniform[15, 30] m/s | Mid-range of published FANET work |
| **MeanPitch** | **Uniform[−0.05, +0.05]** | The widely copied ns-3 template sets `Min=Max=0.05`, so every UAV climbs forever and pins to the ceiling. Bug. |
| NormalVelocity | Normal[0, var 2.0, bound 4.0] | Template sets var=0, i.e. no speed variation |
| Standard | 802.11a, 5.18 GHz, `ConstantRateWifiManager` 6 Mbps | |
| **TxPower** | **19 dBm** | Chosen to hit a **measured** degree, not from a link-budget formula. Gives d(PDR 0.5) = **625 m** and degree **6.14**, both measured in P1. |
| **`MinimumRssi`** | **−101 dBm** | `ThresholdPreambleDetectionModel` defaults to **−82 dBm**, a hard RSSI floor: a frame below it is never detected whatever its SNR, and it sits 7 dB above the noise-limited sensitivity. At −101 the binding constraint becomes `Threshold` (4 dB SNR → effective floor −90 dBm). **Declare in the paper.** It buys no extra range at fixed degree — see below. |
| **Mean degree** | **6.14** | **Measured** (P1, beacon ratio ≥ 0.5 over 5 s), isolated 0.6% of node-time. Cross-checked by a geometric count from recorded positions with no beacon involved: ~6.0. Do not compute this from a density formula — the box is 500 m tall against a 625 m range, so the 2D and 3D formulas differ by nearly 2× and the coverage sphere is clipped by the boundary. |
| **Altitude dynamics** | quasi-2D | Each node stays in a ~107 m altitude slice over a 300 s run (median z-span; **100%** of nodes cover under half the 500 m band). Vertical motion contributes a median of **0.7%** of the distance change that flips a link's state (3.2% before projecting onto the 3D separation). So: 3D **positions**, stratified between nodes, with dynamics driven by horizontal motion. Say it that way in the paper; do not write "3D mobility" and imply altitude varies. |
| Path loss exponent | 2.2 | Measurements put A2A near free-space |
| **Nakagami m₀/m₁/m₂** | **8 / 5 / 3** | LoS-dominated aloft. The ns-3 default of 1.5/0.75/0.75 is an urban ground channel — m<1 is *worse than Rayleigh*. |
| **Distance1 / Distance2** | **100 m / 300 m** | Defaults 80/200 m are a ground-scale threshold; with 500 m links every link falls in the far tier |
| Feature window Δ | 4 s | At 2 s the slope SNR is ≈1 and β_slope is unidentifiable |
| Label window τ | 4 s | |
| Sim time | 300 s, discard first 30 s | Gauss-Markov and neighbour tables need warmup |
| Seeds | 40+ preferred over longer runs | See rule 6 |

### Build and run

- Build: `./ns3 configure --enable-examples && ./ns3 build`
- Run: `./ns3 run "link-dataset-fanet -- --seed=1"`
- Build tree is `~/ns3` inside WSL, edited from `d:\intern\ns3\ns-3-dev`.
  Sync with `cp` before building; **they are two copies, not one.**
- Experimental scenarios live in `scratch/`. Promote to `contrib/` only once
  LinkScore is frozen.
- Trace callback signatures are version-specific. Verify against
  `src/wifi/model/` before assuming a signature is correct.
- Every run emits `run_manifest.json` with git SHA, git-dirty flag, config
  hash, binary hash, and binary-vs-source mtime. **Fail loudly if the binary
  is older than the newest source file** — a stale binary silently
  invalidated an entire campaign on the previous project.

---

## Known traps

- **`HelloInterval`** is an ns-3 Attribute, but `m_helloInterval` is only read
  when `HelloTimerExpire()` reschedules. Changing it mid-run takes effect at
  the next expiry, not immediately. Cancelling and rescheduling has been
  reported to perturb throughput even when the value is unchanged — write a
  regression test that sets the interval to its current value and asserts
  byte-identical results.
- **`OLSR_NEIGHB_HOLD_TIME`** is a compile-time macro in
  `olsr-routing-protocol.cc`, not derived from `m_helloInterval`. If the hello
  interval changes and hold time does not follow, links expire incorrectly.
  Must also set the `HTime` field in the HELLO so neighbours learn the new
  hold time. EE-Hello solves both; read its diff (do not build it — ns-3.27,
  waf, removed from ns-3 since 3.36).
- **No MAC layer feedback in ns-3's OLSR** (unlike the NS-2 version). Retry
  must be hooked manually via `WifiRemoteStationManager` traces.
- **RSSI vs slope collinearity.** A node approaching has both high RSSI and
  positive slope. Check VIF before trusting fitted weights; VIF > 5 needs
  handling.
- **`retry_rate` empty vs zero.** Zero means "500 frames, no failures"; empty
  means "no frames yet". Two different facts — keep them distinguishable, and
  count how many rows have a label but no retry feature (the GLM drops them
  silently).

  ## Repo documents

- `PLAN.md` — 11-phase research plan. Read the section for the current phase.
- `WORKFLOW.md` — folder layout, provenance rules, report template.
  Read section 3 before writing any runner, section 6 before writing a report.
- `STATUS.md` — where the project currently stands. Read this first,
  update it at the end of every phase.