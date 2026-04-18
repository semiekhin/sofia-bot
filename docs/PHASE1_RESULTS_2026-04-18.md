# Phase 1 Results — `max_pause_between_words_hint_ms=700` (18.04.2026)

A/B comparison of EOU_WAIT before/after Phase 1 deploy (`VLAT-07-P1`,
commit `393eb062`). Deploy timestamp ~07:33 UTC; test calls 07:34-07:40 UTC.

Configuration during post-deploy capture:
`VOICE_PROVIDER=yandex`, `STT_MODE=grpc`, `YANDEX_STT_EOU_MODE=high`,
`YANDEX_MAX_PAUSE_HINT_MS=700`, `general:rc`, `ru-RU WHITELIST`.
Banner confirmed at startup: `Pipeline: Yandex STT (GRPC, EOU=high,
hint=700ms) -> YANDEX TTS` (`journalctl` 07:33:17.875).

---

## Post-deploy calls

| UUID                      | ts_start (UTC)      | billsec | msgs | disposition | intent |
|---------------------------|---------------------|--------:|-----:|-------------|--------|
| `bae62e1d-5694-4154-…`    | 07:34:36            | 67      | 11   | ANSWERED    | **short-stress** — все ответы 1-словные (5 turns: "да", "да", "да", "да", "ватсап") |
| `b858cbe0-d7e0-40f4-…`    | 07:36:08            | 107     | 15   | ANSWERED    | **medium** — фразы 5-8 слов (7 turns) |
| `8fa66bb2-dd66-42c7-…`    | 07:38:06            | 111     | 19   | ANSWERED    | **long + mixed** — длинные фразы, один кейс с микропаузой |

Source: `/var/log/sofia-voice/outbound_2026-04-18.jsonl` (последние 3 записи).

Extraction:
```
ssh sofia-voice "journalctl -u sofia-voice \
  --since '2026-04-18 07:34:00' --until '2026-04-18 07:40:30' \
  --no-pager -o cat | grep -E 'EOU_WAIT|USER:|плохо слышно'"
```

Total **21 valid EOU_WAIT events** across 3 calls
(5 + 7 + 9), matching baseline sample size of 22.

---

## Raw turns table (post-deploy)

| uuid_short | turn | text_len | text                                                                     | eou_wait_ms | category |
|------------|-----:|---------:|--------------------------------------------------------------------------|------------:|----------|
| bae62e1d   |    0 |        2 | да                                                                       |        1010 | short    |
| bae62e1d   |    2 |        2 | да                                                                       |         904 | short    |
| bae62e1d   |    4 |        2 | да                                                                       |        1012 | short    |
| bae62e1d   |    6 |        2 | да                                                                       |        1036 | short    |
| bae62e1d   |    8 |        6 | ватсап                                                                   |         988 | short    |
| b858cbe0   |    0 |       39 | а да хотим рассказывайте если не сложно                                  |        1033 | medium   |
| b858cbe0   |    2 |       42 | да давайте мне интересно можете продолжать                               |        1446 | medium   |
| b858cbe0   |    4 |       47 | а можете рассказать подробнее что это за регион                          |        1145 | medium   |
| b858cbe0   |    6 |       44 | да давайте интересно послушать какие условия                             |        1167 | medium   |
| b858cbe0   |    8 |       31 | да скажите какая там доходность                                          |        1177 | medium   |
| b858cbe0   |   10 |       34 | да хотим отправлять если не сложно                                       |        1162 | medium   |
| b858cbe0   |   12 |       38 | ну ну давайте попробуем отправить макс                                   |        1028 | medium   |
| 8fa66bb2   |    0 |       65 | ой интересно ну да если прям как такая доходность как вы говорите        |        1675 | long     |
| 8fa66bb2   |    2 |       69 | от двух с половиной миллионов еще и семь лет но это интересно давайте    |        1015 | long     |
| 8fa66bb2   |    4 |       16 | да это интересно                                                         |        1153 | medium   |
| 8fa66bb2   |    6 |      103 | этот доход вы говорите он где то в договоре прописан да какой то гарантированный… |  1136 | long |
| 8fa66bb2   |    8 |       17 | здравствуйте а да                                                        |        1037 | medium   |
| 8fa66bb2   | **10** | **49** | **дать вот вот этот гарантированный доход он вообще** ⚠                  |    **1021** | medium ⚠ |
| 8fa66bb2   |   12 |       90 | это статистика может быть или вообще откуда взялись эти цифры то про гарантированный… | 869 | long |
| 8fa66bb2   |   14 |       52 | ну отправьте да давайте хорошо отправьте знаете куда                     |        1128 | medium   |
| 8fa66bb2   |   16 |        4 | макс                                                                     |        1020 | short    |

⚠ Turn 10 of call `8fa66bb2` — phrase cut mid-thought. See Regression
check below.

---

## A/B Statistics

### Overall

| Metric        | Baseline (18.04 AM) | Post-deploy (hint=700) | Δ          |
|---------------|--------------------:|-----------------------:|-----------:|
| n             | 22                  | 21                     | —          |
| min           | 597                 | 869                    | +272       |
| max           | 2153                | 1675                   | −478       |
| mean          | 1736.5              | 1117.0                 | **−619.5** |
| **median (p50)** | **1778**         | **1036**               | **−742 (−42 %)** |
| p90           | 2051                | 1177                   | −874       |
| p95           | 2148                | 1446                   | −702       |

Sorted post-deploy (n=21):
`869, 904, 988, 1010, 1012, 1015, 1020, 1021, 1028, 1033, 1036, 1037,
1128, 1136, 1145, 1153, 1162, 1167, 1177, 1446, 1675`
- median = index 10 (1036 ms)
- p90 = rank (21−1)·0.9 = 18 → index 18 = 1177 ms
- p95 = rank (21−1)·0.95 = 19 → index 19 = 1446 ms

### By text_len category

| Category | Baseline median | Post-deploy median | Δ median  | Baseline n | Post-deploy n |
|----------|----------------:|-------------------:|----------:|-----------:|--------------:|
| short (≤15)     | 1924        | **1011**           | **−913 (−47 %)** | 9 | 6 |
| medium (16-60)  | 1790        | **1145**           | **−645 (−36 %)** | 7 | 11 |
| long (>60)      | 1662        | **1076**           | **−586 (−35 %)** | 6 | 4 |

Sorted samples:
- short n=6: `904, 988, 1010, 1012, 1020, 1036` → median = (1010+1012)/2 = 1011
- medium n=11: `1021, 1028, 1033, 1037, 1128, 1145, 1153, 1162, 1167, 1177, 1446` → median = 1145
- long n=4: `869, 1015, 1136, 1675` → median = (1015+1136)/2 = 1075.5

### Phantom EOU rate

| Call | valid | phantom | phantom rate |
|------|------:|--------:|-------------:|
| bae62e1d | 5 | 6 | 55 % |
| b858cbe0 | 7 | 8 | 53 % |
| 8fa66bb2 | 9 | 10 | 53 % |
| **Total post-deploy** | **21** | **24** | **53 %** |
| Baseline total | 22 | 26 | 54 % |

**No change** in phantom rate — confirms phantoms are a Yandex protocol
artefact independent of `max_pause_hint_ms`.

---

## Regression check

### Fallback phrase audit

Search `journalctl` for voice_asterisk.py fallback strings:

```
grep -E "плохо слышно|Простите, повторите|повторите пожалуйста" …
```

**1 occurrence** in post-deploy sample:

```
07:39:29.757 INFO __main__:_process_turn:942 -
🧠 SOFIA: "Простите, плохо слышно, можете повторить?"
```

Triggered after call `8fa66bb2` turn 10 (`text_len=49,
eou_wait_ms=1021, text = "дать вот вот этот гарантированный доход
он вообще"`).

### Transcript audit

Per-call inspection of every USER line for mid-sentence cuts:

| UUID       | turns | cuts | notes |
|------------|------:|-----:|-------|
| bae62e1d   |     5 | 0    | 5×"да" + "ватсап", nothing to cut ✅ |
| b858cbe0   |     7 | 0    | medium phrases, all syntactically complete ✅ |
| 8fa66bb2   |     9 | **1** | turn 10: "дать вот вот этот гарантированный доход **он вообще**" — ends on adverb "вообще" with no following clause. User was mid-thought ("он вообще [гарантирован]?") — Yandex cut at hint-forced pause. User **retried** at turn 12 with complete re-framed question "это статистика может быть или вообще откуда взялись эти цифры". Call recovered to successful close. |

### Baseline comparison

| Metric | Baseline | Post-deploy |
|--------|---------:|------------:|
| turns with mid-sentence cut | 0 / 22 | **1 / 21 (≈ 5 %)** |
| fallback "плохо слышно" occurrences | 0 | **1** |
| calls that completed RIZALTA script | 4 / 4 | 3 / 3 |

**Quantified regression: 1 turn in 21 was cut mid-thought, triggering
Sofia's fallback.** Call recovered — user retried and reached goodbye.
Product-level impact is a single "повторите пожалуйста" on one turn;
not a call-killer on this sample, but statistically non-zero.

---

## Target assessment

Targets set by orchestrator: **median ≤ 1500 ms, p95 ≤ 2000 ms**.

| Target | Actual post-deploy | Status |
|--------|-------------------:|--------|
| median ≤ 1500 ms | 1036 ms | ✅ hit by **464 ms margin** |
| p95 ≤ 2000 ms    | 1446 ms | ✅ hit by **554 ms margin** |

Both targets achieved with significant headroom.

Per-category predictions from `docs/EOU_BASELINE_2026-04-18.md` vs.
reality:

| Category | Predicted Δ | Actual Δ | Prediction |
|----------|------------:|---------:|------------|
| short    | −200 to −500 ms | **−913 ms** | **overshot** the range (hint hit short much harder than predicted) |
| medium   | −150 to −300 ms | **−645 ms** | overshot |
| long     | −50 to −150 ms  | **−586 ms** | **drastically overshot** — long-category was predicted near content-aware floor, but hint cut additional 586 ms |

The prediction that `short > medium > long` in *magnitude* held
qualitatively (913 > 645 > 586), but absolute numbers are 2-5× higher
than predicted. Hint=700 is far more aggressive than guessed. This is
useful signal for the next tuning step: the hint is a bigger knob than
baseline analysis suggested.

---

## Decision

### Strict AC #10 reading

- gain ≥ 100 ms overall: **YES** (−742 ms median, far exceeds threshold).
- 0 regressions: **NO** (1 mid-sentence cut in 21 turns; 1 fallback).

Per the contract's binary rule, **strict decision is "tune"** — not
"keep", because regressions are non-zero; not "rollback", because gain
is large and targets are hit with margin.

### Recommended next action: **tune — raise hint to 900 ms**

Reasoning:

1. **Gain budget is huge.** Overall median at 1036 ms is 464 ms below
   target. Raising hint by 200 ms (to 900 ms) would plausibly add
   ~150-250 ms to median (less than the 464 ms budget) while reducing
   the class of regressions seen on call 8fa66bb2. The exact 8fa66bb2
   regressed phrase ended in "он вообще" — a hanging adverb is a
   classic thinking-aloud micro-pause signal; 200 ms more patience
   would likely have caught the intended continuation.
2. **Safer than 500 ms tightening, more effective than rollback.**
   The original Phase 1 contract pre-approved 500 ms as a follow-up
   *if* 700 ms showed no regression. The opposite direction (loosen
   to 900 ms) is the natural response when regressions appear.
3. **Preserves the core Phase 1 win.** Short-category median 1011 ms
   → even if 900 ms adds 200 ms → still ~1200 ms, still a −700 ms
   gain vs. baseline's 1924 ms.
4. **Same rollback path.** L0 rollback (`sed` on `.env`) unchanged;
   L1 snapshots still valid.

### Alternative reads

- **"Keep as-is"** — defensible if 1 fallback per 21 turns is an
  acceptable UX cost for the 42 % median pause reduction. Argument:
  Sofia's fallback is polite ("Простите, плохо слышно") and the user
  naturally retries; call still closed successfully. Gain of ~740 ms
  on every turn is a visible UX improvement; 1/21 "повторите?" is
  small. However this directly violates AC #10's "0 regressions"
  requirement for "keep", so orchestrator sign-off required.
- **"Rollback to hint=0"** — overkill. The regression was a single
  hanging-adverb case, not a systemic phrase-cutter. Rollback would
  discard a 42 % gain to eliminate ~5 % regression, a poor trade.

### Recommended sprint: tune hint to 900 ms, re-run 3 calls

Change: one `sed` on VPS `.env`:
```
sed -i 's/^YANDEX_MAX_PAUSE_HINT_MS=700/YANDEX_MAX_PAUSE_HINT_MS=900/' /opt/sofia-voice/.env
systemctl restart sofia-voice
```

Then 3 more test calls with same category mix (short/medium/long with
micro-pauses), same regression audit, same A/B format. Expect:
- median ~1200-1250 ms (still way below 1500 target)
- 0 or 1 regressions in ≥20 turns
- Re-evaluate: if 900 ms also regresses → try 1000 ms.

### Not recommended: 800 ms intermediate

The gain budget is large enough to skip the intermediate step and go
directly to 900 ms. Doing 800 → 900 → 1000 across multiple sprints
wastes Sergey's test-call budget. 900 ms is a defensible choice in one
step given today's data.

---

## Open questions

1. **Is the single regression rate representative?** n=21 is too small
   to claim "5 % regression rate" with confidence. Could be 1 % at
   scale, could be 15 %. The 900 ms tune re-test will double the
   sample and provide a better estimate.
2. **Does hint interact with `general:rc` model specifically?** Unknown
   if `general` (stable) would behave differently. Out of scope for
   this sprint; noted for future.
3. **Phantom rate unchanged** despite significantly faster real EOU
   suggests Yandex's duplicate frame emission is not timing-bound,
   it's protocol-bound. Reinforces the conclusion from
   `docs/EOU_BASELINE_2026-04-18.md` — phantoms are Yandex-side, not
   ours.

---

## Side observations

1. **Cut phrase "дать вот вот этот гарантированный доход он вообще"
   starts with an STT error** — the first word "дать" is likely
   "дай[те]" or "да" misheard as "дать" due to the preceding 8fa66bb2
   turn 8 fragmented "здравствуйте а да". This is compound — the STT
   quality was already marginal on this turn, and hint=700 tipped it
   from "marginal-but-complete" to "marginal-and-cut". Possibly the
   regression rate on *clean* STT would be lower than 5 %.
2. **Long-category gain (−586 ms) was unpredicted magnitude.** Baseline
   analysis flagged long as "close to content-aware floor" based on
   the 597 ms outlier from call 866bb7cf turn 6 (reduplicated "всё
   всё всё"). Post-deploy long medians came in at 869-1675 ms; the
   predicted floor wasn't as tight as imagined. Real mechanism: even
   on long phrases, Yandex waits for silence; hint directly shortens
   silence-wait. Lesson for the VLAT-07 deep dive: the content-aware
   component is present but smaller than assumed.
3. **Call 8fa66bb2 included two unusual STT oddities** — "здравствуйте
   а да" (mid-call "здравствуйте" is clearly wrong) and "дать вот вот"
   (opening on nonsense verb). These are not Phase 1 regressions
   — they pre-existed and are upstream STT quality issues. Useful
   signal for a future STT-quality audit.
