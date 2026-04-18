# Noise-case Post-mortem — +79160322905 — 2026-04-18

Read-only analysis of 3 consecutive live-pilot calls to tester
`+79160322905`, all ending prematurely. Read from
`/var/log/sofia-voice/outbound_2026-04-18.jsonl` +
`/var/log/sofia-voice/transcripts/` + `journalctl -u sofia-voice`.

---

## 1. Identification

| # | UUID                         | ts_start (UTC)      | billsec | messages | disposition | user turns reached LLM |
|--:|------------------------------|---------------------|--------:|---------:|-------------|----------------------:|
| 1 | `bda28bd8-7f8e-48f1-833d-e925556f2364` | 10:39:09 | 36 | 9  | ANSWERED | 4 |
| 2 | `f8d41815-737f-4d05-b244-d20871411ccb` | 10:43:17 | 40 | 9  | ANSWERED | 4 |
| 3 | `c7fb25cb-6a1e-4ed1-a304-069ae327e045` | 12:15:58 | 37 | 5  | ANSWERED | 2 |

Source record: `grep '+79160322905' /var/log/sofia-voice/outbound_2026-04-18.jsonl`.

All three within normal call duration range (36-40 s). All ANSWERED —
the tester picked up each time.

---

## 2. Per-call timeline analysis

### Call 1 — `bda28bd8` (36 s billsec, 4 turns)

**Transcript:**
```
[00:16] SOFIA: Алло, здравствуйте! У меня для вас важная новость...
[00:32] USER: да интересно                             ← text_len=12
[00:33] SOFIA: Отель находится... Продолжаю?
[00:39] USER: да да                                    ← text_len=5
[00:40] SOFIA: Это апарт-отель в Белокурихе... Есть рассрочка... Подходит такой формат?
[00:43] USER: да                                       ← text_len=2
[00:43] SOFIA: Отправить вам подробности?
[00:50] USER: не надо але але какая такая я скажу тебе неудобно   ← text_len=49 ⚠
[00:51] SOFIA: Поняла, не буду занимать. Хорошего дня!
```

**AUTO_HANGUP events:**
```
10:40:01.909 AUTO_HANGUP detect uuid=bda28bd8… reason=state
10:40:03.419 AUTO_HANGUP exec   uuid=bda28bd8… after_delay=1.5s
```

**EOU_WAIT:** turn 0=1024, 2=762, 4=1420, 6=781, 8=1024, 10=1429 ms
(all within normal Phase 1 range, no anomalies).

**No HALLUC_TRUNCATED on turn 10.** No pipeline errors.

**Analysis:** User's reply contained two unambiguous refusal signals
("не надо", "неудобно") mixed with filler ("але але какая такая").
Sofia correctly mapped to the "Категорический отказ" branch of the
prompt and emitted the farewell. `reason=state` = LLM appended `[END]`
to the farewell (this is what the prompt asks for). Auto-hangup fired
1.5 s later. **Behaviour correct per prompt** — call ended because
user said "не надо".

---

### Call 2 — `f8d41815` (40 s billsec, 4 turns)

**Transcript:**
```
[00:10] SOFIA: Алло, здравствуйте!...
[00:25] USER: почва растет да хочу                               ← text_len=20 (bg speech + "да хочу")
[00:26] SOFIA: Поняла, продолжайте. Это апарт-отель... Дальше?
[00:37] USER: там на брусчатку накладывали другие какие то камни
              потом асфальт появился потом асфальт перекладывают нос ← text_len=105 ⚠⚠
[00:38] SOFIA: Простите, плохо слышно, можете повторить?
[00:44] USER: да хочу узнать подробнее                           ← text_len=24
[00:44] SOFIA: Хорошо, застройщик на рынке тридцать лет... Хотите посмотреть цифры?
[00:49] USER: это вот теперь не с вами говорить                  ← text_len=33 ⚠
[00:49] SOFIA: Поняла, не буду занимать. Хорошего дня!
```

**AUTO_HANGUP events:**
```
10:44:08.159 AUTO_HANGUP detect uuid=f8d41815… reason=state
10:44:09.668 AUTO_HANGUP exec   uuid=f8d41815… after_delay=1.5s
```

**EOU_WAIT:** 635, 520, 926, 411, 1035, 790 ms — notably lower than
typical (short bursts). Yandex EOU correctly fires on pauses between
user's short utterances even as they're really talking to someone
else intermittently.

**No HALLUC_TRUNCATED.** No pipeline errors.

**Analysis:** User (tester) was **in a noisy environment and
intermittently talking to another person in the room**. STT captured
that faithfully. On the 105-char turn Sofia correctly asked "повторите",
giving the user a chance to return to conversation. On the next turn
user's "это вот теперь не с вами говорить" (literal: "now I'm not
talking to you") Sofia interpreted as a refusal — technically ambiguous
("not with you" could mean "not talking to YOU specifically [because
I'm talking to someone else]" OR "I don't want to talk to you").
Sofia chose the refusal interpretation, emitted farewell + [END],
auto-hangup fired. **This is the interesting case** — not a clear
refusal, but a noise/context confusion.

---

### Call 3 — `c7fb25cb` (37 s billsec, 2 turns)

**Transcript (full — call ended here):**
```
[00:08] SOFIA: Алло, здравствуйте!...
[00:24] USER: да я хочу узнать подробности
[00:25] SOFIA: Отель находится... Дальше?
[00:36] USER: дальше
[00:37] SOFIA: Это апарт-отель в Белокурихе... Рассказать про условия оплаты?
   (no further turns — call ended)
```

**AUTO_HANGUP events:** **NONE** — no `detect`, no `exec`, no `cancel`.

**Connection lifecycle (log):**
```
12:16:45.055 📞 Connection closed (uuid=c7fb25cb…)
12:16:45.055 📞 Call ended: uuid=c7fb25cb…, duration=37.9s
```

`Connection closed` (not `Connection reset`) = Asterisk sending
us the hangup notification. **The tester hung up from their side,
not Sofia.**

**Analysis:** Totally different category. Sofia asked "Рассказать
про условия оплаты?" and the user simply hung up instead of replying.
No Sofia malfunction, no auto-hangup, no [END]. This is attrition /
user disengagement — a real-world cold-call outcome not related to
the other two calls.

---

## 3. Common patterns

Across all 3 calls — **common only at a high level:**
- All 3 tester calls to the same number in a short window (~100 min).
- All 3 reached LLM pipeline correctly (no infra issues).
- All 3 EOU_WAIT, TTS, gRPC streams behaved normally per Phase 1 baseline.

Patterns **specific to calls 1 and 2** (Sofia-initiated closes):
1. Both ended via the "Категорический отказ" branch → farewell
   "Поняла, не буду занимать. Хорошего дня!".
2. Both triggered `AUTO_HANGUP detect reason=state` — meaning LLM
   appended `[END]` to the farewell (as the prompt instructs for
   conversation end).
3. In both, the last user turn contained at least one textual cue
   the LLM could map to refusal:
   - call 1: "не надо", "неудобно" (genuine refusal signal)
   - call 2: "не с вами говорить" (ambiguous — "not with you" can
     mean different things)

**Call 3 shares no pattern with 1-2** — user-initiated hangup, no
Sofia closure code ran.

---

## 4. Root cause

**Sergey's hypothesis — "noisy environment" — is CONFIRMED with
nuance:**

- **STT is working correctly.** It transcribes what it hears,
  including background conversation. No sign of STT hallucinating
  phantom text — the inputs to LLM are faithful renderings of the
  audio.
- **LLM is the closure trigger.** When user input contains refusal-
  adjacent phrases ("не надо"/"не с вами"), LLM maps to the
  "Категорический отказ" prompt branch and emits
  `Поняла, не буду занимать. Хорошего дня! [END]`.
- **Auto-hangup is NOT faulty.** `reason=state` on both calls means
  the `[END]` marker came from the LLM at the true end of the
  farewell response (post hallucination filter — which ran clean,
  no truncations logged for these turns). This is the intended
  design: Sofia signals end-of-dialog → auto-hangup honours that.
- **Absent auto-hangup, the outcome is the same.** Sofia would
  still emit the farewell, the pipeline would stop responding to
  further client audio (Sofia has no more to say), client would
  experience 5-10 s dead air and hang up. Auto-hangup just
  accelerates the inevitable.

**The real root cause:** **Sofia's prompt is too eager to enter
the refusal branch on ambiguous user input.** Call 2 is the textbook
example: "это вот теперь не с вами говорить" is NOT a categorical
refusal of the offer — it's an admission that the user is multitasking
(talking to someone physically present) — but Sofia maps it to
refusal. Call 1 is borderline ("не надо" is genuinely close to
refusal; arguably correct behaviour).

**Call 3 is unrelated** — organic cold-call attrition, no prompt fix
would address it.

Evidence trail for root cause (call 2):
- `journalctl :10:43:55` — USER turn 6 text_len=105 — tester narrating
  unrelated street-repair topic (clearly bg conversation)
- `journalctl :10:44:02` — USER turn 8 text_len=24 "да хочу узнать подробнее"
  (tester returned to call)
- `journalctl :10:44:07` — USER turn 10 text_len=33 "это вот теперь не с вами говорить"
- `journalctl :10:44:08.159` — `AUTO_HANGUP detect reason=state`
- No `HALLUC_TRUNCATED` on this turn → LLM emitted clean farewell with
  `[END]` based on what it read.

---

## 5. Fix options

### Option A — Prompt hardening: stricter refusal criteria (RECOMMENDED)

**Change:** In `VOICE_SYSTEM_PROMPT_RIZALTA`, tighten the "Категорический
отказ" branch. Require BOTH:
  (i) the user's utterance contains an explicit refusal lexeme (нет, не
  интересно, не звоните, не надо, спасибо не надо), AND
  (ii) this is either the first explicit refusal OR the conversation
  has had multiple "повторите" / "плохо слышно" turns (sustained
  misunderstanding).

On ambiguous input (unclear intent, off-topic narrative, noise-adjacent
text), default to "Простите, плохо слышно, повторите?" — **not**
refusal branch.

**Reuse existing pattern.** Atlantis prompt already says
`[END] ставь только когда ... дважды чётко отказался` — apply the
same two-refusal guard to RIZALTA.

**Gain:** eliminates call-2-type false refusals on noise/context confusion.
Gives tester (and real cold users in noisy places) a second chance to
clarify.

**Effort:** ~2 h — edit RIZALTA prompt in `core/pipeline.py` (single
section), run 2-3 live-tests in noisy/quiet conditions, verify
"Поняла, не буду занимать" fires only on explicit refusals.

**Risk:** low-medium. Downside: on rare cases where user unambiguously
refuses and wants fast goodbye, Sofia might ask "повторите" once
before closing. Acceptable UX cost — ~1-2 s added on clear-refusal
path, no impact on happy path.

**Precondition:** none.

### Option B — Disable AUTO_HANGUP during pilot

**Change:** `sed` on `.env` → `AUTO_HANGUP_ENABLED=false` + restart.

**Gain:** zero. Sofia would still emit "Поняла, не буду занимать" and
stop responding; client gets 5-10 s dead air, then hangs up manually.
Calls still "end prematurely" from user perspective — longer dead air,
same conclusion.

**Effort:** ~30 s env switch.

**Risk:** LOW but **wrong direction** — masks the real issue with
worse UX. Restores the dead-air problem auto-hangup was built to solve.

**Precondition:** none.

**Why not recommended:** treats a symptom, not the cause.

### Option C — Add confidence checkpoint on refusal detection (PROMPT-level)

**Change:** Same as A but more elaborate — ask Sofia to explicitly
output a confidence signal before closing. E.g. first time user
seems negative, Sofia says "Чтобы уточнить — вам интересно или сейчас
неудобно?"; only close on the next turn if still clearly refusing.

**Gain:** same as A but with one extra exchange. Maximally
conservative.

**Effort:** ~4 h — more prompt engineering, more regression testing.

**Risk:** medium. Extra turn might feel pushy to users who DO want
to end. Dialogue length grows.

**Precondition:** none.

### Option D — Accept as cold-call attrition

**Change:** none; document current behaviour; monitor rate on larger
sample.

**Gain:** 0.

**Effort:** 0.

**Risk:** expected cold-base attrition rate might be ~20 % on
legitimate refusals + noise-confused cases combined; this is
industry-normal. But call 2 type (misinterpreted "talking to
someone else") is a solvable loss.

**Why not recommended:** at least one of the 3 calls (call 2) is
solvable with prompt tuning (Option A). Leaving it unfixed is
leaving money on the table.

---

## 6. Recommendation

### Right now (no code changes)

**Safe to continue pilot with other testers** — current behaviour
on the 3 calls is not a technical bug:
- 1/3 calls (bda28bd8) was a legitimate user refusal, handled correctly.
- 1/3 calls (c7fb25cb) was client-initiated hangup, totally unrelated
  to Sofia.
- 1/3 calls (f8d41815) had LLM over-eagerly entering refusal branch
  on ambiguous input (not a crash, not a timing bug, not a data leak
  — just a prompt-level sensitivity).

No regression has been introduced today. AUTO_HANGUP / END handler
fix / EOU instrumentation all working as designed. The issue existed
before today's changes — it's just become visible as pilot expanded
to noisier testers.

**Continue pilot. Expect ~20-30 % drop rate on noisy-environment
cold users** (industry normal). Collect 10-15 more samples before
deciding whether prompt tuning is urgent.

### Next sprint (if drop rate warrants)

Option A (prompt hardening, 2 h). One focused RIZALTA prompt edit
adding the explicit-refusal-lexeme + sustained-misunderstanding guard
for entering the "Категорический отказ" branch. Live-test on noisy
vs. clean conditions to confirm.

### Not recommended

- Option B (disable AUTO_HANGUP): worsens UX, doesn't solve anything.
- Option C (explicit confidence prompt): over-engineering for
  marginal gain.

### Immediate signal for Sergey

Keep `AUTO_HANGUP_ENABLED=true`. If the next 5 pilot calls repeat
the call-2 pattern (Sofia saying "Поняла, не буду занимать" after
ambiguous user turn with no explicit refusal lexeme) → schedule
Option A sprint. If calls fail for other reasons (user hangups,
STT blanks, pipeline errors), those need separate analysis.

---

## Side observations

1. **`reason=state` in AUTO_HANGUP detect is the prevalent signal,
   not `reason=keyword`**. On both triggered calls it's `state` —
   meaning Sofia's LLM is reliably appending `[END]` to farewell
   utterances per the new prompt instruction. The keyword fallback
   (checking last 80 chars for "хорошего дня" etc.) hasn't been
   needed yet on these 3 calls. Good — primary detection path working.

2. **EOU_WAIT on call 2 was unusually short (411 ms, 520 ms, 635 ms)** —
   likely because tester's utterances were often short bursts with
   long silence between them (inherent to multitasking). Yandex EOU
   correctly caught each burst end. Not a bug, just a characteristic
   of noisy environments.

3. **Turn count 4/4/2 across the three calls is instructive**: Sofia
   gets through 3-4 exchanges even with noisy input before the LLM
   decides to close. Not a premature-first-turn closure pattern.

4. **Call 3 `Connection closed` vs calls 1-2 `Connection reset`** —
   useful distinction in logs: `closed` = client-initiated, `reset` =
   our-side-initiated (auto-hangup). Already a debug-friendly signal;
   could be formalized in a dashboard.
