# RIZALTA v4 Deploy Results — 2026-04-18

Live-test summary of `VOICE_SYSTEM_PROMPT_RIZALTA` v4 deploy (commit
`ffcde20e`, 08:26 UTC). Configuration unchanged from Phase 1:
`YANDEX_MAX_PAUSE_HINT_MS=700`, `EOU=high`, YandexGPT Pro, Alena TTS.

---

## Calls

| UUID                       | ts_start (UTC)       | billsec | msgs | disposition | intent |
|----------------------------|----------------------|--------:|-----:|-------------|--------|
| `5600c4af-6574-4f06-…`     | 2026-04-18 08:28:28  | 74      | 11   | ANSWERED    | **short** scenario — 1-2 word answers |
| `0ae0b897-9655-4c66-…`     | 2026-04-18 08:35:32  | 106     | 15   | ANSWERED    | **medium** scenario — 3-6 word answers with detail requests |

## EOU_WAIT metrics (v4 vs Phase 1 baseline)

| Metric      | Phase 1 baseline (morning) | v4 (this deploy) | Δ     |
|-------------|---------------------------:|-----------------:|------:|
| n valid     | 21                         | 12               | —     |
| median      | 1036 ms                    | **1038 ms**      | +2 ms (noise) |
| min         | 869                        | 514              | —     |
| max         | 1675                       | 1553             | —     |

**No EOU regression.** Median essentially identical (+0.2 %) — confirms
prompt content length does not affect EOU timing, only Phase 1 hint does.

Per-turn v4:
- Call 1 (n=5): `761, 790, 1016, 1274, 1553` → median **1016**
- Call 2 (n=7): `514, 1028, 1037, 1039, 1052, 1383, 1397` → median **1039**

(Call 2 had one sub-2-char STT fragment at turn 2 `text_len=1`,
filtered pre-pipeline by voice_asterisk.py:908 `len(text.strip()) < 2`
guard — excluded from stats, as baseline extraction did.)

---

## Variability audit

### Call 1 (short scenario) — Sofia utterances

| Stage | Exact wording |
|-------|---------------|
| Pitch part 1 | (cached PCM, unchanged) |
| Pitch part 2 closer | **«Дальше интересно?»** |
| Details closer | «Подходит такой формат?» |
| Material offer | **«Скинуть материалы с ценами и планировками?»** |
| Messenger ask | **«Куда отправить? Телеграм, ватсап или макс?»** |
| Farewell | **«Пришлю через десять минут. Всего доброго!»** |

### Call 2 (medium scenario) — Sofia utterances

| Stage | Exact wording |
|-------|---------------|
| Pitch part 1 | (cached PCM, unchanged) |
| Pitch part 2 closer | **«Дальше интересно?»** |
| Objection/detail closer (payback) | **«Рассказать про сам проект?»** |
| Details closer (Белокуриха) | «Подходит такой формат?» |
| Guarantees closer | **«Хочется подробнее?»** |
| Material offer | **«Скинуть материалы с ценами и условиями?»** |
| Messenger ask | **«Куда отправить? Телеграм, ватсап или макс?»** |
| Farewell | **«Пришлю через десять минут. Всего доброго!»** |

### Cross-call comparison

| Variable slot | Call 1 | Call 2 | Same/Different |
|---------------|--------|--------|----------------|
| Pitch part 2 closer | «Дальше интересно?» | «Дальше интересно?» | **same** |
| Material offer | «Скинуть … с ценами и планировками?» | «Скинуть … с ценами и условиями?» | **different** (суффикс) |
| Messenger ask | «Куда отправить? Телеграм, ватсап или макс?» | «Куда отправить? Телеграм, ватсап или макс?» | **same** |
| Farewell | «Пришлю через десять минут. Всего доброго!» | «Пришлю через десять минут. Всего доброго!» | **same** |

**Cross-call variation: 1/4 slots varied.** Weaker than
hoped but present. Reasonable explanation: with 3-6 options per slot
and only 2 sample calls, same-choice probability is ~30-50 % per slot.
A single extra call would give better signal on whether LLM actually
diversifies across calls over the long run.

### Within-call variation

**Call 1** — 4 distinct closer questions used in 4 positions. Zero
within-call repeats. ✅

**Call 2** — 5 distinct closer questions («Дальше интересно?»,
«Рассказать про сам проект?», «Подходит такой формат?», «Хочется
подробнее?», «Скинуть материалы с ценами и условиями?») in 5 positions.
Zero within-call repeats. ✅

Grep-count verification (per-call transcript grep):
- «Хотите узнать подробнее?» — **0 occurrences in either call** ✅
  (old v3 default removed — Sofia never used it)
- «Хотите отправлю финмодель, планировки и цены?» — 0 in either call ✅
  (old v3 default removed)
- «Отлично» — **0 in either call** ✅ (v4 "use почти никогда" rule
  followed perfectly; previously used in every RIZALTA call)

---

## Funnel-stage integrity

| Stage | Call 1 | Call 2 |
|-------|-------:|-------:|
| Pitch part 1 (greeting) | ✅ | ✅ |
| Pitch part 2 (after consent) | ✅ | ✅ |
| Details (Белокуриха, 15 млн, гарантии) | ✅ | ✅ |
| Deeper facts (214-ФЗ, Жилищная Инициатива, эскроу) | N/A (клиент не просил) | ✅ (pulled correctly from "ЧТО ТЫ ПРОДАЁШЬ" block when client asked) |
| Material offer | ✅ | ✅ |
| Messenger ask | ✅ | ✅ |
| Farewell | ✅ | ✅ |

No stages skipped. All facts pulled from the locked "dolsovno" block
are accurate (цифры, имена компаний, 214-ФЗ, эскроу).

---

## Regression check

| Item | Call 1 | Call 2 | vs Phase 1 baseline |
|------|--------|--------|---------------------|
| mid-sentence cuts | 0 / 5 | 0 / 7 | baseline had 1 / 21 — v4 no regressions |
| «Простите, плохо слышно» fallback | 0 | 0 | baseline 1 — v4 no occurrences |
| Pipeline errors / exceptions | 0 | 0 | — |
| EOU_WAIT median | 1016 ms | 1039 ms | 1036 ms — within noise |

No regressions observed. Phase 1 performance fully preserved.

---

## TTS pronunciation issues (found by orchestrator listening)

These are **Yandex TTS Alena** problems, not prompt problems. Fix
options are separate sprints (variant replacement in prompt, or
Unicode U+0301 stress marks, or TTS custom dictionary).

| Phrase | Used in | Issue | Fix path |
|--------|---------|-------|----------|
| «Дальше интересно?» | Call 1 + Call 2 (both pitch part 2) | Yandex stresses 1st word; should be 2nd | Replace in variant list (**next sprint, trivial**) |
| «Хочется подробнее?» | Call 2 (guarantees closer) | Yandex stresses 2nd word; should be 1st | Replace in variant list (**next sprint, trivial**) |
| «Белокуриха» | Both calls (во всех details replies) | Yandex says «Белокурих́а» (предпосл. ударение); правильно «Белоќуриха» (на «у») | **Not trivially fixable** — word appears in locked facts block, используется много раз. Варианты: (a) Unicode U+0301 stress mark `Белоку́риха`, (b) Yandex custom dictionary (separate sprint), (c) переформулировать говоримый текст на `курорт в Алтайском крае` избегая топонима, но теряется специфика |

The Belokurikha issue is the more expensive to fix — word is
central to the sales pitch and appears in the locked "dolsovno" block
multiple times.

---

## Decision

**keep.** v4 is a strict improvement over v3:
- Within-call repeats eliminated (was the core complaint from 10 test
  calls on v3).
- Content of locked facts intact; funnel stages intact.
- Zero regressions on 12 turns; EOU median within Phase 1 noise.
- Cross-call variation weaker than ideal but present; will improve
  with more samples as LLM rotates through variant pools.

**Next immediate follow-ups (not this sprint):**
1. Fix «Дальше интересно?» and «Хочется подробнее?» TTS stress by
   replacing variants in the prompt (1-line edits each).
2. Investigate Belokurikha TTS stress as separate sprint.

**Not-to-do:**
- Rollback to v3 — no regressions justify discarding v4 improvements.
- Further prompt tweaks in the same sprint — let this version stabilise
  across more real calls first.
