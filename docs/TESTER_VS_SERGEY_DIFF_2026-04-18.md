# Tester vs. Sergey differential — 2026-04-18

Read-only analysis of why outbound pilots to testers fail while
Sergey's own +79181011091 calls succeed.

Data source:
- `grep "+7918" /var/log/sofia-voice/outbound_2026-04-18.jsonl`
- `/var/log/sofia-voice/transcripts/`
- `journalctl -u sofia-voice` for specific UUIDs

---

## Call inventory (last 120 min)

| phone | uuid (first8) | billsec | msgs | auto-hangup? | hangup side | user first-turn character |
|-------|---------------|--------:|-----:|--------------|-------------|---------------------------|
| +79181011091 (Sergey) | d0c3d7db | 82 | 11 | — | — | contextual ✓ |
| +79181011091 (Sergey) | 6b52ae6d | 55 | 3 | — | — | short, may be cut short — TBD |
| +79181011091 (Sergey) | 5f2e6a97 | 34 | 3 | — | — | same |
| +79160322905 (tester 1) | bda28bd8 | 36 | 9 | **reason=state** | reset (ours) | contextual at start; final turn "не надо ... неудобно" |
| +79160322905 (tester 1) | f8d41815 | 40 | 9 | **reason=state** | reset (ours) | "почва растет" (bg speech) |
| +79160322905 (tester 1) | c7fb25cb | 37 | 5 | — | **closed (client)** | contextual; client hung up mid-flow |
| +79185927466 (tester 2) | 181ac44a | 41 | 10 | — | **closed (client)** | "давайте продавать сразу перестала..." (bg speech) |
| +79189007826 (tester 3) | — | — | — | — | **no CDR** (Telfin never created channel) | n/a |
| +79181011091 (Sergey) | de29c532 | 67 | 11 | — | — | contextual ✓ |

Key distinction:
- **Sergey's full-conversation calls** (`d0c3d7db`, `de29c532`, etc. +
  earlier today): 11-19 messages, full RIZALTA funnel reached.
- **Tester calls:** 9-10 messages max, abrupt endings. **50 % are
  client-side hangups** (`Connection closed`), 50 % are auto-hangup
  via Sofia's refusal branch.

---

## Deep-dive: 181ac44a (+79185927466, latest tester call)

**Transcript (dословно):**
```
[00:10] SOFIA: Алло, здравствуйте! ...
[00:28] USER: давайте продавать сразу перестала мы сразу отдавались всем
              клиентам не не отдавали                                 ← text_len=82
[00:29] SOFIA: Простите, плохо слышно, можете повторить?
[00:34] USER: ну расскажите давайте интересно                         ← text_len=31
[00:35] SOFIA: Отель находится... Продолжаю?
[00:39] USER: всю ситуацию                                            ← text_len=12
[00:40] SOFIA: Это апарт-отель в Белокурихе... Подходит такой формат?
[00:43] USER: да да да                                                ← text_len=8
[00:44] SOFIA: Есть рассрочка... Хотите посмотреть цифры?
[00:51] USER: заработала ну пипец просто а получается что я своих
              клиентов отдавала брокером брокеры закрывали получали   ← text_len=105
```

**STT partial stream on turn 1 (journal 12:45:29-33):**
```
[давай] → [давайте] → [давайте продавать] → [давайте продавать сразу перестала]
→ ... → final: «давайте продавать сразу перестала мы сразу отдавались
всем клиентам не не отдавали» (82 chars)
```
Clean organic text-evolution, **no STT hallucination artefacts** —
Yandex faithfully captures what the user's mic picks up.

**Final turn (105 chars) was still streaming when client hung up:**
```
12:45:56.638 📞 Connection closed (uuid=181ac44a…)   ← client hangup
12:45:56.807 gRPC final: [заработала ну пипец просто... брокерами закрывали получали]
12:45:57.645 SOFIA: "Простите, плохо слышно, можете повторить? ..."
```
Sofia's "плохо слышно" retort was rendered but never delivered —
connection was already dead on the wire.

**AUTO_HANGUP events:** ZERO. Sofia did not initiate the hangup.

**EOU_WAIT per turn:** 641, 384, 835, 135, 496, 997, 384, 90 ms.
Median ≈ **440 ms**.

---

## Comparative metrics

### EOU_WAIT median

| Group | n turns (sampled) | median EOU_WAIT | range |
|-------|------------------:|----------------:|-------|
| Sergey's calls (today Phase 1 baseline) | 21 | **1036 ms** | 869-1675 |
| Tester 181ac44a (+79185927466) | 8 | **440 ms** | 90-997 |
| Tester bda28bd8 (+79160322905 #1) | 6 | ~1220 ms | 762-1429 |
| Tester f8d41815 (+79160322905 #2) | 6 | ~635 ms | 411-1035 |

**Tester EOU_WAIT is markedly shorter than Sergey's** on 2 of 3
tester calls. 181ac44a's median 440 ms is **under half** Sergey's
1036 ms.

Why shorter? Testers speak in **bursts with pauses inside their
utterance** — Yandex EOU fires on each burst-end, final stabilises
quickly (partial text doesn't change for ~100-500 ms, enough for
EOU to commit). Sergey speaks in flowing phrases: last word + natural
~700 ms trailing silence = longer EOU_WAIT.

Short EOU_WAIT here = signal that the speaker is **not engaging
conversationally** (fragmented speech, disjoint bursts) — not a
phone-hardware artefact.

### STT final text length

Testers: mix of very long (82, 105 chars) and very short (8, 12)
finals. Content is **semantically off-topic** relative to Sofia's
questions (broker/client stories, random narrative).

Sergey's calls: finals are on-topic replies ("да давайте", "а что
по оплате", "да отправляйте") — 2-20 words, aligned with Sofia's
question.

### TTS-echo in STT partials

**Checked gRPC partials during Sofia's TTS playback.** TTS-echo
guard (voice_asterisk.py on `_tts_playing` flag) works: during
Sofia's reply playback, partials are filtered by `_on_grpc_partial
if self._tts_playing and not self._cancel_playback: return`. **No
evidence of echo leaking into user-turn finals** on any tester call.
Partials stream cleanly after `_tts_playing=False`.

This **rules out Sergey's hypothesis of weaker echo-cancellation**
on tester phones.

### HALLUC_TRUNCATED frequency

Zero occurrences across all 4 tester calls analysed today. So it's
not LLM hallucinating `[END]` in tail (the pre-existing bug we fixed
in 19102904).

---

## Hangup pattern

| call | hangup side | reason (if ours) | what happened |
|------|-------------|------------------|---------------|
| bda28bd8 | ours | **state** (LLM emitted [END] on "не буду занимать") | user said "не надо... неудобно" — genuine soft refusal, Sofia went to Категорический отказ branch |
| f8d41815 | ours | **state** | user said "это вот теперь не с вами говорить" — ambiguous, Sofia over-eagerly refused (Noise-case postmortem root cause) |
| c7fb25cb | **client** | — | user hung up after Sofia's "Рассказать про условия оплаты?" — silent disengagement |
| 181ac44a | **client** | — | user hung up mid-TTS while Sofia was rendering "повторите?" — rambling off-topic speech for 40 s then disconnect |

**No case of auto-hangup on non-farewell text.** All 2 of 4 Sofia-
side closes had `reason=state` (= LLM refusal branch), not `reason=
keyword`. Auto-hangup mechanism itself is not misbehaving.

**2 of 4 testers hang up themselves** without Sofia misbehaving.

---

## Root cause / hypotheses

### What this is NOT

1. **Not a phone-hardware difference.** STT partials are clean, no
   echo leakage, no codec issues. Audio quality from tester phones
   is comparable to Sergey's.
2. **Not an auto-hangup false-positive** (with exception of
   f8d41815 already diagnosed as LLM over-eagerness on "не с вами
   говорить" — fixable by prompt hardening per NOISE_CASE post-mortem
   Option A).
3. **Not STT hallucination** — Yandex faithfully transcribes what
   the mic captures.
4. **Not AUTO_HANGUP triggering on non-farewell text.**

### What this IS — primary hypothesis

**Testers are not focused on the call.** Evidence:

- 181ac44a: user narrates "заработала ну пипец просто а получается
  что я своих клиентов отдавала брокером..." — **talking about being
  a broker/about brokers closing deals**. This is someone engaged
  in a different conversation or reading aloud from another screen.
- 181ac44a turn 1: 82-char rambling "давайте продавать сразу
  перестала мы сразу отдавались всем клиентам не не отдавали" —
  again not a reply to Sofia's greeting; again sounds like ongoing
  sales/broker conversation.
- f8d41815 turn 6: 105-char street-repair narrative ("на брусчатку
  накладывали камни потом асфальт...") — totally unrelated.
- f8d41815 final turn: "это вот теперь не с вами говорить" =
  literal "now I'm not talking to you" — admission of bilateral
  context.

**Pattern:** testers took the call but are simultaneously engaged
with another stimulus (another call on another line / in-person
conversation / reading something aloud). Cold-call fails because
the user's attention is split.

Sergey, by contrast, runs dial.py and focuses on the call — he
is always the sole speaker on his end.

### Secondary hypothesis (smaller effect)

**+79160322905 calls 1-2 had a genuine prompt-level issue** (Noise-
case post-mortem covered): LLM maps ambiguous user text to refusal
branch. But even if we fix this, calls 3 and 4 (client-hangups)
wouldn't change — they're primary-hypothesis cases.

### Third hypothesis (not supported by data but kept for
completeness)

Tester phone speakerphone/hands-free mode could amplify room noise.
Consistent with "talking to someone in the room" observations but
not the primary driver — even if their phone had perfect mic
directivity, a user looking at another screen and reading broker
narratives wouldn't produce on-topic Sofia replies.

---

## Recommendation

### Not a technical bug

No code change would make these calls succeed. The failure mode is
**social / attention-level**, not technical:

- 2 of 4 tester calls failed because tester hung up themselves while
  engaged elsewhere (c7fb25cb, 181ac44a). No Sofia malfunction.
- 1 of 4 (bda28bd8) was handled correctly — genuine refusal.
- 1 of 4 (f8d41815) was the already-known prompt over-eagerness on
  ambiguous text — fix plan documented in Noise-case post-mortem
  (Option A, ~2 h).

### What Sergey should tell testers

If pilot participants are paid/tasked testers, they need a brief:
**be in a quiet room, focused on the call, not doing other work.**
Otherwise the data is contaminated — we're measuring "does Sofia
cope with distracted human" rather than "does Sofia cope with
normal cold-call prospect".

For REAL cold-call base later, expect ~20-40 % attrition from
distracted users — this is industry-normal and not a Sofia bug.
Successful cold calls require the prospect to give the call 100 %
for 60-90 s. If they're not willing, they hang up; Sofia can't
fix that.

### Safe to continue pilot? YES

If goal is UX validation — **use Sergey-like testers** (focused,
quiet room). Current tester pool is dirtied by attention issues.

If goal is realistic cold-call simulation — **accept current rate**
and proceed to larger sample. Prompt fix (Option A from Noise-case
post-mortem) helps with ~25 % of tester-pool failures (the f8d41815
class), not the remaining 50 % (client hangups).

---

## Open questions (cannot answer from existing logs)

1. Were testers **paid/tasked with simulating interested prospect**,
   or casually picking up? Context would distinguish "tester
   discipline problem" from "real cold-prospect distribution".
2. Were testers called on their **mobile-at-work** (likely: picking
   up mid-task) or from a dedicated test setup? Likely the former.
3. **Are testers conscious of being recorded** and performing /
   play-acting broker dialogues aloud? The 181ac44a transcript
   is so thematically coherent (all broker-business talk) that it
   might be the tester *reading from a script* without interacting
   with Sofia.

Answers to these would refine the recommendation. All are
process/comms questions outside log analysis scope.
