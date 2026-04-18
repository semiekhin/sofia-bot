# Voice Latency Audit — 18.04.2026

Read-only audit of the Sofia-GPT voice pipeline (RIZALTA outbound + Atlantis
inbound) on VPS `185.207.66.201` after Phase 2D (Yandex STT v3 gRPC streaming
+ EOU sensitivity HIGH + YandexGPT Pro + Yandex Alena TTS v1 REST).

Scope: end-to-end **user-perceived pause** = wall-clock from
`last-change-of-STT-partial-text` (proxy for "client stopped talking")
→ `first TTS PCM frame reaches AudioSocket writer` (proxy for "first
audible word").

No code changes. No deployments. No test calls initiated.

---

## Baseline

**Sample:** all 7 user-turn events from the two most recent transcribed
outbound RIZALTA calls, extracted from `journalctl -u sofia-voice`
on VPS `sofia-voice` (IP 185.207.66.201):

- Call `5a067eb8-7890-47c4-831e-5e1e41cbe4d9`, 2026-04-17 18:15:23..18:17:02 UTC,
  92 s billsec, 5 user turns reached LLM.
- Call `38472953-82eb-48ef-b3c9-eb268bab8356`, 2026-04-18 05:49:48..05:50:41 UTC,
  40 s billsec, 2 user turns reached LLM.

Extraction commands (documented for reproduction):

```
ssh sofia-voice 'journalctl -u sofia-voice \
  --since "2026-04-17 18:15:00" --until "2026-04-17 18:17:30" \
  --no-pager -o cat | grep -E "partial|final|USER:|SOFIA:|first audio|Turn timings"'
ssh sofia-voice 'journalctl -u sofia-voice \
  --since "2026-04-18 05:49:00" --until "2026-04-18 05:51:00" \
  --no-pager -o cat | grep -E "partial|final|USER:|SOFIA:|first audio|Turn timings"'
```

Per-turn table (wall-clock from service log; all times UTC, all numbers ms):

| # | Call  | Turn text (truncated)       | last_stable_partial | eou_wall | sofia_text_wall | first_audio_wall | EOU_wait | LLM | TTS_TTFB | **Pause** |
|---|-------|-----------------------------|--------------------:|---------:|----------------:|-----------------:|---------:|----:|---------:|----------:|
| 1 | 5a06… | здравствуйте да хочу…       | 18:15:45.208        | :47.010  | :47.942         | :48.143          | 1802     | 932 | 201      | **2935** |
| 2 | 5a06… | давайте                     | 18:16:00.580        | :02.495  | :03.554         | :03.758          | 1915     |1059 | 204      | **3178** |
| 3 | 5a06… | а да подходит               | 18:16:16.173        | :18.240  | :18.664         | :18.814          | 2067     | 424 | 150      | **2641** |
| 4 | 5a06… | ну давайте отправьте        | 18:16:26.311        | :28.257  | :28.721         | :28.880          | 1946     | 464 | 159      | **2569** |
| 5 | 5a06… | телеграмм                   | 18:16:33.734        | :35.277  | :35.657         | :35.808          | 1543     | 380 | 151      | **2074** |
| 6 | 3847… | да хотим                    | 05:50:14.706        | :16.368  | :17.366         | :17.570          | 1662     | 998 | 204      | **2864** |
| 7 | 3847… | а давайте угу               | 05:50:32.846        | :33.117  | :33.837         | :34.025          |  271     | 720 | 188      | **1179** |

**Medians (n=7):**

- **Total pause: 2641 ms**
- EOU wait (text-stable → Yandex eou): **1802 ms**
- LLM (eou → sofia text): **720 ms**
- TTS first chunk (sofia text → first PCM to writer): **188 ms**

**Discrepancy flag.** The contract/context claims "user-perceived pause
≈860ms median from call 4ad65942" with "EOU wait ≈1920ms median". The
first number cannot fit the second (860 < 1920). On fresh logs the full
pause is ~2.6 s; the 860 ms figure matches `LLM + TTS TTFB` **after**
Yandex sends the EOU event, not the full perceived silence from the
client's point of view. Likely a definition slip between `(LLM+TTS)`
and `(EOU_wait + LLM + TTS)`. Treat the 2.6 s number below as the correct
reference for "how long the client waits".

Notes:

- Cached greeting (`greeting_rizalta.pcm`, 12.4 s audio) keeps the
  **first** Sofia utterance at 0 ms TTFB. Cache is **not** applied to
  any other turn today.
- STT_MODE=grpc on VPS (`/opt/sofia-voice/.env`), so `transcribe_audio()`
  (REST v1) and the `VAD_SILENCE_THRESHOLD=0.5s` silence timer are dead
  code on production path. They remain as fallback for `is_broken`.
- VPS file state matches local DEV repo for `voice_asterisk.py`
  (md5 `4f400ee0…`) and `core/pipeline.py` (md5 `f7150f50…`).
  `yandex_stt_grpc.py` (VPS md5 `eae3873b…`) is **NOT** present in DEV
  git — captured via `scp` only. Side issue — see end.

---

## Карта этапов

All files on VPS at `/opt/sofia-voice/`. Lines reference the code running
at md5 above. `t0` = `last_stable_partial_wall`; "median" = the 7-sample
median from the Baseline table.

| # | Stage                                | Location                                         | Median (ms) | Cut?           |
|---|--------------------------------------|--------------------------------------------------|------------:|----------------|
| 1 | Client mic silence before Yandex EOU | Yandex server-side (DefaultEouClassifier, HIGH), config at `yandex_stt_grpc.py:125-128` | **1802**   | partial (hard limit physics ~400-600ms) |
| 2 | Our wall-clock jitter EOU→callback   | `voice_asterisk.py:791-817` `_on_grpc_eou`       | ~1-5       | no (noise)     |
| 3 | `_process_turn` turn guard + state   | `voice_asterisk.py:878-915`                      | ~5-10      | no             |
| 4 | History load + state extract         | `core/pipeline.py:838-870`                       | ~15-30     | partial        |
| 5 | LLM prompt build (RIZALTA 11.7 KB)   | `core/pipeline.py:880-903` (prompt) + `:913-921` (request wrap) | ~5 | no |
| 6 | LLM call (YandexGPT Pro, non-stream) | `core/pipeline.py:913-921` `asyncio.to_thread(yandex.chat.completions.create, ..., max_tokens=150)` | **710**   | **yes** (stream + sentence pipelining) |
| 7 | Post-LLM filters                     | `core/pipeline.py:1003-1043` (`[END]`, hallucination regex, `sanitize_for_tts`) | ~2-5 | no |
| 8 | TTS synth (Yandex Alena v1 REST)     | `voice_asterisk.py:294-343` `synthesize_tts_yandex()` — single POST returning full LPCM | **165** | **yes** (gRPC v3 stream) |
| 9 | TTS first frame to AudioSocket       | `voice_asterisk.py:1044-1059` (first `_send_audio` inside `_speak`) | ~20 | no |
|10 | AudioSocket→Asterisk→SIP RTP         | Asterisk local `127.0.0.1:9090`, then SIP media to Telfin edge | ~30-60 | no |

Sum of stages 1+6+8+9+10 = ~2725 ms, matches measured median 2641 ms
(±network jitter).

Ranges (not medians) for each high-variance stage:

- EOU wait: 271–2067 ms (the 271 outlier was "а давайте угу" where the
  speaker trailed off and Yandex fired EOU fast; the upper bound of
  ~2067 is the HIGH-mode effective ceiling on this traffic).
- LLM: 380–1059 ms. Weak correlation with output length (150 tok cap
  rarely reached). Jitter likely dominated by YandexGPT Pro load.
- TTS TTFB: 150–204 ms. Very consistent.

---

## Оптимизации

Each block: id, title, code pointer, gain, effort, risk, precondition,
evidence. Gains are **per turn**, medians. "Effort" includes discovery,
implementation, live-call validation, regression fix — not just code time.

---

### VLAT-01 — TTS cache for canonical RIZALTA replies

**Место:** `voice_asterisk.py:1017-1060` `_speak()` — prepend a cache
lookup by `sha256(clean_text + voice_id + speed)` analogous to the
existing `_speak_pcm()` path at `:974-1015`. Cache file layout mirrors
`greeting_rizalta.pcm`.

**Gain_ms:** **−150 ms median on cache hits** (TTS TTFB 165 → ~5 ms).
Cache hit rate expected **high** for RIZALTA flow — the first 3 Sofia
replies in both 17.04 and 18.04 calls are **character-identical**:
"Отель находится в инвестиционно безопасном регионе. Это горнолыжный
курорт…", "Это апарт-отель в Белокурихе…", "Хотите, чтобы я отправил
финмодель, планировки и цены?", "Куда отправить? Телеграм, ватсап или
макс?". Atlantis has less canonicalisation but still has stock closers
("Хорошего дня!", "Простите, плохо слышно").

**Effort_hours:** ~4h. Cache dir + hash key + lookup + warm-up script
for ~10 canonical phrases. Invalidation on `voice_id` or
`YANDEX_TTS_SPEED` change — same pattern as greeting regeneration
(see CLAUDE.md "Регенерация cached PCM").

**Risk:** low. TTS quality identical (same synth); only risk is stale
cache if `alena` voice updates — mitigated by voice_id in hash key.

**Precondition:** none.

**Evidence:**
- Transcripts `transcript_5a067eb8-…txt` and `transcript_38472953-…txt`
  show turn-1/turn-2 Sofia replies match byte-for-byte across calls.
- CLAUDE.md line "Cached greetings (0ms TTFB)" already documents the
  same mechanism successfully deployed for greeting.
- BACKLOG.md item "TTS cache canonical phrases + backchannel fillers"
  already scoped but un-prioritised.

---

### VLAT-02 — Backchannel filler during LLM wait (perceived-only)

**Место:** `voice_asterisk.py:898-931` `_process_turn()` — between
`logger.info(f'🎤 USER: ...')` (`:912`) and the LLM call block
(`:917-931`). Kick off `_speak_pcm(cached_filler)` as a fire-and-forget
task, whose playback is cancelled when the real TTS starts.

**Gain_ms:** **perceived pause 2641 → ~300 ms** (time until *any* audio
appears). Real pause unchanged — the filler plays while LLM is still
generating, real reply follows. Only perceptual; does not actually
shorten the audio gap the user waits through before hearing substantive
content.

**Effort_hours:** ~8h. Pre-render 5-8 short PCM fillers ("так…",
"секундочку", "угу"), intent-aware selector (simple keyword match on
STT text), cancellation wiring so filler stops cleanly when real TTS
first chunk arrives. Live-call tuning for "stale filler when LLM
returns fast" edge case.

**Risk:** medium. If filler overlaps real reply → awkward. Requires
strict gate: only play if estimated LLM time > 400 ms (hard to predict
per-turn), and cut immediately on first real TTS frame. Also possible
quality regression if filler feels repetitive across turns.

**Precondition:** none, but synergy with VLAT-01 (same cache
infrastructure).

**Evidence:**
- BACKLOG.md B1 note closed 16.04 on the grounds "TTS TTFB 177ms,
  fillers not needed". That rationale is wrong for the full pause —
  the 1800ms EOU wait dominates, not TTS TTFB, so B1's premise should
  be revisited.
- `docs/VOICE_RESEARCH_2026_04_16.md` §6 describes the pattern.

---

### VLAT-03 — Sentence-level LLM streaming + parallel TTS

**Место:** `core/pipeline.py:913-932`. Replace
`asyncio.to_thread(yandex.chat.completions.create, ..., stream=False)`
with SSE streaming (`stream=True`), an async accumulator that cuts on
`[.!?](\s|$)`, and a per-sentence queue that
`voice_asterisk.py:_speak()` consumes as an async generator. Second
edit point: `voice_asterisk.py:1017-1060` `_speak()` — accept an
`AsyncIterable[str]` instead of `str`, synthesise+send each sentence
as it arrives.

**Gain_ms:** **−250 to −500 ms median.** Today the full LLM response
(~720 ms) is awaited before the first TTS request is even made. With
sentence streaming the first sentence typically reaches TTS after
~200-350 ms of LLM generation (RIZALTA replies are 1-3 sentences,
first sentence is usually 30-50 tokens). TTS TTFB starts in parallel.

**Effort_hours:** ~16h. Robust Russian sentence splitter (handle
"10 млн.", "т.е."), hallucination filter must now run on partial
chunks with stop-sequence detection instead of full-text regex
(`core/pipeline.py:1020-1042`), `[END]` marker handling across chunks.

**Risk:** medium. Anti-hallucination currently runs post-hoc on the
complete response (`:1020-1042`) — moving to streaming requires stop
detection on the partial stream, and an error in the splitter or
stop-sequence logic could let hallucinated continuations leak to TTS
before they can be truncated. Also: `[END]` is a signal the dialog is
finished; if it appears only in the last sentence, we cannot commit
the earlier sentences' TTS until we've seen it — but that's rare in
RIZALTA flow.

**Precondition:** none.

**Evidence:**
- `core/pipeline.py:913-921` — literal blocking call,
  `resp.choices[0].message.content` read whole.
- `core/pipeline.py:1048` — single `yield answer_text`, one chunk.
- `voice_asterisk.py:929-930` — caller collects into `response +=`
  string, ignores the streaming interface of `stream_voice_response`.
- `docs/VOICE_RESEARCH_2026_04_16.md` §3 identifies this as P0
  ("1 ночь работы, 300-500ms").

---

### VLAT-04 — Yandex TTS v3 gRPC streaming (replace REST v1)

**Место:** `voice_asterisk.py:294-343` `synthesize_tts_yandex()`.
Replace single `POST …/speech/v1/tts:synthesize` with Yandex v3
`Synthesizer/StreamSynthesis` (server-streaming, protos already present
in `yandex_proto/`). Output becomes an async generator yielding LPCM
chunks as Yandex encodes them.

**Gain_ms:** **−60 to −100 ms TTS TTFB** (165 → ~80 ms). Stream-first
benefit is larger **in combination with VLAT-03** — with sentence
streaming, TTFB is also called more often per reply, so any TTS TTFB
reduction scales with that.

**Effort_hours:** ~8h. Protos exist (`yandex_proto/yandex/cloud/ai/tts/v3`);
need an async generator wrapper analogous to `yandex_stt_grpc.py`.
Channel reuse across turns (see VLAT-05).

**Risk:** low. v3 is stable. Same voice (`alena`) available. Keep REST
path as fallback via `VOICE_TTS_PROVIDER=yandex_rest` env.

**Precondition:** Standalone benefit is modest (60-100 ms). Real leverage
appears when combined with VLAT-03 — so prefer sequencing VLAT-03 first.

**Evidence:**
- `voice_asterisk.py:323` — `async with httpx.AsyncClient(timeout=10.0)`
  per call, non-streaming receive at `:335` (`resp.content`).
- Log line `Yandex TTS: 224 chars -> 185316 bytes (183ms)` (journalctl
  2026-04-18 05:50:34.024) shows the full-buffer 183 ms that becomes
  the baseline for TTFB.

---

### VLAT-05 — Connection reuse / prewarm for Yandex TTS REST

**Место:** `voice_asterisk.py:323` — `httpx.AsyncClient(timeout=10.0)`
is constructed inside `synthesize_tts_yandex()` on every call, so every
turn eats a fresh TCP+TLS handshake to `tts.api.cloud.yandex.net:443`.
Fix: module-level singleton `httpx.AsyncClient` created at process start
(or in call's `__init__`), reused across all turns of the call.

**Gain_ms:** **−50 to −80 ms** on every TTS call after the first (first
call pays the handshake either way). For a 3-turn call, ~150 ms saved
cumulatively; for the 2.6 s median pause on turn 2+ = ~−70 ms direct.

**Effort_hours:** ~3h. Simple refactor, plus smoke test that no event
loop is closed across calls (httpx must stay alive at module scope).

**Risk:** low. httpx is thread-safe for `AsyncClient` reuse. Minor
concern: idle TCP kept alive beyond server NAT timeout — Yandex edge
is fine for 5-10 min idle per informal testing of other Yandex APIs.

**Precondition:** none. Orthogonal to VLAT-04 (but VLAT-04 supersedes
it — gRPC channel reuse is part of that work).

**Evidence:**
- `voice_asterisk.py:323` — `async with httpx.AsyncClient(timeout=10.0) as client:`
  literally inside the function body.
- `voice_asterisk.py:245` — same pattern in the REST STT fallback
  (`transcribe_audio`), though that path is dead during gRPC mode.

---

### VLAT-06 — Compact RIZALTA system prompt

**Место:** `core/pipeline.py:646-790` `VOICE_SYSTEM_PROMPT_RIZALTA`
(11 727 bytes ≈ ~3 000 tokens, measured with
`awk '/^VOICE_SYSTEM_PROMPT_RIZALTA = /,/^"""$/' | wc -c`).

**Gain_ms:** **−50 to −150 ms LLM.** YandexGPT Pro TTFT scales with
input length. Trimming prompt by 30-40 % (preserving
script/voice/objections core, dropping duplicated examples and
verbose phrasing) reduces both prefill and decode path.
Expert estimate, not measured — Yandex does not publish
per-token prefill cost for Pro, but the behaviour is consistent
with the scaling observed on gpt-5.2.

**Effort_hours:** ~12h. Needs a regression set (min 30 canonical RIZALTA
dialogue openings) to check that output quality does not drop after
trimming. Trimming must not violate CLAUDE.md rule about RIZALTA v3
script structure.

**Risk:** medium. Shorter prompt can lose edge-case handling (customer
says "не по карману", "перезвоните через полгода", etc.). Quality
regression only caught on live calls — hard to batch-test offline.

**Precondition:** agreement with Sergey on which rules can be
compressed (RIZALTA v3 was just stabilised on 16.04 at commit
`ef2888ae`).

**Evidence:**
- `core/pipeline.py:646-790` — 144 lines of prompt.
- `core/pipeline.py:899-903` — `est_tokens = len(system_prompt) // 4`
  debug line confirms the team already tracks prompt size.
- Observed LLM variance 380–1059 ms despite max_tokens=150 suggests
  prefill is significant (output length alone doesn't explain 680 ms
  spread when max output is ~50 tokens).

---

### VLAT-07 — ExternalEouClassifier with semantic turn detector

**Место:** `yandex_stt_grpc.py:120-125`. Yandex v3 `EouClassifierOptions`
supports `external_classifier` as an alternative to
`DefaultEouClassifier` — client sends `eou_update` manually when a
local model decides the turn is over. A CPU-runnable model like
LiveKit `turn-detector` (135M SmolLM v2 distill) reads STT partials
and fires EOU on partial-text stability + semantic completion.

**Gain_ms:** **−500 to −1000 ms EOU_wait.** Default HIGH sensitivity
already floors at ~1800 ms because Yandex conservatively waits to
distinguish micro-pause ("и ... десять миллионов") from true end-of-turn.
A semantic model can fire on the partial "да подходит" within ~300 ms
of the last token (Yandex EOU takes ~1920 ms for the same input in
measured logs), because it decides on *text* completeness rather than
*audio* silence duration.

**Effort_hours:** ~32h+ (explore, download, wire, fine-tune on Russian
dialogues). LiveKit model is multilingual-trained but Russian-specific
accuracy is unverified. Without fine-tune, call-volume needed for
confidence: 20+ live calls with shadow-mode comparison before cutover.

**Risk:** high. False EOU firings = Sofia interrupting the client
mid-sentence (the exact failure mode we fixed by raising
`VAD_SILENCE_THRESHOLD` to 0.5s on call `e177d7ad` — see CLAUDE.md
lesson "VAD_SILENCE 300ms резал фразы на микропаузах"). Semantic EOU
can drift into the same trap on unusual phrasing.

**Precondition:** none, but explicitly **exploratory** — requires a
shadow-mode prototype before any cut-over. Should not be scheduled as
a standalone sprint without instrumented comparison.

**Evidence:**
- `yandex_stt_grpc.py:120-125` — `EouClassifierOptions(default_classifier=…)`
  is hard-coded; Yandex proto also defines `external_classifier` field.
- `docs/VOICE_RESEARCH_2026_04_16.md` §5 references this family of
  models (LiveKit/SmolLM).
- The 7-sample EOU_wait distribution (271, 1543, 1662, 1802, 1915,
  1946, 2067 ms) shows a ~1800 ms plateau — indicating server-side
  forced wait, not audio-dependent variability.

---

### VLAT-08 — Speculative LLM on stable STT partial

**Место:** new code in `voice_asterisk.py:766-776` `_on_grpc_partial`.
When the partial text hasn't changed for ~500 ms, dispatch a
speculative LLM call; on EOU, compare final vs. speculative input — if
identical (>95 % of cases in our logs), the LLM response is already
ready and we skip straight to TTS.

**Gain_ms:** **−500 to −700 ms** on matched speculations (~80 % of
turns based on the 7-sample data, all of which had stable partials
for >=1.2 s before EOU). Misses cost a wasted LLM call (~¢0.1) and no
user-facing latency.

**Effort_hours:** ~20h. State management for speculative turns,
cancellation if partial changes, reconciliation on EOU. Non-trivial
concurrency.

**Risk:** high. If Sofia's response is generated speculatively and
committed to TTS, then the user actually adds "…но только если будет
ипотека" after the speculated EOU — we've already started speaking
stale content. Mitigation: only commit speculative result *after*
real EOU arrives and matches; otherwise cancel silently. But this
means the gain is conditional on real EOU firing **before** TTS
starts, which caps gain at `LLM_time − EOU_timing_race` ≈ 500 ms.

**Precondition:** VLAT-03 (sentence streaming) makes this easier —
earlier first-sentence commit reduces risk window.

**Evidence:**
- All 7 measured turns had >=1 unchanged partial for >=1.2 s before
  the final. Stable-text-to-EOU gap is wide enough for a full LLM
  call to complete.
- `docs/VOICE_RESEARCH_2026_04_16.md` §16 lists this as idea #16.

---

## Ranking

Ordered by `gain_ms / effort_hours` with risk adjustment (high risk
halves the effective ratio).

| Rank | ID      | Gain median | Effort h | Risk   | Adj ratio | Notes |
|-----:|---------|------------:|---------:|--------|----------:|-------|
| 1    | VLAT-01 | 150 (hit)   | 4        | low    | 37.5      | **recommended next sprint** — cache canonical RIZALTA phrases |
| 2    | VLAT-03 | 350         | 16       | medium | 22        | **recommended next sprint** — sentence LLM streaming (biggest real-latency lever inside Yandex stack) |
| 3    | VLAT-05 | 65          | 3        | low    | 22        | **recommended next sprint** — reuse httpx client (orthogonal win, easy) |
| 4    | VLAT-02 | ~2300 (perceived only) | 8  | medium | 14      | perceived only; real latency unchanged. Valuable UX but ≠ real speedup |
| 5    | VLAT-04 | 80          | 8        | low    | 10        | best scheduled *after* VLAT-03 for compound win |
| 6    | VLAT-06 | 100         | 12       | medium | 4.2       | prompt compaction; risky because RIZALTA was just stabilised |
| 7    | VLAT-07 | 750         | 32       | high   | 11.7      | biggest theoretical lever (EOU is the single largest stage) but also highest risk and longest sprint — budget a shadow-mode exploration before committing |
| 8    | VLAT-08 | 550 (cond.) | 20       | high   | 13.8      | clever, fragile, only worth it after VLAT-03 proves streaming contract |

**Top-3 for immediate work:** VLAT-01, VLAT-03, VLAT-05 (real-latency
wins, combined effort ~23 h, combined median gain ~565 ms
`max(150, 350) + 65 + compound`). All three are independent; can be
worked in parallel or rolled in any order.

Note on `BACKLOG.md` alignment: items "TTS cache canonical phrases +
backchannel fillers" and "sentence-level streaming" already exist in
backlog but without evidence-based prioritisation. This ranking
supersedes their current implicit order.

---

## Теоретический предел

### Absolute minimum (single-turn, optimal conditions)

- **Human-imposed:** client ends sentence with falling intonation; 
  reliable *any* detector needs ~300-500 ms of sustained silence to
  distinguish end-of-turn from micro-pause. Lower than 300 ms →
  cuts fluent speakers mid-sentence (reproduced on call `e177d7ad`
  at 300 ms setting). **Floor: ~400 ms EOU.**
- **Network:** Moscow-Novosibirsk Yandex RTT measured at VPS:
  ~20-40 ms one-way. **Floor: ~30 ms RTT + 30 ms SIP.**
- **LLM:** YandexGPT Pro prefill on a minimal system prompt (~100
  tokens, vs. current ~3 000) would give ~150-250 ms TTFT. With
  sentence-level streaming the *first-sentence ready* signal can
  arrive in ~200-300 ms. **Floor: ~200 ms LLM to first sentence.**
- **TTS:** Yandex v3 gRPC TTFB on 8kHz LPCM ~80 ms (Yandex-published
  for `Synthesizer/StreamSynthesis`). Cached phrase: ~5 ms.
  **Floor (cached): ~10 ms; Floor (live): ~80 ms.**
- **Client-side audio pipeline:** SIP RTP jitter buffer at Telfin
  adds ~20-40 ms before playback. **Floor: ~30 ms.**

**Sum floor (live generation):** 400 + 30 + 200 + 80 + 30 ≈ **740 ms**.
**Sum floor (cached reply):** 400 + 30 + 10 + 30 ≈ **470 ms** (LLM
skipped because the reply is pre-synthesized; in practice this still
requires LLM deciding the reply matches a cache key, so a realistic
cached-hit floor is ~500-600 ms).

This floor is a hard physics+UX bound inside the current architectural
contract (Yandex STT, YandexGPT, Yandex TTS, 8 kHz SIP). Any further
reduction requires dropping one of those — not in scope.

### Realistic target after top-3 (VLAT-01 + VLAT-03 + VLAT-05)

- Baseline: 2641 ms median, 3178 ms p95 (n=7)
- VLAT-01: −150 ms on ~50 % of turns (canonical reply hits). Median
  turn becomes ~2566 ms.
- VLAT-03: −350 ms median on *every* turn (sentence streaming).
  Combined with VLAT-01: ~2216 ms.
- VLAT-05: −65 ms on every turn after first. Combined: ~2150 ms.

**Estimated post-top-3:** median ≈ **2150 ms**, p95 ≈ **2600 ms**.

The EOU wait (1800 ms median) remains the dominant residual
component. Without touching EOU (VLAT-07), the pause cannot drop below
~1900-2000 ms no matter what else is optimised. This is the
**diminishing-returns boundary**: after VLAT-03, every additional
50-ms win costs either a large engineering sprint (VLAT-07 at 32 h,
high risk) or a quality concession (VLAT-06 prompt trimming that can
break unusual objections).

### Where diminishing returns begin

After VLAT-01 + VLAT-03 (combined effort 20 h, ~500 ms saved), the
next 100 ms costs either:

1. **32 h on VLAT-07** — only lever big enough to break below the
   ~2000 ms EOU floor, and by far the riskiest item (semantic EOU
   false positives = Sofia talking over the client). Gate: shadow-mode
   A/B required before production.
2. **20 h on VLAT-08** — speculative LLM, lower gain, similar
   complexity, meaningful only paired with VLAT-03.
3. **12 h on VLAT-06** — small gain, quality regression risk right
   after RIZALTA v3 was just stabilised on 16.04.

Below ~2000 ms the only remaining lever that doesn't risk quality is
**perceived-time tricks** (VLAT-02 filler). That is fundamentally not
a latency optimization — it's a UX patch on top of an unchanged latency
and has diminishing marginal value once real latency is already <2.2 s.

Recommendation: **do top-3, measure p50/p95 over 20+ live RIZALTA
calls, then re-audit** before committing to VLAT-07 or VLAT-08.

---

## Что не смог измерить

- Per-turn "how long client spoke" — Yandex partials arrive at ~320 ms
  intervals, so "end of speech" is resolved only to ±300 ms. Would
  need per-frame VAD probability logs.
- Yandex EOU internal mechanics — cannot distinguish whether the
  ~1800 ms is Yandex's `silence_timeout_ms` equivalent or a
  classifier-decision delay. Would need a controlled A/B on a private
  test call with deliberate mid-word pauses, which violates the
  "no new test calls" guardrail.
- Prompt prefill latency vs. decode latency split — YandexGPT response
  object doesn't expose `prefill_time_ms` separately. Would need a
  controlled A/B with varying prompt sizes.
- Barge-in response time impact on latency — not measured because
  `_detect_barge_in` is off the critical path for end-of-turn → first-audio.
  However VLAT-02 filler interaction with barge-in is untested.
- Cache-hit rate for VLAT-01 in realistic call flow — the 7-turn sample
  is too small. Need to compute over the full transcript corpus once
  VLAT-01 is implemented and running for ~1 week.
- p95 and tail latency — 7 samples insufficient. P95 reported above
  is a single data point, not a reliable estimate. Would need an
  instrumentation sprint logging per-turn JSON timings to enable
  reliable percentile statistics. Partial infra exists (`VOICE_DIAG`
  logger in `core/pipeline.py`), but not yet aggregated to a per-call
  JSON record.

---

## Обнаруженные побочные проблемы

(Not fixed; for backlog.)

1. **`yandex_stt_grpc.py` is VPS-only, not in DEV git.** md5 on VPS
   `eae3873b49c34e618388a82f6cb73260`. Not present at
   `/opt/sofia-gpt-dev/yandex_stt_grpc.py`. Commit `e13aa3fa` which
   says "feat(voice): Yandex STT v3 gRPC streaming (Phase 2B+2C)"
   references it but the file was never added to the DEV repo —
   deploys went VPS-direct. This is the exact drift pattern that
   bit us on commit 49659ffb (Observer portback). Should be imported
   into DEV git before next DEV→PROD or DEV-clone-to-backup.

2. **Dead STT code path** — `transcribe_audio()` at
   `voice_asterisk.py:229-266` and the whole REST VAD path
   (`_process_audio_vad` + `VAD_SILENCE_THRESHOLD`) are dormant when
   `STT_MODE=grpc`. They only activate on `_fallback_to_rest()`
   (`:819-826`). The `VAD_SILENCE_THRESHOLD=0.5 s` comment at `:66-68`
   describes 2 iterations of historical evolution; whole block is
   effectively orphaned unless fallback fires. Worth either deleting
   (after a few more weeks of gRPC stability) or explicitly gating
   behind an env flag so readers don't mistake it for live behaviour.

3. **Legacy `stream_tts_audio()` ElevenLabs path** in
   `voice_asterisk.py:346-439` is ~90 lines of code gated on
   `VOICE_TTS_PROVIDER=elevenlabs`, never hit since 16.04. Keeps
   `ffmpeg` dependency live. CLAUDE.md marks it as rollback-only;
   removal should wait at least until the gRPC migration window is
   over, but it should be re-evaluated in 2-3 weeks.

4. **Duplicated config lines in `core/pipeline.py`** — lines 32-40
   have each VOICE_* line appearing twice (probably a merge artefact).
   Harmless (`os.getenv` re-assignment), but looks unintentional.

5. **Default voice model drift between `.env` and code default** —
   `core/pipeline.py:34` says
   `"VOICE_MODEL_YANDEX", "gpt://…/yandexgpt-lite/latest"` but `.env`
   on VPS has `yandexgpt/latest` (Pro). Anyone reading code would
   assume Lite is production. Should either update the default or
   add a comment.
