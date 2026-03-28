"""
A/B test round 2: gpt-5.4-mini vs qwen3-32b vs llama-4-scout-17b.
Enhanced prompt V2 for Groq models (stricter rules against "Ponjala", hallucinations).
Measures streaming TTFT, total time, and automated quality checks.
"""

import asyncio
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

load_dotenv()

# === CONFIG ===

OPENAI_MODEL = "gpt-5.4-mini"
GROQ_QWEN_MODEL = "qwen/qwen3-32b"
GROQ_LLAMA_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

openai_sync_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

RUNS_PER_CASE = 2
GROQ_DELAY = 3  # seconds between Groq requests to avoid rate limit queuing

# === PROMPTS ===  # noqa: E501 — long lines inside multiline strings are intentional

# Original prompt for OpenAI (already works well)
VOICE_SYSTEM_PROMPT = """Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

ЭТАП: {stage}
КЛИЕНТ: {state_summary}

СКРИПТ (иди по этапам, но подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: "Просто под инвестиции и для жизни подбираем разные объекты — локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?" После ответа — сразу к бюджету, без уточнений про стратегию.
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: "До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: "От способа оплаты зависит выбор — есть варианты только за наличные, а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: "Давайте наш эксперт за пятнадцать минут покажет два-три варианты под ваш запрос. Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы (локация — море или горы? стадия — готовое или стройка?), потом повторно: "За пятнадцать минут покажем варианты, которых нет в открытом доступе. Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — "Хорошо, эксперт подготовит подборку и пришлёт вам. Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- СТРОГО один вопрос за ответ. Уточнение тоже считается вопросом. Два вопроса в одном ответе — грубая ошибка.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет", "правильное решение". Просто прими и двигайся дальше.
- НЕ начинай каждый ответ одинаково. Чередуй: ответ на вопрос, уточнение, переход к делу. Слово "Поняла" ЗАПРЕЩЕНО. Не используй. Сразу переходи к сути.
- НЕ пугай ограничениями. Вместо "ипотека ограничивает выбор" — "с ипотекой тоже есть варианты".
- Если клиент задал вопрос — СНАЧАЛА ответь коротко (одно предложение), потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Говори "от", никогда не говори "до" — верхней границы нет, цены начинаются от указанных сумм.
{object_context}

ФОРМАТ: Только текст ответа клиенту (1-2 предложения). Ничего больше."""

# Enhanced prompt V2 for Groq models (extra strictness)
VOICE_SYSTEM_PROMPT_V2 = """Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

ЭТАП: {stage}
КЛИЕНТ: {state_summary}

СТРОГИЕ ЗАПРЕТЫ (нарушение = критическая ошибка):
- НИКОГДА не начинай ответ словами: "Поняла", "Понял", "Понятно", "Ясно", "Хорошо, поняла". Это ЗАПРЕЩЕНО.
- НИКОГДА не предлагай конкретное время (14:00, завтра в 10), дату, адрес — только уточняй у клиента.
- НИКОГДА не выдумывай факты об объектах, ценах, процентах доходности, условиях — если не знаешь точно, предложи уточнить у эксперта.
- Вместо "Поняла" используй: сразу переходи к вопросу, или начни с краткого парафраза ("Инвестиция — хорошо.", "Море — отличное направление.").

СКРИПТ (иди по этапам, но подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: "Просто под инвестиции и для жизни подбираем разные объекты — локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?" После ответа — сразу к бюджету, без уточнений про стратегию.
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: "До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: "От способа оплаты зависит выбор — есть варианты только за наличные, а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: "Давайте наш эксперт за пятнадцать минут покажет два-три варианта под ваш запрос. Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы (локация — море или горы? стадия — готовое или стройка?), потом повторно: "За пятнадцать минут покажем варианты, которых нет в открытом доступе. Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — "Хорошо, эксперт подготовит подборку и пришлёт вам. Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- СТРОГО один вопрос за ответ. Уточнение тоже считается вопросом.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет".
- НЕ пугай ограничениями. Вместо "ипотека ограничивает выбор" — "с ипотекой тоже есть варианты".
- Если клиент задал вопрос — СНАЧАЛА ответь коротко (одно предложение), потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Говори "от", никогда не говори "до" — верхней границы нет.
{object_context}

ФОРМАТ: Только текст ответа клиенту (1-2 предложения). Ничего больше."""


# === TEST CASES ===

MANUAL_TEST_CASES = [
    {
        "desc": "1_greeting_cold",
        "stage": "GREETING",
        "state_summary": "новый клиент",
        "messages": [{"role": "user", "content": "Алло, здравствуйте"}],
    },
    {
        "desc": "2_goal_investment",
        "stage": "GOAL",
        "state_summary": "новый клиент",
        "messages": [
            {
                "role": "assistant",
                "content": "Добрый день! Это София из Оазис Эстэйт. "
                "Вы оставляли заявку на сайте по недвижимости. "
                "Расскажите, что ищете?",
            },
            {
                "role": "user",
                "content": "Хочу инвестировать в недвижимость на юге",
            },
        ],
    },
    {
        "desc": "3_goal_unsure",
        "stage": "GOAL",
        "state_summary": "новый клиент",
        "messages": [
            {
                "role": "assistant",
                "content": "Добрый день! Это София из Оазис Эстэйт. "
                "Расскажите, что ищете?",
            },
            {"role": "user", "content": "Ну не знаю, просто интересуюсь"},
        ],
    },
    {
        "desc": "4_budget_range",
        "stage": "BUDGET",
        "state_summary": "goal=инвестиция",
        "messages": [
            {
                "role": "assistant",
                "content": "Скажите, какой примерно бюджет рассматриваете?",
            },
            {
                "role": "user",
                "content": "Ну где-то десять пятнадцать миллионов",
            },
        ],
    },
    {
        "desc": "5_budget_dont_know",
        "stage": "BUDGET",
        "state_summary": "goal=для себя, отдых",
        "messages": [
            {
                "role": "assistant",
                "content": "Какой примерно бюджет комфортен?",
            },
            {
                "role": "user",
                "content": "Даже не знаю, а какие цены вообще?",
            },
        ],
    },
    {
        "desc": "6_payment_question",
        "stage": "PAYMENT",
        "state_summary": "goal=инвестиция, budget=10-15 млн",
        "messages": [
            {
                "role": "assistant",
                "content": "Рассматриваете полную оплату, рассрочку или ипотеку?",
            },
            {
                "role": "user",
                "content": "А какая рассрочка у вас? На сколько месяцев?",
            },
        ],
    },
    {
        "desc": "7_objection_expensive",
        "stage": "MEETING_1",
        "state_summary": "goal=инвестиция, budget=10 млн, payment=ипотека",
        "messages": [
            {
                "role": "assistant",
                "content": "Давайте наш эксперт покажет варианты — "
                "пятнадцать минут, без обязательств. Когда удобно?",
            },
            {"role": "user", "content": "Это дорого, я видел дешевле"},
        ],
    },
    {
        "desc": "8_meeting_decline",
        "stage": "MEETING_2",
        "state_summary": "goal=инвестиция, budget=12 млн, payment=рассрочка, "
        "meeting_declined=1",
        "messages": [
            {
                "role": "assistant",
                "content": "Скажите, вам ближе море или горы?",
            },
            {
                "role": "user",
                "content": "Море. Но созваниваться не хочу, "
                "пришлите мне подборку лучше",
            },
        ],
    },
    {
        "desc": "9_meeting_agree",
        "stage": "MEETING_1",
        "state_summary": "goal=для себя, budget=8 млн, payment=полная оплата",
        "messages": [
            {
                "role": "assistant",
                "content": "Давайте эксперт за пятнадцать минут "
                "покажет два-три варианта. Когда удобно?",
            },
            {"role": "user", "content": "Давайте завтра после обеда"},
        ],
    },
    {
        "desc": "10_price_question",
        "stage": "BUDGET",
        "state_summary": "goal=инвестиция, аренда",
        "messages": [
            {
                "role": "assistant",
                "content": "Какой бюджет рассматриваете?",
            },
            {"role": "user", "content": "А сколько стоит в Сочи?"},
        ],
    },
    {
        "desc": "11_location_crimea",
        "stage": "MEETING_2",
        "state_summary": "goal=инвестиция, budget=10-15 млн, payment=ипотека",
        "messages": [
            {
                "role": "assistant",
                "content": "Вам ближе море или горы?",
            },
            {
                "role": "user",
                "content": "Крым, может быть, там что-то есть?",
            },
        ],
    },
    {
        "desc": "12_busy_callback",
        "stage": "GREETING",
        "state_summary": "новый клиент",
        "messages": [
            {
                "role": "assistant",
                "content": "Добрый день! Это София из Оазис Эстэйт.",
            },
            {
                "role": "user",
                "content": "Неудобно сейчас, перезвоните позже",
            },
        ],
    },
]


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> from Qwen3 output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def run_openai_streaming(system_prompt, messages):
    """OpenAI Responses API streaming."""
    input_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]

    ttft = None
    chunks = []
    start = time.perf_counter()

    try:
        stream = openai_sync_client.responses.create(
            model=OPENAI_MODEL,
            instructions=system_prompt,
            input=input_msgs,
            max_output_tokens=300,
            stream=True,
        )

        for event in stream:
            if event.type == "response.output_text.delta":
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                chunks.append(event.delta)

        total_ms = (time.perf_counter() - start) * 1000
        return {
            "ttft_ms": round(ttft, 1) if ttft else None,
            "total_ms": round(total_ms, 1),
            "response": "".join(chunks),
            "error": None,
        }
    except Exception as e:
        total_ms = (time.perf_counter() - start) * 1000
        return {
            "ttft_ms": None,
            "total_ms": round(total_ms, 1),
            "response": None,
            "error": str(e),
        }


async def run_groq_streaming(model, system_prompt, messages):
    """Groq Chat Completions API streaming."""
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    ttft = None
    chunks = []
    start = time.perf_counter()

    try:
        stream = await groq_client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=300,
            temperature=0.7,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                if ttft is None:
                    ttft = (time.perf_counter() - start) * 1000
                chunks.append(chunk.choices[0].delta.content)

        total_ms = (time.perf_counter() - start) * 1000
        full_response = "".join(chunks)

        if "<think>" in full_response:
            full_response = strip_think_tags(full_response)

        return {
            "ttft_ms": round(ttft, 1) if ttft else None,
            "total_ms": round(total_ms, 1),
            "response": full_response,
            "error": None,
        }
    except Exception as e:
        total_ms = (time.perf_counter() - start) * 1000
        return {
            "ttft_ms": None,
            "total_ms": round(total_ms, 1),
            "response": None,
            "error": str(e),
        }


def check_quality(response: str) -> dict:
    """Automated quality checks on the response."""
    if not response:
        return {"pass": False, "issues": ["empty_response"]}

    issues = []
    lower = response.lower().strip()

    # Forbidden starts
    for word in ["поняла", "понял", "понятно", "ясно"]:
        if lower.startswith(word):
            issues.append(f"starts_with_{word}")

    # Multiple questions
    questions = response.count("?")
    if questions >= 2:
        issues.append(f"multiple_questions_{questions}")

    # Latin chars (3+ consecutive)
    latin_words = re.findall(r"[a-zA-Z]{3,}", response)
    # Filter out [END] which is expected
    latin_words = [w for w in latin_words if w != "END"]
    if latin_words:
        issues.append(f"latin_chars ({', '.join(latin_words[:3])})")

    # URL / email
    if re.search(r"https?://", response) or ".com" in response:
        issues.append("url")
    if "@" in response:
        issues.append("email")

    # Specific time hallucination (14:00, в 10 часов, etc.)
    if re.search(r"\d{1,2}:\d{2}", response):
        issues.append("specific_time")
    if re.search(r"\d{1,2}\s*(часов|часа|час)\b", response):
        issues.append("specific_time")

    # Too long (> 3 sentences)
    sentences = [s.strip() for s in re.split(r"[.!?]+", response) if s.strip()]
    if len(sentences) > 3:
        issues.append(f"too_long_{len(sentences)}_sent")

    # Praise
    for pw in ["отличный выбор", "хороший бюджет", "правильное решение"]:
        if pw in lower:
            issues.append(f"praise ({pw})")

    return {"pass": len(issues) == 0, "issues": issues}


# === MODELS CONFIG ===

MODELS = [
    {
        "key": "openai",
        "label": "OpenAI gpt-5.4-mini",
        "model": OPENAI_MODEL,
        "provider": "openai",
    },
    {
        "key": "qwen3",
        "label": "Groq qwen3-32b (V2)",
        "model": GROQ_QWEN_MODEL,
        "provider": "groq",
        "prompt_suffix": "\n\n/no_think",
    },
    {
        "key": "llama4",
        "label": "Groq llama-4-scout (V2)",
        "model": GROQ_LLAMA_MODEL,
        "provider": "groq",
    },
]


async def run_ab_test():
    """Main A/B test: 3 models, 12 cases, 2 runs each."""

    test_cases = MANUAL_TEST_CASES
    print(f"Test cases: {len(test_cases)}, runs per case: {RUNS_PER_CASE}")
    print(f"Models: {', '.join(m['label'] for m in MODELS)}")
    print(f"Groq delay: {GROQ_DELAY}s between requests")

    results = []

    for i, case in enumerate(test_cases):
        desc = case["desc"]
        stage = case.get("stage", "GOAL")
        state_summary = case.get("state_summary", "")

        print(f"\n{'='*70}")
        print(f"[{i+1}/{len(test_cases)}] {desc}")
        print(f"  User: {case['messages'][-1]['content'][:80]}")

        for run_id in range(RUNS_PER_CASE):
            run_results = {}

            for mcfg in MODELS:
                key = mcfg["key"]
                provider = mcfg["provider"]

                # Build prompt
                if provider == "openai":
                    prompt = VOICE_SYSTEM_PROMPT.format(
                        stage=stage,
                        state_summary=state_summary,
                        object_context="",
                    )
                else:
                    prompt = VOICE_SYSTEM_PROMPT_V2.format(
                        stage=stage,
                        state_summary=state_summary,
                        object_context="",
                    )
                    suffix = mcfg.get("prompt_suffix", "")
                    if suffix:
                        prompt = prompt.strip() + suffix

                # Run
                if provider == "openai":
                    r = await asyncio.to_thread(
                        run_openai_streaming, prompt, case["messages"]
                    )
                else:
                    # Delay before Groq to avoid rate limiting
                    await asyncio.sleep(GROQ_DELAY)
                    r = await run_groq_streaming(
                        mcfg["model"], prompt, case["messages"]
                    )

                r.update(
                    case=desc,
                    provider_key=key,
                    provider=provider,
                    model=mcfg["model"],
                    label=mcfg["label"],
                    run=run_id,
                )
                results.append(r)
                run_results[key] = r

            # Print run summary
            parts = []
            for mcfg in MODELS:
                r = run_results[mcfg["key"]]
                t = r["ttft_ms"]
                parts.append(f"{mcfg['key']}={t:.0f}ms" if t else f"{mcfg['key']}=ERR")
            print(f"  Run {run_id+1}: {' | '.join(parts)}")

        # Show last responses side-by-side
        print()
        for mcfg in MODELS:
            last = [
                r
                for r in results
                if r["case"] == desc and r["provider_key"] == mcfg["key"]
            ][-1]
            resp = (last["response"] or "ERROR")[:160]
            q = check_quality(last["response"] or "")
            status = "PASS" if q["pass"] else f"FAIL {q['issues']}"
            print(f"  [{mcfg['key']:6s}] {resp}")
            print(f"           {status}")

    # === SUMMARY ===
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY")
    print(f"{'='*70}\n")

    # Header
    print(
        f"{'Model':<30s} {'TTFT med':>8s} {'TTFT min':>8s} "
        f"{'TTFT max':>8s} {'Quality':>10s} {'Ponjala':>8s} "
        f"{'2+Q':>5s} {'Time':>6s} {'Errs':>5s}"
    )
    print("-" * 100)

    for mcfg in MODELS:
        key = mcfg["key"]
        all_r = [r for r in results if r["provider_key"] == key]
        valid = [r for r in all_r if r["ttft_ms"] and r["ttft_ms"] < 1000]
        with_text = [r for r in all_r if r["response"]]
        errors = sum(1 for r in all_r if r["error"])

        if not valid:
            print(f"{mcfg['label']:<30s} {'N/A':>8s} (all rate-limited or errors)")
            continue

        ttfts = sorted([r["ttft_ms"] for r in valid])
        totals = sorted([r["total_ms"] for r in valid])
        median_ttft = ttfts[len(ttfts) // 2]

        q_pass = sum(1 for r in with_text if check_quality(r["response"])["pass"])
        q_total = len(with_text)

        ponjala = sum(
            1
            for r in with_text
            if r["response"].lower().strip().startswith("поняла")
            or r["response"].lower().strip().startswith("понял,")
            or r["response"].lower().strip().startswith("понятно")
        )
        multi_q = sum(1 for r in with_text if r["response"].count("?") >= 2)
        spec_time = sum(  # noqa: F841
            1 for r in with_text if re.search(r"\d{1,2}:\d{2}", r["response"])
        )

        median_total = totals[len(totals) // 2]

        print(
            f"{mcfg['label']:<30s} {median_ttft:>7.0f}ms {min(ttfts):>7.0f}ms "
            f"{max(ttfts):>7.0f}ms {q_pass:>4d}/{q_total:<4d} "
            f"{ponjala:>7d} {multi_q:>5d} {median_total:>5.0f}ms {errors:>5d}"
        )

    # Note about rate-limited requests
    all_groq = [r for r in results if r["provider"] == "groq" and r["ttft_ms"]]
    rate_limited = [r for r in all_groq if r["ttft_ms"] >= 1000]
    if rate_limited:
        print(
            f"\nNote: {len(rate_limited)}/{len(all_groq)} Groq requests "
            f"were rate-limited (TTFT >= 1000ms) and excluded from stats."
        )

    # Save results
    output_dir = os.path.join(os.getenv("SOFIA_PATH", "/opt/sofia-gpt-dev"), "tests")
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "ab_test_results_v2.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Markdown report
    md_path = os.path.join(output_dir, "ab_test_results_v2.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# A/B Test Round 2: gpt-5.4-mini vs qwen3-32b vs llama-4-scout\n\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Cases: {len(test_cases)}, runs per case: {RUNS_PER_CASE}\n")
        f.write("Groq models use enhanced prompt V2 (stricter rules).\n\n")

        f.write("## Side-by-side responses\n\n")
        seen = set()
        for r in results:
            if (
                r["case"] not in seen
                and r["provider_key"] == "openai"
                and r["run"] == 0
            ):
                seen.add(r["case"])
                f.write(f"### {r['case']}\n\n")

                for mcfg in MODELS:
                    mr = next(
                        (
                            x
                            for x in results
                            if x["case"] == r["case"]
                            and x["provider_key"] == mcfg["key"]
                            and x["run"] == 0
                        ),
                        None,
                    )
                    if mr and mr["response"]:
                        q = check_quality(mr["response"])
                        status = "PASS" if q["pass"] else f"FAIL {q['issues']}"
                        f.write(
                            f"**{mcfg['label']}** (TTFT {mr['ttft_ms']}ms) "
                            f"{status}:\n> {mr['response']}\n\n"
                        )
                f.write("---\n\n")

    print(f"\nFull results: {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    asyncio.run(run_ab_test())
