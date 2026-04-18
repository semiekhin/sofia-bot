# VLAT-07 Deep-Dive — Yandex SpeechKit v3 EOU Levers (18.04.2026)

Read-only research on mechanisms inside Yandex SpeechKit v3 gRPC that
influence EOU wait latency (median 1802 ms in our fleet, dominant
contributor to the 2641 ms user-perceived pause measured in
`docs/VOICE_LATENCY_AUDIT_2026-04-18.md`).

No code changes. No deployment. No test calls initiated.

Source material:

- `/opt/sofia-voice/yandex_stt_grpc.py` md5 `eae3873b49c34e618388a82f6cb73260`
- `/opt/sofia-voice/yandex_proto/yandex/cloud/ai/stt/v3/stt.proto`
- Corresponding Python bindings `stt_pb2.py` on VPS (confirmed via
  `grep max_pause_between_words_hint_ms` on serialised descriptor —
  field byte-encoded at offset `0x1f` in `DefaultEouClassifier`)
- Yandex official docs (URLs in Evidence per finding)
- Journal logs `journalctl -u sofia-voice --since "2026-04-15"` —
  30+ turn sample with `🗣️ STT (grpc):` lines
- Network RTT: `ping stt.api.cloud.yandex.net` from VPS =
  **7.25 ms avg** (5/5 packets, mdev 0.22 ms; floor is tiny)

---

## Inventory — рычаги, влияющие на EOU wait

| # | Рычаг | Источник | Status | Ожидаемый gain | Complexity |
|---|-------|----------|--------|----------------|------------|
| L-1 | `DefaultEouClassifier.max_pause_between_words_hint_ms` (int64) | `stt.proto:41-54`; Python descriptor byte `0x1f`; [docs/speechkit/stt/eou](https://yandex.cloud/en/docs/speechkit/stt/eou) | **Documented (vague)** — "hint for max pause between words … could use this information to adjust the speed of EOU detection". **No documented default, no documented scale.** We currently leave at 0 (unset) → Yandex uses internal default. | **Unknown but ≥0.** Expert estimate −100 to −400 ms based on the premise that lowering a "max pause" cap forces EOU to commit sooner after the last word. Ceiling bounded by the word-to-EOU lag actually observed on filler-ending utterances (271 ms on "а давайте угу"). Not measured. | **Trivial** — one int64 field in `_request_iterator()` at `yandex_stt_grpc.py:120-125`. 1-2 LOC. |
| L-2 | `EouSensitivity = HIGH` | `stt.proto:43-47`; already set via `YANDEX_STT_EOU_MODE=high` in `/opt/sofia-voice/.env` | **Documented, active** — "high-sensitive and fast EOU detector, which may produce more false positives". Docs confirm HIGH is the fastest of two discrete values (`DEFAULT`, `HIGH`). | **Already realised**. Not a new lever. Phase 2D commit `9114d825` switched DEFAULT → HIGH and reduced EOU wait by ~620 ms per commit message. | N/A (deployed) |
| L-3 | `ExternalEouClassifier` — client-driven EOU via `StreamingRequest.eou` (field 4) | `stt.proto:55-67, 282-296`; `_request_iterator()` would need an extra control-path to push `Eou{}` messages into `_audio_queue` | **Documented, un-tested in our code** — empty message; user sends `Eou{}` control frame; Yandex emits `eou_update` with `eou_time_ms == received_data_ms` (i.e. immediate). Public research found **zero production examples** — no real-world code or forum post demonstrates the flow end-to-end. | **−500 to −1100 ms** *if* we can fire `Eou{}` within ~200-500 ms of true end-of-speech via Silero VAD. Bounded below by Silero's own silence-window (see e177d7ad lesson: 300 ms cut valid phrases mid-word). | **Moderate** — need Silero "tail of utterance" detector with sustained-silence window, separate from the barge-in detector; plumbing to push control frames into the audio_queue; fallback logic if Silero mis-fires. Full test battery required (e177d7ad regression is the exact failure mode). |
| L-4 | `SilenceChunk{duration_ms}` — `StreamingRequest` field 3 | `stt.proto:263-266, 282-296` | **Documented, poorly documented** — described as "data chunk with silence" in proto; Yandex API reference does not tie it to EOU acceleration. Explore-agent research also finds zero examples and concludes it is a bandwidth optimisation, not a latency lever. | **≈0** for EOU. Possibly negligible bandwidth save. | N/A (not a latency lever) |
| L-5 | Model selection: `general` vs `general:rc` vs `general:deprecated` | `stt.proto:208-209` lists the values; [release notes](https://github.com/yandex-cloud/docs/blob/master/en/speechkit/release-notes-stt.md) describe behaviour changes but **do not publish per-model EOU latency differences** | **Documented existence, not documented for latency** | **Unknown**. Not measurable without an A/B. Switching models is also a WER decision, not just latency. | Low to make the code change (1 LOC), high to judge the outcome (need accuracy regression tests on Russian voice corpus) |
| L-6 | Our own wall-clock between partial-text-stable and EOU callback | `yandex_stt_grpc.py:140-165` `_receive_loop()`, dispatching to `_on_grpc_eou` in `voice_asterisk.py:791-817` | **Internal code** — receive loop is a simple `async for response in stream` iterating server events. No asyncio.sleep, no queue latency. Measured wall-clock jitter EOU→callback ~1-5 ms. | **≈0**. Not a viable lever. | N/A |
| L-7 | `audio_processing_type = REAL_TIME` vs `FULL_DATA` | `stt.proto:229-236` | **Documented** — `REAL_TIME` sends partials and finals "as soon as possible"; `FULL_DATA` processes after all data received. `REAL_TIME` already selected. `FULL_DATA` would be catastrophic for streaming. | **Negative if changed** | N/A (locked to REAL_TIME) |

Summary: only **two** levers on the table that genuinely affect EOU
wait in a way we haven't already pulled — **L-1** (simple, ~trivial,
unknown gain) and **L-3** (moderate effort, potentially large gain,
high risk). All other candidates are either already active, documented
as non-latency, or explicitly ruled out.

---

## Phases breakdown

The original audit lumped these into one 32 h / high-risk item
("VLAT-07"). The proto inventory shows a natural 3-phase split where
Phase 1 is an order of magnitude cheaper than Phase 2, and Phase 3 is
an order of magnitude riskier than Phase 2. This is a meaningful
re-framing — the audit's 32 h estimate was correct for Phase 2+3, but
Phase 1 was not previously identified as a standalone option.

---

### Phase VLAT-07-P1 — Set `max_pause_between_words_hint_ms`

**Scope:** Add a single field to
`DefaultEouClassifier(type=HIGH, max_pause_between_words_hint_ms=N)` at
`yandex_stt_grpc.py:120-125`. Start at a conservative value (e.g.
700 ms) and measure on live calls; optionally tighten to 500 ms if no
phrase-cutting regressions appear.

**Gain_ms:** **−100 to −400 ms median EOU wait.** Range explanation:
- Lower bound (100 ms): Yandex's "hint" is advisory; the HIGH-sensitivity
  classifier may already use heuristics that approximate what a 700 ms
  hint expresses, so the delta is small.
- Upper bound (400 ms): if the current Yandex internal default is
  ~1200 ms (speculative; undocumented), dropping to 500 ms could shave
  up to 400 ms before false-positive risk kicks in.
- **Expert estimate, not measured.** No open-source production
  examples found that quantify the parameter's effect (see
  `yandex.cloud/en/docs/speechkit/stt/eou` — Yandex docs describe it
  qualitatively as "set up how fast the voice assistant should respond
  to the end of speech" without numbers).

**Effort_hours:** ~4-6 h. Components:
- 0.5 h — code change (1 line in `_request_iterator`)
- 0.5 h — import and sync `yandex_stt_grpc.py` into DEV git (see
  Prerequisites)
- 1 h — instrumentation: log the per-turn EOU_wait (wall ts from last
  stable partial to `eou_update` receipt) so we can A/B cleanly
- 2 h — 3-5 live RIZALTA test calls at hint=700 ms, compare EOU wait
  to baseline
- 1 h — follow-up test at hint=500 ms if 700 shows no regression
- 1 h — rollback readiness, BACKLOG + SESSION_LOG updates

**Risk:** **low-medium.** The field is a hint, worst-case behaviour
on bad tuning = occasional mid-sentence EOU trigger (exactly the
e177d7ad bug class but much weaker, because the classifier is also
using its own learned features and does not blindly cut at the hint
value). Mitigation: start with 700 ms (above our proven-safe
`VAD_SILENCE_THRESHOLD=500 ms` sibling), measure regression on 5-10
calls before tightening. Revert is a one-line `git revert`.

**Rollback:** remove the added field in `_request_iterator()` →
Yandex falls back to its undocumented default. Deployable via:

```
ssh sofia-voice "cd /opt/sofia-voice && git checkout yandex_stt_grpc.py && systemctl restart sofia-voice"
```

*(requires VPS to actually be a git checkout — currently it is
file-deployed via `scp`; see Prerequisites.)*

**Verification approach:**
1. Before switching, capture baseline EOU_wait distribution on 5
   calls at current settings (log `last_partial_wall → eou_wall` per
   turn).
2. After switch, run 5 calls at `hint=700 ms`. Compare medians.
3. Check for phrase-cutting regressions (the e177d7ad class) — look
   for turns where `final text` is a recognisable incomplete
   fragment ("цена и", "хочу узнать", trailing conjunctions without
   object). If ≥1 such regression in 5 calls — abort tightening.
4. Only if 5 calls at 700 ms show no regression AND measurable −Nms
   gain — try 500 ms on another 5 calls.

**Precondition:**
- **P0** — `yandex_stt_grpc.py` is VPS-only, not in DEV git (see
  "Обнаруженные побочные проблемы" in the 18.04 audit, item 1). Must
  sync before this Phase so that Phase 1 is a normal DEV→PROD deploy,
  not another scp. **This is a blocker for any VLAT-07 phase.**
- Baseline instrumentation capturing EOU_wait per turn as a machine-
  readable field in logs (one-liner `f"EOU_WAIT_MS={...}"` at
  `voice_asterisk.py:791-817` `_on_grpc_eou`, using
  `self._last_grpc_partial_ts` tracked alongside
  `_stt_stream_turn_t0`). Without this, A/B is hand-greppy.

---

### Phase VLAT-07-P2 — ExternalEouClassifier driven by Silero silence-tail

**Scope:**
1. Switch `EouClassifierOptions` from `default_classifier` to
   `external_classifier` in `yandex_stt_grpc.py:120-125`.
2. Add a new Silero-driven "utterance-tail" detector in
   `voice_asterisk.py` — distinct from the existing barge-in detector.
   After a confirmed speech segment during `_is_responding=False`,
   track sustained silence; when silence exceeds threshold
   (e.g. 500 ms), enqueue an `Eou{}` message into the stream's audio
   queue.
3. Add a new method `YandexSTTStream.send_eou()` in
   `yandex_stt_grpc.py` that pushes `StreamingRequest(eou=Eou())` into
   `_audio_queue` (or a control queue merged with it).

**Gain_ms:** **−500 to −1100 ms median EOU wait** *if* Silero fires
within 500 ms of true end-of-speech. Upper bound assumes the measured
1802 ms Yandex median floors at ~1800 ms server-side; Silero-driven
EOU can bring that to ~500-700 ms client-side silence detection + 7 ms
network RTT + server processing ~(unknown, not documented). So
Yandex-server-side wait becomes effectively zero (confirmed by proto
comment: `eou_time_ms == received_data_ms` at the moment the
external `Eou{}` arrives).

**Effort_hours:** ~20-28 h. Components:
- 2 h — sync `yandex_stt_grpc.py` into DEV git, refresh proto
  inspection for the `eou` oneof field wiring
- 4 h — implement `send_eou()`, merge control events with audio
  queue, end-to-end smoke test
- 6 h — Silero utterance-tail detector: parameter choice, sustained-
  silence window, interaction with existing `_silence_start`/
  `_is_speaking` state machine (currently REST-path-only, would need
  to live alongside gRPC-path)
- 6 h — live-call validation (at least 2 sessions of 5-10 calls each,
  reviewing every transcript for e177d7ad-class mid-sentence
  truncation)
- 4 h — regression tuning if phrase-cutting re-emerges
- 2 h — documentation (CLAUDE.md lesson, BACKLOG, SESSION_LOG)

**Risk:** **high.** Direct replay territory for e177d7ad:
VAD-driven endpointing at the wrong moment kills
"Скажите … минимальную цену … и срок". Difference from historical
fix: we now have HIGH sensitivity as a fallback (if we keep
DefaultEouClassifier as backup, never activate External), and Silero
v4 is more accurate than the old energy-VAD that originally caused
e177d7ad. But the failure mode is identical and Sergey explicitly
flagged it in the contract context.

**Rollback:** env flag `YANDEX_STT_EOU_MODE=high` should continue to
use `DefaultEouClassifier(HIGH)` path — only add a *new* mode value
`external` which routes through the new code. Reverting is
`YANDEX_STT_EOU_MODE=high` + `systemctl restart sofia-voice`.
Single-env-var switch. L1 rollback fidelity via the same pattern as
`VOICE_VAD_PROVIDER=energy` for Silero (rollback-fidelity rule from
user_sergey memory).

**Verification approach:**
1. Shadow mode for ≥20 live RIZALTA calls: fire `Eou{}` from Silero
   tail but **also** keep DefaultEouClassifier active; log both
   decisions; compare timings and any content differences. Requires
   Yandex to accept both classifiers simultaneously (to be confirmed
   — the `oneof Classifier` in proto implies "one or the other",
   making true shadow mode infeasible without two parallel streams).
2. If true shadow impossible, A/B on alternating calls (odd call =
   default, even = external), with monitoring of `USER:` transcript
   text completeness — look for any phrase ending on conjunction/
   preposition/open clause structure.
3. Cut-over only after 20+ calls with zero mid-sentence cuts and
   measurable −500 ms+ gain.

**Precondition:**
- VLAT-07-P1 done first (ensures `yandex_stt_grpc.py` in DEV git and
  per-turn EOU_wait instrumentation exists).
- ≥20 live RIZALTA calls baseline distribution is available for the
  comparison; at current ~1-2 calls/day this is a ~2-week calendar
  constraint, not an engineering constraint.

---

### Phase VLAT-07-P3 — Semantic turn detector (LiveKit-style) on partials

**Scope:** Add an on-VPS CPU-runnable transformer model
(`livekit/turn-detector` SmolLMv2 135M, or equivalent Russian fine-
tune) that consumes each `gRPC partial` text and predicts "is the
utterance semantically complete?". On positive prediction, fire
`Eou{}` via the Phase 2 pipeline.

**Gain_ms:** **−200 to −500 ms over Phase 2** on turns where silence
alone is ambiguous (client says "да, хочу" with a hanging tone).
Expert estimate; LiveKit documents median p50 improvements of ~100-
300 ms over VAD-only in their own English/Spanish stack.
**Unmeasured on Russian**, and specifically unmeasured on 8 kHz
telephony audio with WER elevated by the channel.

**Effort_hours:** ~40-48 h. Components:
- 8 h — model choice, download, benchmark Russian performance on
  existing transcript corpus (file `/var/log/sofia-voice/transcripts/`,
  currently 2 files — need corpus growth first)
- 12 h — integrate as a partial-text consumer in
  `yandex_stt_grpc.py:135-165` `_receive_loop`
- 8 h — confidence threshold tuning, interaction with Silero
  silence-tail
- 8 h — shadow-mode validation (≥30 calls) before cut-over
- 4 h — fine-tune on our Russian RIZALTA dialogues if base model
  insufficient (only if transcript corpus has ≥500 turns, currently
  has ~20)
- 4 h — rollback plumbing + docs

**Risk:** **high-very-high.** Two kinds of risk stacking:
(a) the e177d7ad phrase-cut risk (same as Phase 2), (b) the
model-quality risk (zero evidence the chosen model is accurate on
Russian phone-quality audio transcripts). Yandex's own EOU classifier
is trained on Russian speech — our external one almost certainly
will not be.

**Rollback:** env flag `YANDEX_STT_EOU_MODE=external` (Phase 2) vs
`=external_semantic` (Phase 3). Roll back via env + restart.

**Verification approach:** same as Phase 2 but with an additional
quality dimension (response coherence) to be judged by a human
reviewer over the shadow-mode call set.

**Precondition:** Phase 2 complete, in production for ≥2 weeks,
with measured baseline showing Phase 2 alone insufficient to hit
target (median ≤1500 ms).

---

## Decision matrix

**Hard recommendation:**

| Phase | Recommendation | Rationale |
|-------|----------------|-----------|
| **P1 (max_pause hint)** | **Do now, in an upcoming sprint.** | Effort ~5 h, reversible in one commit, new finding that was not in the original VLAT-07 framing. Gain unknown but unlikely to be zero; worst plausible case ≈ 0 ms with no regression; best plausible case ≈ −400 ms with minor tuning. Expected value of doing it outweighs expected cost by an order of magnitude. |
| **P2 (ExternalEouClassifier + Silero tail)** | **Do not schedule as a standalone sprint yet. Re-evaluate after 20-30 live RIZALTA calls with P1 active.** | P1 may close enough of the gap to make P2 unnecessary. P2 resurfaces the exact e177d7ad risk; ~24 h of work includes a mandatory 20-call shadow validation that only pays off if P1's ceiling is insufficient. Sequencing P1 → measure → decide P2 is 100% cheaper than doing both back-to-back. |
| **P3 (semantic turn detector)** | **Do not do in foreseeable future. Close as P3 backlog item.** | Two independent risks (phrase-cut + model-quality). Russian fine-tune requires a dialogue corpus we don't yet have (≥500 turns; we're at ~20). LiveKit's gain is English/Spanish; Russian not demonstrated. If P1+P2 together hit median 1500 ms, P3 has no justification. If they don't, the next sensible lever is shadow-switching STT models (`general:rc` → `general`) before investing in a bespoke semantic model. |

**What the pilot series should measure (to unblock decision on P2):**
1. P1 gain: compare EOU_wait median **before/after** over ≥10 calls
   at each `max_pause_between_words_hint_ms` setting (baseline →
   700 → 500).
2. Phrase-completeness regression rate: count user-turn transcripts
   with trailing conjunction / incomplete clause. Baseline is ~0 %
   today (5/7 measured turns on 17-18.04 were complete; 2 were
   single-word answers where completeness is trivial).
3. User-perceived pause full distribution (not just median): the
   upper tail matters as much as p50 for UX.

**If after 20-30 calls the P1 median lands at:**

- **<1600 ms → P2 and P3 are both unnecessary.** Close VLAT-07
  completely. Move to instrumentation / TTS cache / sentence
  streaming (ranked higher in 18.04 audit).
- **1600-1800 ms → P2 is worth ~24 h for another 200-400 ms; P3
  skippable.** Do P2 next sprint, keeping risk mitigations.
- **>1800 ms (P1 no effect) → P2 is the only remaining lever.** Do
  P2 next sprint with extra shadow-validation time (say 32 h total).

---

## Prerequisites

Before any phase is implementable:

1. **[P0 blocker] Sync `yandex_stt_grpc.py` into DEV git.**
   Current state: file exists only at `/opt/sofia-voice/yandex_stt_grpc.py`
   (md5 `eae3873b49c34e618388a82f6cb73260`). No local copy at
   `/opt/sofia-gpt-dev/yandex_stt_grpc.py` (verified by `ls` and
   `find`). Commit `e13aa3fa` titled "feat(voice): Yandex STT v3
   gRPC streaming (Phase 2B+2C)" references it but never added it.
   This is the same drift pattern that caused the 49659ffb Observer
   incident. Block any code change to this file on `git add` +
   commit first.

2. **[P0 blocker] Per-turn EOU_wait instrumentation.**
   Today we log `stream duration`, `partial count`, `final count` in
   `voice_asterisk.py:807-811`. We do **not** log the wall-clock
   interval between last-stable-partial and EOU event. Without this
   we cannot A/B cleanly. Minimal change: track
   `self._last_grpc_partial_ts = time.monotonic()` inside
   `_on_grpc_partial` and compute `eou_wait_ms` at the start of
   `_on_grpc_eou`. Log as a machine-readable field
   `| eou_wait_ms=NNNN` on the existing `🗣️ STT (grpc):` line. ~30
   LOC incl. tests. This is a **dependency of P1**, not a separate
   task.

3. **[P1 pre-work] Baseline dataset of ≥5 live calls at current
   settings** (HIGH + `max_pause_between_words_hint_ms=0`), with the
   new instrumentation active. Required to have a "before" number
   to compare against. At current RIZALTA cadence (~1-2 calls/day),
   1-week calendar lead time.

4. **[P2 only] Verify Yandex accepts shadow / A/B pattern.** The
   `oneof Classifier` in `stt.proto:68-74` syntactically forbids
   having both default and external active on a single stream. True
   shadow requires two parallel streams (doubles Yandex API cost per
   call and roughly doubles network work). Alternating calls
   (odd=default, even=external) is cheaper and probably sufficient
   but is a weaker experimental design.

5. **[Sanity] DEV→PROD deploy plumbing** for `yandex_stt_grpc.py` once
   added to DEV git. CLAUDE.md describes the deploy pattern
   (scp + systemctl restart sofia-voice); should work unchanged once
   the file is in git.

6. **[Nice-to-have] Fresh proto.** Our on-VPS proto version matches
   what the Python bindings expose, and includes
   `max_pause_between_words_hint_ms` and `ExternalEouClassifier`.
   These are present in current upstream too (verified via the
   Yandex docs URL). No immediate upgrade required, but a scheduled
   re-sync every 6-12 months is healthy hygiene.

---

## Open questions

What could not be answered from this read-only research and needs
either a live experiment or a deeper Yandex-side escalation:

1. **What is Yandex's internal default for
   `max_pause_between_words_hint_ms` when unset?** Critical for
   predicting P1 gain. Not documented. Yandex support ticket could
   clarify; alternatively it can be inferred by measuring at two
   explicit settings (e.g. 700 and 1500) and observing the shape.

2. **Is there a latency difference between
   `EouSensitivity=HIGH + max_pause=500` and
   `EouSensitivity=DEFAULT + max_pause=500`?** If DEFAULT+low-pause
   achieves the same effect with lower false-positive rate, that's a
   better tuning than HIGH+low-pause. Not deducible from proto; needs
   A/B.

3. **Does `general:rc` have different EOU latency behaviour than
   `general`?** Release notes do not mention EOU latency. Could be
   tested in a ~5-call A/B.

4. **Is true shadow mode (both classifiers on one stream)
   accepted by the server?** `oneof Classifier` in proto suggests no,
   but Yandex could accept extra fields silently and ignore them —
   small probing experiment would verify.

5. **When firing `Eou{}` via ExternalEouClassifier, what is the
   actual server-side processing delay before `eou_update` arrives
   back?** Proto comment implies near-zero
   (`eou_time_ms == received_data_ms`), but wall-clock server-trip
   time is undocumented. Direct measurement needed in P2.

6. **Does Yandex's HIGH classifier already use semantic cues?** The
   271 ms EOU wait on "а давайте угу" vs 1662 ms on "да хотим" (same
   call, same session, both short) strongly suggests content-aware
   behaviour — Yandex may already recognise terminal fillers like
   "угу". If true, Phase 3 (semantic) is **redundant** with Yandex's
   own work. Would be useful to confirm via systematic testing on
   different utterance terminals.

7. **Does REAL_TIME vs FULL_DATA matter for the EOU detection
   algorithm quality?** Docs say REAL_TIME "sends partials and finals
   as soon as possible". Unclear if the EOU classifier itself is
   compromised for speed in REAL_TIME mode. FULL_DATA is not usable
   for streaming (by definition) so this is an information question
   only.

---

## Evidence summary

All claims above are anchored in one of:

- Proto field with file:line at
  `/opt/sofia-voice/yandex_proto/yandex/cloud/ai/stt/v3/stt.proto`
- Python binding (verified present via grep of serialised descriptor)
- Yandex official doc (URL given inline per claim)
- Journal log extract from VPS (`journalctl -u sofia-voice --since 2026-04-15`)
- Research-agent exploration of third-party and open-source code
  (returned zero production examples of `ExternalEouClassifier` use)
- Baseline measurements from `docs/VOICE_LATENCY_AUDIT_2026-04-18.md`

Expert estimates are explicitly flagged (e.g. "−100 to −400 ms",
"not measured"). Nothing in the gain column is a number Yandex
commits to; they are a-priori estimates bounded by physics
(network RTT 7 ms) and by the single measured data point
(271 ms minimum observed EOU wait in our fleet).

---

## Расхождения с аудитом 18.04

1. **Audit estimate of VLAT-07 was 32 h / high risk / −750 ms gain
   conflated all three phases.** Phase 1 alone is 5 h / low-medium
   risk / −100-400 ms; it was not identified as a separate option.
   Decision matrix now recommends starting with Phase 1 only.

2. **Audit implied the only EOU lever was ExternalEouClassifier.**
   This missed `max_pause_between_words_hint_ms`, which is in our
   proto and Python bindings today, unused. Small miss in evidence
   coverage during the audit's Yandex proto inspection.

3. **Audit rightly flagged the e177d7ad risk for semantic EOU.**
   This finding still stands, but it applies most strongly to Phase 2
   and Phase 3, less to Phase 1 (which uses Yandex's own learned
   classifier with a hint, not a hard cap).
