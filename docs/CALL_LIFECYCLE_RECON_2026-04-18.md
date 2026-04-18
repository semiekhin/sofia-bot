# Call Lifecycle Reconnaissance — 18.04.2026

Read-only recon of two operational gaps before RIZALTA live cold-call
series: (A) ringing timeout, (B) auto-hangup after Sofia's farewell.
No code changes. Implementation deferred to separate sprints.

---

## ЗАДАЧА A — Ringing timeout

### Current state

`dial.py` originates via:

```
channel originate PJSIP/<phone>@telphin-endpoint
  extension s@outbound-audiosocket
```

(`dial.py` line with `originate_cmd` — calls `asterisk -rx` to run the CLI.)

Evidence for **default 30s ringing timeout**: `asterisk -rx "help channel
originate"` returns verbatim:

> "Calls originated with this command are given a timeout of 30 seconds."

The CLI form `channel originate … extension <exten>@<ctx>` **does not
expose a timeout parameter** — the 30s is hard-coded in Asterisk 20's
CLI implementation.

No `Dial()` app is involved on the outbound leg: `[outbound-audiosocket]`
context (`/etc/asterisk/extensions.conf:20-22`) only runs **after
answer** — AudioSocket app directly, no Dial timeout to tune.

No timeout-related tuning in `pjsip.conf` affects ring duration (session
timers govern keepalive, not ringing wait).

### Current CDR distribution

```
jq / grep on /var/log/sofia-voice/outbound_2026-04-18.jsonl
→ 13 ANSWERED, 1 FAILED, 0 NO ANSWER
```

All 14 outbound calls made today were to Sergey's own phone — he
answered every one. **The 30s default has never actually been hit.**
Impact of reducing timeout is hypothetical until real cold base is
dialled.

### Parameters and their levels of control

| Lever | Level | Current value | Changeable via |
|-------|-------|---------------|----------------|
| CLI `channel originate` timeout | Asterisk internal | 30s hard-coded | **Cannot — CLI limitation** |
| AMI `Originate` action `Timeout` field | Manager Interface | not used | Switch to AMI client |
| `.call` file `WaitTime:` header | Spool-based originate | not used | Switch to .call file approach |
| `Dial()` app timeout | Dialplan | N/A (no Dial() on outbound path) | — |

### Path forward

The simplest refactor to get a tunable ringing timeout is **switch
from `asterisk -rx "channel originate"` to a `.call` file** written
atomically into `/var/spool/asterisk/outgoing/`.

Verified prerequisites:
- `/var/spool/asterisk/outgoing/` exists, writable (`ls -la` confirmed)
- AMI is also enabled (`manager.conf` `enabled=yes`, `port=5038`,
  listening on `127.0.0.1:5038`) — alternative path

Example `.call` file content (what dial.py would write):

```
Channel: PJSIP/<phone>@telphin-endpoint
WaitTime: 20
MaxRetries: 0
RetryTime: 1
Context: outbound-audiosocket
Extension: s
Priority: 1
CallerID: <optional>
```

`WaitTime: 20` means 20s ringing cap.

### Recommended value: **20 seconds**

Rationale:
- Industry standard for cold-calling is 4-5 rings (20-25s) per major
  telco guidelines and Telfin's own docs.
- Russian PSTN typical ring cadence is ~4s on / 2s off → 20s ≈ 3-4 rings.
- 30s → 20s on a cold base with 40% no-answer rate saves ~10s per
  no-answer call; on a 1000-call batch that's ~67 minutes saved
  (4000 s spent ringing vs 6000 s at 30s).

### Concrete edit site

`/opt/sofia-voice/dial.py` — current originate block:

```python
originate_cmd = (
    f"channel originate PJSIP/{phone}@telphin-endpoint "
    f"extension s@outbound-audiosocket"
)
# … run_asterisk_cli(originate_cmd, timeout=ORIGINATE_CMD_TIMEOUT)
```

Would be replaced with a function `write_call_file(phone)` that:
1. Writes `.call` content to `/tmp/<uuid>.call`.
2. `os.rename("/tmp/<uuid>.call", "/var/spool/asterisk/outgoing/<uuid>.call")`
   — atomic, race-safe.
3. Asterisk picks up the file, processes it. CDR polling infrastructure
   below `run_asterisk_cli` stays unchanged.

**No dialplan change needed.** `[outbound-audiosocket]` context is
triggered as before when the outbound leg answers.

### Effort estimate (Task A)

| Step | Hours |
|------|------:|
| Replace `asterisk -rx` path with `.call` file writer | 2 |
| Keep CDR-uniqueid matcher intact (call file CDR vs CLI CDR differ slightly — CDR.src may differ) | 1 |
| Live-test with a non-answering number (one call to verify 20s) | 1 |
| Fix regressions in uniqueid capture (fallback matcher may need adjustment) | 1-2 |
| **Total** | **5-6 h** |

### Rollback (Task A)

L0 (instant): env-gated dispatch — keep old `asterisk -rx` path behind
`DIAL_MODE=cli` env flag, new `DIAL_MODE=callfile` (default). Switch
back via env.

L1 (git): `git revert` the commit.

---

## ЗАДАЧА B — Auto-hangup после Sofia farewell

### Current dead-air evidence

Billsec vs duration gap across today's successful calls:

| UUID | billsec | duration | dead air |
|------|--------:|---------:|---------:|
| 5600c4af | 74 | 81 | **7 s** |
| b858cbe0 | 107 | 112 | **5 s** |
| 8fa66bb2 | 111 | 116 | **5 s** |
| 0ae0b897 | 106 | 116 | **10 s** |
| f882e6b2 | 118 | 125 | **7 s** |

Dead air median ≈ **7s**, range 5-10s. Transcripts confirm — final line
is always Sofia's farewell phrase, client does not respond.

### AudioSocket hangup mechanism

**Two viable Python-side mechanisms:**

1. **Send AS_TYPE_HANGUP frame (0x00)** — protocol-level hangup
   request. Frame wire format (per `voice_asterisk.py:8-11` protocol
   comment and the existing decoder at `:620-626`):
   ```
   [1 byte type=0x00] [2 bytes length=0x0000] [0 bytes payload]
   ```
   Equivalent to: `writer.write(struct.pack(">BH", 0x00, 0))`.
   Asterisk's `app_audiosocket.c` accepts this and terminates the
   channel.

2. **Close TCP writer** — existing path at `voice_asterisk.py:1144-1145`:
   `self.writer.close(); await self.writer.wait_closed()`. Asterisk
   sees EOF and hangs up PJSIP leg. This is what `_cleanup()` already
   does at end-of-call.

Either works. Path (1) is the documented protocol way; path (2) is
already used by the cleanup code. **Recommend path (1) for intent
clarity** — a close() could be misread as "network error", while
a 0x00 frame is unambiguous "we're done".

Evidence: `voice_asterisk.py:7-11`:
```
Asterisk AudioSocket protocol (TCP):
  Packet: [1 byte type] [2 bytes length BE] [payload]
  Types:  0x00=hangup, 0x01=UUID(16 bytes binary), 0x10=audio(slin 8kHz),
          0x12=audio(slin 16kHz), 0xFF=error
```
(The protocol is bidirectional; types apply both directions per
AudioSocket spec.)

### Three detection approaches

| Approach | How it works | False-positive risk | Effort | Evidence |
|----------|--------------|----------------------|--------|----------|
| **A. Keyword match** | After `_speak()` completes, regex-check Sofia's text for farewell keywords: «хорошего дня», «всего доброго», «удачного дня», «удачной дороги», «хорошего вам дня» | Low-medium. Unlikely mid-call use, but LLM could say "хорошего дня" in rare defensive greeting contexts (cold-calling Sofia wouldn't, but safety-net needed). | ~3 h | Last 5 transcripts: 5/5 end with exactly one of these keywords. |
| **B. State-based (`dialog_finished`)** | voice_asterisk.py reads `state.dialog_finished` via `state_manager` after `_process_turn`. Currently set only via [END] marker mechanism in `core/pipeline.py:1053-1060`. | Very low (flag flips explicitly). Requires RIZALTA prompt to instruct Sofia to emit [END] after farewell — LLM adherence is the variable. | ~5 h | `core/pipeline.py:1053-1060` already strips [END] from voice output and sets `dialog_finished=True`. Infrastructure 80% ready — voice_asterisk.py just needs to read the flag. RIZALTA v4.1 prompt currently has no [END] instruction. |
| **C. LLM [END] marker** | Same as B but tightly coupled to pipeline-side [END] detection. Same prompt change, same voice_asterisk.py check — functionally B and C are the same thing. | Same as B. | Same as B. | Same as B. |

**Conclusion on A vs B/C:** B and C are the same mechanism (LLM emits
[END] → pipeline sets `dialog_finished` → voice_asterisk.py reads
flag). A is independent. **The safest and simplest path is
hybrid A+B** — either signal triggers hangup.

### Recommended approach: **hybrid A + B**

**Primary: keyword-match (A).** Immediate benefit without prompt change
risk. Keywords are stable Russian farewell phrases unlikely to appear
mid-call in a cold-sales script.

**Secondary: [END] marker (B) — next iteration.** Add `[END]` instruction
to RIZALTA prompt in the farewell section; voice_asterisk.py reads
`state.dialog_finished` as an OR-condition alongside the keyword match.
Strengthens detection without depending on it.

This ordering lets us ship the immediate win with A while B matures
(LLM adherence to [END] has to be observed over 5-10 live calls).

### Timing: **1500ms after last TTS chunk**

- 0ms would clip the tail of Sofia's last audio byte (Asterisk buffering
  ~20-40ms + SIP RTP jitter buffer ~40-80ms). Too abrupt.
- 1500ms gives:
  - Tail flush: ~150ms for last RTP packet to reach Telfin.
  - Polite pause: ~1000ms natural after-farewell silence (mimics human
    sales conversations).
  - Client retort window: ~350ms — if client says "до свидания" fast,
    they get some of it said before we cut. If they want a longer
    reply, they're cut off — **acceptable for cold calling**, Sergey
    explicitly wants faster hangup.
- Total dead air saved vs current 7s median: ~5.5s per successful call.

### Safety-net for false-positive

Three layers:

1. **Keyword regex scoped to END of Sofia's text** — only match if
   farewell phrase appears in last 80 chars of response. Prevents
   mid-sentence false match.
2. **Only trigger after funnel-stage is late** — proxy via state:
   if `state.dialog_finished` was NEVER written AND no messenger
   was selected in message history, do NOT hangup even on keyword.
   Protects against Sofia accidentally saying "хорошего дня" mid-call.
3. **If false-positive occurs anyway**: client can call back. Cold
   calls are one-shot anyway — a rare cut-off adds no UX cost beyond
   a missed close. The safety-net is "fail open = early hangup"
   which is always better than current "fail closed = 7s dead air".

### Concrete edit sites (Task B)

**`voice_asterisk.py` — in `_process_turn()` after `_speak(response)` completes:**

After the `self._turn_timings["tts_ms"] = ...` line (around
voice_asterisk.py:942), add a detect-and-hangup block:

```python
# VLAT-B (farewell detection):
# 1. check last 80 chars of response for farewell keywords
# 2. OR check state.dialog_finished (for future [END] support)
# 3. if match: wait 1500ms for TTS tail flush, send AS_TYPE_HANGUP, cleanup
```

**`core/pipeline.py` — RIZALTA prompt (optional, next iteration):**

Add to ЛОГИКА МЕССЕНДЖЕРОВ section: "В конце прощания добавляй [END]
как маркер завершения диалога" (or equivalent). LLM will start emitting
[END], `stream_voice_response` already strips it and sets
`dialog_finished`.

### Effort estimate (Task B)

| Step | Hours |
|------|------:|
| Implement keyword regex + tail-80-char scope | 1 |
| Implement `await asyncio.sleep(1.5)` + AS_TYPE_HANGUP frame send | 1 |
| Safety-net (messenger-selected check) | 1 |
| Live-test (1-2 calls of full RIZALTA flow, measure billsec reduction) | 1 |
| Fix regressions if any | 1 |
| **Total (A path only)** | **5 h** |
| + [END] prompt addition + state.dialog_finished reading | +1 |
| **Total (A+B hybrid)** | **6 h** |

### Rollback (Task B)

L0 (env switch): gate behind `VOICE_AUTO_HANGUP=on|off` env var
(default `on` after deploy). Setting `off` + restart reverts to current
client-hangs-up behavior. <30s.

L1 (git revert): one-commit revert.

---

## Общие находки

### Interaction between A and B

**Zero overlap.** Task A touches `dial.py` originate mechanism; Task B
touches `voice_asterisk.py` post-TTS turn handling. Different processes,
different files, different failure domains.

They can be done:
- **Sequentially** (A first, B second — or vice versa)
- **Parallel in the same sprint** (two commits in one session)
- **In separate sprints**

No coupling, no shared state.

### Interaction with Phase 1 (`hint=700ms`)

Task A: none. `hint=700ms` operates on EOU during the call; ringing
timeout operates before call answer. Orthogonal.

Task B: none. `hint=700ms` shortens EOU wait → faster turn → Sofia
reaches farewell faster. Task B cuts dead air AFTER farewell.
Compound benefit — Phase 1 cuts intra-turn latency, Task B cuts
end-of-call latency. Additive savings.

### Interaction with cached greeting

Zero. Greeting is first Sofia utterance; Task B triggers on last.

### Effect on Atlantis inbound channel

**Zero on Task A** — outbound dialer is not used for inbound.

**Near-zero on Task B**, with one caveat: the `voice_asterisk.py`
AudioSocket code is shared between inbound (`from-telphin`) and
outbound (`outbound-audiosocket`) — Task B's change in `_process_turn`
fires for both. Atlantis farewell phrases are different (e.g.
"Спасибо за разговор, хорошего дня!" from `core/pipeline.py:632`) and
contain the keyword "хорошего дня" — so auto-hangup would also fire
for Atlantis inbound. This is arguably desirable (same dead-air
problem exists there), but needs explicit call-out during Task B
implementation. If undesirable, gate on `voice_prompt_mode == "rizalta"`
or on a separate env.

### Potential side effects

1. **Task A `.call` file approach**: Asterisk writes CDR the same way
   regardless of originate mechanism. But `CDR.src` and `CDR.channel`
   may differ slightly — the uniqueid capture logic in
   `find_new_telphin_uniqueid` (`dial.py`) uses substring match on
   `telphin-endpoint`, which should still work. Worth verifying live.
2. **Task B 1500ms delay**: between Sofia's last audio byte and hangup.
   If the user calls again in that window, they get ringing on an
   already-live channel — harmless but monitor.
3. **Task B on Atlantis**: as noted above, fires there too unless
   gated. Default recommendation: gate on `VOICE_PROMPT_MODE=rizalta`
   to keep Atlantis inbound unchanged until its behaviour is
   separately verified.

---

## Decision matrix

### Sequence recommendation: **B first, then A**

Rationale:
- **Task B has immediate real-world impact.** Every ANSWERED call
  saves ~5.5s. With 14 ANSWERED calls today, that's ~77s saved
  retroactively. At scale (500 cold calls × 30% ANSWERED rate = 150
  calls × 5.5s = ~14 min saved per batch).
- **Task A has payoff only on NO ANSWER calls.** Current data: 0 NO
  ANSWER in 14 calls. Impact hypothetical until cold base is engaged.
- **B is lower-risk.** Keyword match is self-contained; worst case
  rollback is one env flag. Task A requires refactoring dial.py
  originate mechanism (call files), which touches CDR polling paths.
- **Either can go first without blocking the other.** If Sergey prefers
  to do them same-sprint, parallel is fine.

### Can they fit in one sprint?

**Yes, one sprint fits both.** Combined effort ~11h (6h Task B + 5h
Task A). Different files, different failure modes — no cognitive load
interference. Recommended breakdown:

- Phase 1: Task B (3-4h implementation + 1h test)
- Phase 2: Task A (3-4h implementation + 1h test)
- Total: ~8-10h in one full day of work.

Split to two sprints is also reasonable if Sergey wants to observe
Task B on live cold-calling before starting Task A (data-driven
refinement of the 20s ringing choice).

### Prerequisites

**For Task A:**
- Confirm `/var/spool/asterisk/outgoing/` is writable by the user
  running dial.py (it's `asterisk:asterisk`, owner-group; currently
  dial.py runs as root per `ps` so has permission). ✅ verified.
- AMI as backup path — `manager.conf` `enabled=yes`, port 5038
  listening. ✅ verified.

**For Task B:**
- Familiarity with AudioSocket protocol byte layout — already in
  `voice_asterisk.py:7-11` comment block.
- Decision on Atlantis scope — gate on `rizalta` only, or apply to
  both. **Recommend: gate on rizalta first**, then evaluate Atlantis
  separately.
- Verification that the current `state_manager` `get_state` call is
  cheap enough to invoke after each `_speak()` (it reads SQLite —
  should be ~1ms, but verify). If expensive, cache locally.

### Recommended sprint plan

Single sprint, in this order:

1. **Task B Phase 1 (keyword-match only, gated on RIZALTA)** — 3-4h,
   deploy, observe 5-10 live calls, measure billsec reduction.
2. **If Task B Phase 1 clean** (no false-positives, billsec drops to
   ~duration) → optionally add [END] marker as Phase 2 (1h) for
   stronger signal.
3. **Task A** — after Task B stabilised, refactor dial.py to `.call`
   files. 5-6h.

Total: ~10-12h across ~2 working days.

---

## Open questions (for experiment)

1. **`.call` file exact `WaitTime` unit semantics on Asterisk 20** —
   documented as seconds, but verify by writing a .call file with
   `WaitTime: 20` and observing actual ring duration.
2. **Does `app_audiosocket.c` accept client-initiated 0x00 frame as
   hangup?** Expected yes per protocol spec; verify by sending one
   and observing Asterisk `channel dump` behaviour. If not, fall back
   to `writer.close()`.
3. **LLM adherence rate to `[END]` marker** after prompt instruction —
   unknown on YandexGPT Pro for RIZALTA. Needs 5-10 live calls post-
   deploy to measure.
4. **Any Telfin-side ringing timeout** that might override Asterisk's
   20s? Unknown. If Telfin imposes 30s minimum, Asterisk's 20s just
   cancels earlier; otherwise Telfin's and Asterisk's interact.

---

## TL;DR priorities

- **Task B first** (~5h for keyword-match variant), saves ~5.5s per
  ANSWERED call immediately.
- **Task A after** (~5h for `.call` file refactor), saves ~10s per
  NO ANSWER call — impact scales with cold-base volume.
- **One sprint** (~10-12h total) handles both.
- **Zero interaction** between the two — no sequencing constraint
  beyond impact timing.
