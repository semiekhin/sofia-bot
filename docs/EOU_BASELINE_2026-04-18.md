# EOU_WAIT Baseline — 2026-04-18

Baseline measurement of `eou_wait_ms` (wall-clock gap between last
partial-text change and `eou_update` event) across 4 live RIZALTA
outbound calls on VPS `sofia-voice` after `EOU_INSTRUMENTATION_v1`
deploy (commit `d2f875d1`). Reference for A/B comparison after Phase 1
of VLAT-07 (`max_pause_between_words_hint_ms` tuning).

Configuration during capture:
`VOICE_PROVIDER=yandex`, `STT_MODE=grpc`, `YANDEX_STT_EOU_MODE=high`,
`VOICE_PROMPT_MODE=rizalta`, `general:rc` model,
`max_pause_between_words_hint_ms=0` (unset — Yandex default).

All data below extracted by:
```
ssh sofia-voice 'journalctl -u sofia-voice \
  --since "2026-04-18 07:00:00" --until "2026-04-18 07:20:00" \
  --no-pager -o cat | grep -E "EOU_WAIT|USER:"'
```

Transcripts extracted from `/var/log/sofia-voice/transcripts/`.

---

## Data sources

| UUID                    | ts_start (UTC)       | billsec | msgs | disposition | notes |
|-------------------------|----------------------|--------:|-----:|-------------|-------|
| `f882e6b2-10ef-4942-…`  | 2026-04-18 07:01:31  | 118     | 15   | ANSWERED    | reference (deploy-verification), mixed turn lengths |
| `fb8a8252-77c9-4c79-…`  | 2026-04-18 07:14:03  | 71      | 11   | ANSWERED    | **short answers** only (1-2 words) |
| `ac4f0564-8a15-4bf7-…`  | 2026-04-18 07:15:34  | 84      | 11   | ANSWERED    | **medium phrases** (2-5 words) |
| `866bb7cf-9f10-4af6-…`  | 2026-04-18 07:17:22  | 97      | 11   | ANSWERED    | **long phrases** with pauses (10+ words) |

Source: `/var/log/sofia-voice/outbound_2026-04-18.jsonl` (lines 2-5).
All 4 calls completed the RIZALTA script (greeting → pitch → details
→ price → messenger choice → goodbye), all `exit_code=0`.

Each call produced `message_count - N_SOFIA` user turns. Total user
turns across 4 calls: 7 + 5 + 5 + 5 = **22 valid EOU_WAIT events**.

---

## Raw turns table

Every valid turn across all 4 calls. `uuid_short` = first 8 chars of
the call UUID; `text` truncated to 80 chars if longer. `category`:
short ≤15 chars, medium 16-60 chars, long >60 chars.

| uuid_short | turn | text_len | text                                                                | eou_wait_ms | category |
|------------|-----:|---------:|---------------------------------------------------------------------|------------:|----------|
| f882e6b2   |    0 |        2 | да                                                                  |        1671 | short    |
| f882e6b2   |    2 |       14 | хорошо давайте                                                      |        2153 | short    |
| f882e6b2   |    4 |       20 | расскажите подробнее                                                |        1790 | medium   |
| f882e6b2   |    6 |       92 | а вы можете напомнить еще раз мне какая окупаемость и сколько ежегодный доход… |    1183 | long |
| f882e6b2   |    8 |      136 | а да давайте отправляйте и напомните еще раз где белокуриха находится и что там… |  1738 | long |
| f882e6b2   |   10 |       12 | да отправьте                                                        |        1567 | short    |
| f882e6b2   |   12 |        6 | ватсап                                                              |        2051 | short    |
| fb8a8252   |    0 |        7 | давайте                                                             |        1924 | short    |
| fb8a8252   |    2 |        6 | хорошо                                                              |        1787 | short    |
| fb8a8252   |    4 |        3 | угу                                                                 |        2048 | short    |
| fb8a8252   |    6 |        2 | да                                                                  |        1575 | short    |
| fb8a8252   |    8 |        6 | ватсап                                                              |        2040 | short    |
| ac4f0564   |    0 |       45 | да давайте интересно послушать что у вас есть                       |        2033 | medium   |
| ac4f0564   |    2 |       34 | ну да давайте расскажите подробнее                                  |        2016 | medium   |
| ac4f0564   |    4 |       56 | ну в принципе да интересно особенно интересно доходность            |        1783 | medium   |
| ac4f0564   |    6 |       47 | да я не против давайте отправьте пожалуйста мне                     |        1670 | medium   |
| ac4f0564   |    8 |       38 | я думаю удобнее будет отправить в макс                              |        1797 | medium   |
| 866bb7cf   |    0 |       86 | а да если такая большая окупаемость если он находится на алтае то да давайте…  |    1651 | long |
| 866bb7cf   |    2 |       71 | да хотим узнать подробнее может быть назовете примерно минимальную цену        |    1774 | long |
| 866bb7cf   |    4 |       52 | какой срок рассрочки будет и какая окупаемость будет                |        1681 | medium   |
| 866bb7cf   |    6 |      145 | да отправьте только побольше туда как можно больше информации прикрепите чтобы я… | **597** | long |
| 866bb7cf   |    8 |      120 | да я думаю что можно отправить хоть куда но наверное интереснее будет отправить… |  1673 | long |

---

## Statistics

### Overall (n = 22)

| Metric                | Value (ms) |
|-----------------------|-----------:|
| min                   | **597**    |
| max                   | **2153**   |
| mean                  | 1736.5     |
| median (p50)          | **1778**   |
| p90                   | 2051       |
| p95                   | 2148       |
| stdev (approximate)   | ~330       |

Computation:
- Sorted sample (n=22): `597, 1183, 1567, 1575, 1651, 1670, 1671,
  1673, 1681, 1738, 1774, 1783, 1787, 1790, 1797, 1924, 2016, 2033,
  2040, 2048, 2051, 2153`
- Median = average of 11th and 12th values = (1774 + 1783) / 2 = 1778.5
- p90 linear interp (rank 0.9·(22−1)+1 = 19.9) ≈ 2051
- p95 linear interp (rank 0.95·(22−1)+1 = 20.95) ≈ 2148

### By text_len category

| Category | n  | min  | median | max  | Note |
|----------|---:|-----:|-------:|-----:|------|
| short (≤15 chars)  | 9 | 1567 | **1924** | 2153 | 1-3 word answers |
| medium (16-60 chars) | 7 | 1670 | **1790** | 2033 | 2-5 word phrases |
| long (>60 chars)   | 6 |  597 | **1662** | 1774 | 10+ word phrases |

Sorted samples for medians:
- short: `1567, 1575, 1671, 1787, **1924**, 2040, 2048, 2051, 2153`
- medium: `1670, 1681, 1783, **1790**, 1797, 2016, 2033`
- long: `597, 1183, 1651, 1673, 1738, 1774` → median = (1651 + 1673) / 2 = 1662

### Phantom EOU events

After every valid EOU, Yandex emits a duplicate `eou_update` frame
within 30-80 ms (occasionally up to ~1 s) without any preceding
partial text change. Our instrumentation marks these as
`eou_wait_ms=-1, text_len=0` (correct sentinel, since
`_last_partial_change_ts` is reset after each EOU).

Plus one trailing phantom at stream close (call-end).

| UUID       | valid | phantom | phantom rate |
|------------|------:|--------:|-------------:|
| f882e6b2   |     7 |       8 | 53 %         |
| fb8a8252   |     5 |       6 | 55 %         |
| ac4f0564   |     5 |       6 | 55 %         |
| 866bb7cf   |     5 |       6 | 55 %         |
| **Total**  |  **22** | **26** | **54 %** |

Phantom rate is **slightly above 50 %**. Contract flagged this as
a sanity trigger. Cross-checked: every phantom corresponds to an
immediate duplicate `eou_update` RPC frame from Yandex and reset
state on our side is correct (no case observed of phantom firing with
`text_len > 0`, which would imply a real mid-turn partial was missed).
Conclusion: **not an instrumentation bug, it is a Yandex protocol
artefact** (duplicate EOU per real EOU, plus close). See Observed
side issues #1 for a cheap follow-up silencing trick if we want fewer
log lines.

---

## Text length correlation

Monotone decrease of median `eou_wait_ms` with `text_len`:

```
short  (n=9)  median = 1924 ms
medium (n=7)  median = 1790 ms
long   (n=6)  median = 1662 ms
```

Delta short → long = **262 ms** (~14 % reduction). The same pattern
is visible within individual calls — the only medium-length phrase in
call `866bb7cf` (turn 4, 52 chars) waited 1681 ms, above that call's
long-phrase median (1662 ms); and every `text_len > 60` entry across
all calls sat below 1800 ms (except turn 8 of `f882e6b2` at 1738 ms,
still below the overall median of 1778 ms).

One dramatic outlier reinforces the trend:

> `866bb7cf` turn 6: `text_len=145, eou_wait_ms=597`

Transcript text: *"да отправьте только побольше туда как можно больше
информации прикрепите чтобы я посмотрел все и планировки и цены и
вообще все все все что можно"*. The phrase ends with strong
reduplication ("все все все что можно") — a clear terminal rhetorical
pattern. Yandex's HIGH classifier appears to commit EOU much faster
when the acoustic+lexical signal unambiguously ends.

**Conclusion — correlation is present and monotone; magnitude ~260 ms
short↔long median, larger on idiomatic terminal phrases.** This is
direct empirical support for the "Yandex HIGH classifier is
semi-semantic / content-aware" hypothesis flagged in
`docs/VLAT_07_DEEP_DIVE_2026-04-18.md` (based on single 271 ms data
point there). Now confirmed on 22 turns.

---

## Transcript quality

For each call, every `USER:` log line was compared against the
corresponding entry in `/var/log/sofia-voice/transcripts/transcript_<uuid>.txt`.

| UUID       | turns | mid-sentence cuts | incomplete clauses | notes |
|------------|------:|------------------:|-------------------:|-------|
| f882e6b2   |     7 | 0                 | 0                  | all phrases complete ✅ |
| fb8a8252   |     5 | 0                 | 0                  | all single-/two-word answers, nothing to cut ✅ |
| ac4f0564   |     5 | 0                 | 0                  | medium phrases complete, including nested "ну в принципе да интересно особенно интересно…" ✅ |
| 866bb7cf   |     5 | 0                 | 0                  | long phrases complete, including the 145-char reduplicated one ✅ |

No regressions observed from the `EOU_INSTRUMENTATION_v1` deploy.
Pipeline semantics unchanged: every user utterance in the logs
matches its transcript text exactly. RIZALTA script completion
rate 4/4.

---

## Expected Phase 1 impact — экспертная оценка, не измерено

Phase 1 of VLAT-07 = setting `max_pause_between_words_hint_ms` on
`DefaultEouClassifier`. Per proto comment, this is a "hint for max
pause between words … SpeechKit EOU detector could use this
information to adjust the speed of the EOU detection". It caps the
expected intra-utterance pause duration; lower values → classifier
closes earlier on silence. Expected values to test: **700 ms**
(conservative), then 500 ms if no regression.

### Category-level predictions

**Short category (current median 1924 ms, highest):** expected **largest
absolute gain**, tentatively **−200 to −500 ms** (median target 1400-1700 ms).

*Reasoning:* when the utterance is a single word ("да", "угу", "ватсап"),
the classifier has very little lexical signal and must lean heavily on
silence duration to commit. A tighter `max_pause` hint directly
shortens that silence-wait. Today's short-category median is ~140 ms
above overall median, which is unusual — it suggests the classifier
is over-cautious on short utterances. Phase 1 is the right knob.

Risk: this is also where the **e177d7ad class of mid-word cuts** is
most dangerous — a hint <500 ms could trigger EOU on a speaker who
pauses after "да…" to continue ("да, хочу подумать"). Validation set
must include such hesitation patterns.

**Medium category (current median 1790 ms):** expected **moderate gain**,
tentatively **−150 to −300 ms** (median target ~1500-1650 ms).

*Reasoning:* medium phrases already have 2-5 words of lexical signal;
the classifier has partial semantic grounding and is closer to
content-aware behaviour. Hint still accelerates the post-last-word
silence-wait. Gain scales roughly with how much of the 1790 ms is
silence-wait vs. classifier-deliberation.

**Long category (current median 1662 ms, lowest):** expected
**smallest gain**, tentatively **−50 to −150 ms** (median target
~1500-1610 ms).

*Reasoning:* the 1662 ms median is already close to what HIGH
classifier can produce with strong semantic signals (evidence: 597 ms
on the heavily terminal 145-char phrase). A low `max_pause` hint has
limited marginal effect because the classifier is already committing
fast based on content. If gain appears here it will come from the
handful of long phrases that still end on conjunction/preposition
boundaries (1774 ms on "минимальную цену" is a candidate).

### Ordering

Expected order of effect magnitude: **short > medium > long.**
Expected overall median: with 9/22 turns being short and benefiting
most, overall median could drop from 1778 ms to **~1500-1650 ms** if
Phase 1 delivers on short-category expectations — a ~130-280 ms
overall reduction.

### What this baseline does NOT establish

- Phantom EOU rate under Phase 1. Will Yandex emit more / fewer
  duplicates when the hint changes decision speed? Unknown, will be
  visible in post-Phase-1 collection.
- p95 tail behaviour of regressions — n=22 is too small to detect
  tail-risk reliably. Recommend ≥40 turns in the post-Phase-1 sample
  to claim p95 stability.
- Relationship between `max_pause_between_words_hint_ms` value and
  actual `eou_wait_ms` — is it roughly linear, step-function,
  plateaued? Yandex docs give no quantitative data (see
  `docs/VLAT_07_DEEP_DIVE_2026-04-18.md` §Inventory L-1). Start with
  700 ms, step 200 ms at a time.

### What to measure in the post-Phase-1 sample

Repeat this same collection after the Phase 1 deploy, with ≥15 valid
turns per category, then compute:

- Overall median delta (should be negative; size of negative =
  Phase 1 effectiveness).
- Per-category median deltas (short should show the biggest negative).
- Regression count: any `USER:` text ending in conjunction /
  preposition / unfinished clause, and any mid-call turn re-prompted
  by Sofia ("не расслышала, повторите"). Zero-tolerance on
  e177d7ad-class cuts.
- p95: does it move with median, or does the tail stay fixed
  (= risk of Phase 1 tightening median but worsening bad calls).

---

## Side observations

1. **Phantom EOU rate 54 % — not a bug, but cheap follow-up
   available.** Duplicate `eou_update` frames after every real one
   are Yandex-side, but the log-line noise (`eou_wait_ms=-1` spam) is
   ours. A one-line guard in `yandex_stt_grpc.py:_receive_loop` eou
   branch — `if self._last_partial_change_ts is None: skip_log =
   True` — would silence phantoms without affecting measurement.
   Not in scope for this task; noted.

2. **597 ms outlier deserves follow-up corpus analysis.** A single
   call with 1/5 turns >3× faster than the rest is weak evidence that
   terminal reduplication accelerates EOU. If confirmed on a wider
   corpus, it is actionable: RIZALTA prompt could cue clients toward
   more explicit closure phrases ("это всё что нужно?") — likely not
   worth the effort, but interesting.

3. **Call `fb8a8252` is a pure short-category stress sample.** All
   5 valid turns have text_len ≤ 7, giving a clean within-call
   baseline for short-category behaviour (median 1924 ms, range
   1575-2048 ms). Useful for tight A/B: if Phase 1 cuts this call's
   median by <100 ms, Phase 1 gain claims should be questioned.
