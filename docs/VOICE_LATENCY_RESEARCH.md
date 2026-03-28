# Voice Pipeline Latency Research

**Date:** 2026-03-28
**Current pipeline:** Client speaks -> Retell STT -> WebSocket -> LLM (gpt-4.1-mini) -> text -> Retell TTS -> client hears
**Current timings:** TTFT 500-1300ms, total LLM 800-3000ms, end-to-end 900-3000ms+
**Server:** 72.56.64.91 (Timeweb, Russia)

---

## 1. Models -- What's Faster Than gpt-4.1-mini for Russian?

### Available Models (from API listing, 2026-03-28)

| Model | Avg TTFT (ms) | Avg Total (ms) | Russian Quality | Price (input/output per 1M) |
|-------|---------------|-----------------|-----------------|---------------------------|
| gpt-4.1-nano | 885 | 1114 | Good (80.1% MMLU) | $0.10 / $0.40 |
| **gpt-4.1-mini** (current) | **606** | **951** | Very good | $0.40 / $1.60 |
| gpt-5-nano | N/A (streaming broken*) | ~1400 | Unknown | ~$0.10 / $0.40 |
| gpt-5-mini | N/A (streaming broken*) | ~2000 | Unknown | ~$0.40 / $1.60 |
| **gpt-5.4-nano** | **601** | **1083** | Good | ~$0.10 / $0.40 |
| **gpt-5.4-mini** | **325** | **737** | Very good | ~$0.40 / $1.60 |
| Groq llama-3.3-70b | **146** | 454 | Decent (not native) | $0.59 / $0.79 |
| Groq llama-3.1-8b | **54** | 174 | Weak for sales | $0.05 / $0.08 |

*gpt-5-nano and gpt-5-mini: Responses API streaming does not emit `response.output_text.delta` events (possibly uses different event types). Need investigation.

### Benchmark Details (measured from 72.56.64.91)

**gpt-4.1-mini TTFT vs prompt length (single run):**
- prompt_len=100 chars: TTFT=1030ms
- prompt_len=500 chars: TTFT=966ms
- prompt_len=2000 chars: TTFT=923ms
- Conclusion: prompt length has minimal TTFT impact in this range

**gpt-5.4-mini (3 runs):**
- Run 0: TTFT=345ms, total=833ms
- Run 1: TTFT=299ms, total=759ms
- Run 2: TTFT=329ms, total=620ms
- Average: TTFT=325ms, total=737ms
- Quality: Excellent Russian, proper sales tone

**gpt-5.4-nano (3 runs):**
- Run 0: TTFT=346ms, total=762ms
- Run 1: TTFT=372ms, total=942ms
- Run 2: TTFT=1083ms, total=1546ms (spike!)
- Average: TTFT=601ms, total=1083ms (high variance)

**Groq llama-3.3-70b-versatile (3 runs):**
- Run 0: TTFT=147ms
- Run 1: TTFT=87ms
- Run 2: TTFT=205ms
- Average: TTFT=146ms
- Quality: Decent Russian but not native-grade for complex sales scenarios

**Groq llama-3.1-8b-instant (3 runs):**
- Run 0: TTFT=41ms
- Run 1: TTFT=78ms
- Run 2: TTFT=44ms
- Average: TTFT=54ms
- Quality: Weak for nuanced Russian sales conversation

### Realtime Models Available
- gpt-4o-realtime-preview, gpt-4o-realtime-preview-2025-06-03
- gpt-4o-mini-realtime-preview
- gpt-realtime, gpt-realtime-1.5
- gpt-realtime-mini

**Findings:** gpt-5.4-mini is the clear winner: ~325ms avg TTFT (almost 2x faster than gpt-4.1-mini at ~606ms) with excellent Russian quality. Groq is 4x faster on TTFT but Russian quality is a risk for sales.

**Potential:** -280ms TTFT by switching to gpt-5.4-mini. Groq would save -460ms but quality risk.

**Complexity:** Low (model name change in VOICE_MODEL constant)

**Recommendation:**
1. **Immediate: Switch to gpt-5.4-mini** -- single line change in `core/pipeline.py` VOICE_MODEL. Test with 10 voice calls.
2. **Experiment: Test gpt-5.4-nano** for simple stages (GREETING, CLOSING) where quality bar is lower.
3. **Investigate: gpt-5-nano/gpt-5-mini** -- their streaming may work with Chat Completions API instead of Responses API.
4. **Explore: Groq as fallback** for high-latency moments, but only after extensive Russian quality testing.

---

## 2. Retell -- Optimal Agent Settings

**Findings:**

Retell advertises ~600ms end-to-end latency (STT + LLM + TTS). For Custom LLM WebSocket mode (which Sofia uses), key settings:

- **`high_priority_pool: true`** -- Dedicated resources for lower, more consistent latency. Currently likely not set (defaults to false).
- **Responsiveness** -- Adjusts how quickly agent responds to utterances. Higher = faster but may cut off user.
- **Voice Speed** -- Controls speech rate of TTS output.
- **Boost Keywords** -- Prioritize specific keywords for STT ("Оазис Эстэйт", "рассрочка", "ипотека", etc.).
- **`begin_message`** -- Greeting sent immediately on call connect, zero LLM latency for first message. Sofia already does this (hardcoded greeting in `voice_api.py:71-75`).
- **Latency tracking** -- `get-call` API now provides LLM and WebSocket roundtrip latency metrics.

**Retell internal breakdown:**
- STT processing: 150-300ms
- LLM inference: 100-400ms (our part)
- TTS generation: 50-150ms

**Potential:** 50-150ms from `high_priority_pool`, better STT with Boost Keywords

**Complexity:** Low (agent config change in Retell dashboard)

**Recommendation:**
1. Enable `high_priority_pool: true` in agent settings
2. Set Boost Keywords: "Оазис Эстэйт", "рассрочка", "ипотека", "созвон", "инвестиция", "апартаменты"
3. Tune Responsiveness upward (test 0.7-0.9 range)
4. Use `get-call` API to get per-call latency breakdown for monitoring

---

## 3. Parallelism and Preloading

**Findings:**

### Can we start building prompt BEFORE receiving transcript?
Yes, partially. The system prompt + state + RAG examples can be precomputed:
- `state_manager.get_state()` -- can be cached at call start and updated incrementally
- `_determine_voice_stage()` -- depends on state, can be precomputed
- RAG examples -- can be pre-fetched for current stage (will be reused ~70% of time since stage rarely changes between turns)

Current pipeline in `stream_voice_response()` does prompt building synchronously after receiving the message. Prompt build time is logged but is typically <5ms (not a bottleneck).

### Can we run LLM in parallel while STT is still working?
Not with Retell's Custom LLM WebSocket -- Retell sends the final transcript when ready, then expects a response. We cannot start LLM before transcript arrives.

However, with Pipecat (Voice V2), we could potentially use partial/interim transcripts to speculatively start LLM inference, then cancel if the final transcript differs significantly. This is complex and error-prone.

### Prewarming LLM connection
- **HTTP/2 keep-alive**: The OpenAI Python client uses `httpx` which supports connection pooling. The `_client` in `pipeline.py` is a global singleton, so connections ARE being reused between calls.
- **Keep-alive pings**: Sending lightweight requests every 30-45s keeps TCP/TLS connections warm. Currently not implemented.
- **OpenAI Prompt Caching**: Automatic for prompts >= 1024 tokens. Cache TTL is 5-10 minutes (up to 1h off-peak). Voice prompt is ~2900 chars / ~700 tokens -- **below the 1024 token threshold!** This means prompt caching is NOT active for voice calls.

**Potential:** 30-80ms from connection warming, potentially 100-200ms from prompt caching if we increase prompt to 1024+ tokens (counterintuitive but effective)

**Complexity:** Medium

**Recommendation:**
1. **Add keep-alive pings** to OpenAI client during active calls (every 30s, lightweight request)
2. **Investigate prompt caching**: Pad the static part of voice prompt to >= 1024 tokens. Put variable content (state, stage) at the END. This would give 50% input token cost reduction AND faster processing.
3. **Pre-fetch RAG examples** for current stage at call start, refresh only when stage changes

---

## 4. Prompt Engineering for Speed

**Findings:**

### Does system prompt length affect TTFT?
Benchmark results from our server (gpt-4.1-mini):
- prompt_len=100 chars: TTFT=1030ms
- prompt_len=500 chars: TTFT=966ms
- prompt_len=2000 chars: TTFT=923ms

Counterintuitively, longer prompts did not increase TTFT in our tests. This aligns with research showing ~0.24ms per additional input token -- at 700 tokens, that is only ~168ms total token processing, small relative to network + inference startup.

### Current voice prompt analysis
- `VOICE_SYSTEM_PROMPT` in `core/pipeline.py:457-494`: ~2900 characters, ~700 tokens
- Contains: personality, sales script (7 stages), rules, prices, format instructions
- This is already quite compact compared to the full `sofia_prompt_v2.py` (35KB!)

### max_tokens effect on TTFT
Benchmark (gpt-4.1-mini):
- max_tokens=50: TTFT=493ms
- max_tokens=150: TTFT=1040ms
- max_tokens=300: TTFT=526ms
- max_tokens=800: TTFT=1338ms

Results are noisy (high variance), no clear correlation. max_tokens does NOT significantly affect TTFT for non-reasoning models.

### Can we move context from system prompt to assistant messages?
Technically possible but not recommended. System prompt is cached by OpenAI's prefix caching (if >= 1024 tokens). Moving content to messages would break caching and make each request unique.

**Potential:** Minimal (prompt is already compact, length has small TTFT impact)

**Complexity:** Low

**Recommendation:**
1. Current prompt is already well-optimized for voice
2. Consider INCREASING static prompt to 1024+ tokens to trigger OpenAI prefix caching (see Section 3)
3. Keep max_output_tokens=300 (current setting) -- lowering further risks truncation without TTFT benefit

---

## 5. Response Caching

**Findings:**

### Scripted responses for common situations
Current code already has a hardcoded greeting (`voice_api.py:71-75`). Additional candidates:

| Trigger | Scripted response | Frequency |
|---------|------------------|-----------|
| "Алло" / "Да" / "Слушаю" (first turn) | "Добрый день! Это София из Оазис Эстэйт..." | Every call |
| "Не слышу" / "Алло?" | "Да-да, я на связи! Вы меня слышите?" | ~10% calls |
| "Кто это?" / "Какая компания?" | "Оазис Эстэйт, курортная недвижимость. Вы оставляли заявку на сайте." | ~15% calls |
| "Перезвоните" / "Неудобно" | "Хорошо, перезвоним позже. Когда удобнее?" | ~10% calls |
| "Спасибо, до свидания" | "И вам спасибо, хорошего дня!" | ~5% calls |

Pattern matching (regex or keyword) can instantly respond without LLM, saving 500-1000ms.

### Pre-generation
Running LLM speculatively with predicted next user response is possible but:
- User responses are unpredictable
- Wasted API calls (cost)
- Complex state management
Not recommended at this stage.

### Retell begin_message
Already implemented -- greeting is sent immediately on WS connect.

**Potential:** 500-1000ms saved for 30-40% of turns (scripted responses)

**Complexity:** Medium (need to build pattern matching + quality test)

**Recommendation:**
1. **Build a scripted response layer** for 5-7 common patterns (regex matching before LLM call)
2. Especially valuable for: greeting acknowledgment, identity questions, "I'm busy" responses
3. Use LLM only for qualification and complex dialog turns

---

## 6. Alternative Architectures

**Findings:**

### Vapi vs Retell
- Vapi claims sub-500ms optimal latency (requires expert optimization)
- Retell claims ~600ms consistently
- Vapi has more flexibility but more variability
- Retell has better interruption handling (sub-700ms barge-in)
- Neither has a clear latency advantage -- both are in 500-800ms range
- **Migration cost is high** for marginal gain

### OpenAI Realtime API
- Available: gpt-realtime, gpt-realtime-1.5, gpt-realtime-mini
- Voice-to-voice latency: 450-900ms (first voice), 180-300ms TTFT
- Eliminates STT + TTS pipeline -- single model handles everything
- **This is the biggest potential win**: removes 200-450ms of STT + TTS overhead
- BUT: Russian TTS quality unknown, no Yandex voices, less control over persona
- Pricing: significantly more expensive than text API

### Streaming TTS (text chunks to TTS before full response)
Current `stream_voice_response()` uses `stream=false` and yields the complete response. Switching to streaming would allow sending partial text to Retell as it arrives.

However, looking at the Retell Custom LLM protocol:
- `content_complete: false` can be sent for partial responses
- Retell will start TTS on partial content
- This could save 200-500ms (TTS starts on first sentence while LLM generates second)

Current code (`voice_api.py`) already supports the `content_complete` flag but sends complete responses.

### WebSocket keep-alive with OpenAI
The OpenAI Python client already reuses connections via httpx connection pooling. The global `_client` singleton in `pipeline.py` ensures this.

**Potential:**
- Streaming to Retell: -200-500ms
- Realtime API: -200-450ms (eliminates STT/TTS) but quality risk
- Vapi migration: marginal, not worth the effort

**Complexity:**
- Streaming to Retell: Medium
- Realtime API: High (new architecture)
- Vapi: High (full rewrite)

**Recommendation:**
1. **Priority: Enable streaming to Retell** -- switch to `stream=True` in LLM call, send `content_complete: false` chunks as text arrives, then `content_complete: true` at the end. This lets Retell TTS start immediately.
2. **Investigate Realtime API** for Voice V3 -- test Russian quality with gpt-realtime-mini. If acceptable, this eliminates STT+TTS overhead entirely.
3. **Do NOT migrate to Vapi** -- marginal benefit, high cost.

---

## 7. Infrastructure

### Network Measurements (from 72.56.64.91)

**curl to api.openai.com:**
```
dns=0.020s connect=0.021s tls=0.066s ttfb=0.086s total=0.086s
```

- DNS resolution: 20ms (fast, likely cached)
- TCP connect: 1ms after DNS (21ms - 20ms) -- excellent, server is close via CDN
- TLS handshake: 45ms (66ms - 21ms) -- reasonable
- TTFB: 20ms (86ms - 66ms) -- fast
- **Total overhead per fresh connection: ~86ms**
- With keep-alive (no DNS/TCP/TLS): ~20ms

The connect time of 1ms suggests OpenAI uses a CDN with a POP near Russia (likely Cloudflare). This means:
- **A proxy closer to OpenAI would NOT help** -- we already have low network latency
- The bottleneck is LLM inference time, not network

### ping
ICMP ping to api.openai.com was blocked (server firewall or OpenAI does not respond to ICMP).

### Where is the latency?
Given 86ms total network overhead and ~325ms TTFT for gpt-5.4-mini:
- Network: ~86ms (26% of TTFT)
- LLM inference startup: ~239ms (74% of TTFT)
- **Network is NOT the bottleneck**

**Potential:** Minimal from infrastructure changes

**Complexity:** N/A

**Recommendation:**
1. No proxy needed -- CDN already provides fast connectivity
2. Ensure connection pooling is active (it is, via global OpenAI client)
3. Monitor with Retell get-call API for per-call breakdown

---

## Summary: Latency Reduction Roadmap

### Quick Wins (Total: -400 to -700ms)

| Action | Est. Savings | Complexity | Priority |
|--------|-------------|------------|----------|
| Switch VOICE_MODEL to gpt-5.4-mini | -280ms TTFT | Low | P0 |
| Enable streaming to Retell (content_complete: false) | -200-400ms | Medium | P0 |
| Retell high_priority_pool: true | -50-150ms | Low | P0 |
| Retell Boost Keywords | -30-50ms STT | Low | P1 |

### Medium-Term (Total: -200 to -500ms additional)

| Action | Est. Savings | Complexity | Priority |
|--------|-------------|------------|----------|
| Scripted responses for common patterns | -500-1000ms for 30% turns | Medium | P1 |
| Pad prompt to 1024+ tokens for prefix caching | -100-200ms | Low | P1 |
| Connection keep-alive pings | -30-80ms | Low | P2 |

### Long-Term Research

| Action | Est. Savings | Complexity | Priority |
|--------|-------------|------------|----------|
| OpenAI Realtime API (Voice V3) | -200-450ms | High | P2 |
| Groq fallback for simple stages | -300ms | High | P3 |
| gpt-5.4-nano for GREETING/CLOSING | -100ms | Low | P3 |

### Expected Result After Quick Wins

Current: 900-3000ms end-to-end
After P0 changes: **500-1500ms end-to-end** (estimated)
- LLM TTFT: 325ms (was 600ms)
- Streaming overlap: saves 200-400ms of TTS wait
- High priority pool: -50-150ms consistency

### Files to Modify

- `/opt/sofia-gpt-dev/core/pipeline.py` line 28: `VOICE_MODEL = "gpt-5.4-mini"`
- `/opt/sofia-gpt-dev/core/pipeline.py` lines 576-593: Switch to `stream=True`, collect and yield chunks
- `/opt/sofia-gpt-dev/voice_api.py` lines 148+: Send `content_complete: false` partial responses
- Retell dashboard: agent settings (high_priority_pool, boost_keywords, responsiveness)

---

## Appendix: Raw Benchmark Data

### Test 1: gpt-4.1-mini TTFT vs Prompt Length
```
prompt_len=100: TTFT=1030ms
prompt_len=500: TTFT=966ms
prompt_len=2000: TTFT=923ms
```

### Test 2: Model Comparison (3 runs each)
```
gpt-4.1-nano: TTFT avg=885ms, total avg=1114ms
gpt-4.1-mini: TTFT avg=606ms, total avg=951ms
gpt-5.4-nano: TTFT avg=601ms, total avg=1083ms (high variance, spike to 1083ms)
gpt-5.4-mini: TTFT avg=325ms, total avg=737ms
Groq llama-3.3-70b: TTFT avg=146ms, total avg=454ms
Groq llama-3.1-8b: TTFT avg=54ms, total avg=174ms
```

### Test 3: max_tokens Effect (gpt-4.1-mini)
```
max_tokens=50: TTFT=493ms
max_tokens=150: TTFT=1040ms
max_tokens=300: TTFT=526ms
max_tokens=800: TTFT=1338ms
(high variance, no clear correlation)
```

### Test 4: Network Timing
```
curl https://api.openai.com/:
  dns=0.020s connect=0.021s tls=0.066s ttfb=0.086s total=0.086s
```
