"""
Multi-turn test: llama-4-scout vs gpt-5.4-mini on full dialog scenarios.
Tests context retention, script adherence, looping, and hallucinations
across 6-7 turn conversations.
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
GROQ_LLAMA_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

openai_sync_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

GROQ_DELAY = 3  # seconds between Groq requests

# === PROMPTS ===

# Original prompt for OpenAI (as in production)
VOICE_SYSTEM_PROMPT = """\
Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. \
Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

СКРИПТ (иди по этапам, но подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: \
"Просто под инвестиции и для жизни подбираем разные объекты — \
локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?" \
После ответа — сразу к бюджету, без уточнений про стратегию.
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: \
"До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, \
выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: \
"От способа оплаты зависит выбор — есть варианты только за наличные, \
а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: \
"Давайте наш эксперт за пятнадцать минут покажет два-три варианта под ваш запрос. \
Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы \
(локация — море или горы? стадия — готовое или стройка?), потом повторно: \
"За пятнадцать минут покажем варианты, которых нет в открытом доступе. \
Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — \
"Хорошо, эксперт подготовит подборку и пришлёт вам. \
Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- СТРОГО один вопрос за ответ. Уточнение тоже считается вопросом. \
Два вопроса в одном ответе — грубая ошибка.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет", \
"правильное решение". Просто прими и двигайся дальше.
- НЕ начинай каждый ответ одинаково. Чередуй: ответ на вопрос, \
уточнение, переход к делу. Слово "Поняла" ЗАПРЕЩЕНО. Не используй. \
Сразу переходи к сути.
- НЕ пугай ограничениями.
- Если клиент задал вопрос — СНАЧАЛА ответь коротко (одно предложение), \
потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Говори "от", никогда не говори "до" — верхней границы нет.

ФОРМАТ: Только текст ответа клиенту (1-2 предложения). Ничего больше."""

# Enhanced prompt V3 for Groq llama-4-scout
VOICE_SYSTEM_PROMPT_V3 = """\
Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. \
Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

СТРОГИЕ ЗАПРЕТЫ (нарушение = критическая ошибка):
- НИКОГДА не начинай ответ словами: "Поняла", "Понял", "Понятно", "Ясно".
- НИКОГДА не предлагай конкретное время, дату, адрес — только уточняй у клиента.
  Ты НЕ ЗНАЕШЬ расписание эксперта. Можешь только спросить удобное время.
- НИКОГДА не выдумывай факты: проценты доходности, конкретные объекты, условия. \
  Если не знаешь — предложи уточнить у эксперта.
- Вместо "Поняла" начни с парафраза ("Инвестиция — хорошо.", \
"Море — отличное направление.") или сразу переходи к вопросу.

СКРИПТ (иди по этапам, но подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: \
"Просто под инвестиции и для жизни подбираем разные объекты — \
локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?" \
После ответа — сразу к бюджету, без уточнений про стратегию.
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: \
"До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, \
выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: \
"От способа оплаты зависит выбор — есть варианты только за наличные, \
а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: \
"Давайте наш эксперт за пятнадцать минут покажет два-три варианта. \
Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы \
(локация — море или горы? стадия — готовое или стройка?), потом повторно: \
"За пятнадцать минут покажем варианты, которых нет в открытом доступе. \
Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — \
"Хорошо, эксперт подготовит подборку и пришлёт вам. \
Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- СТРОГО один вопрос за ответ. Уточнение тоже считается вопросом.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет".
- НЕ пугай ограничениями.
- Если клиент задал вопрос — СНАЧАЛА ответь коротко (одно предложение), \
потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Говори "от", никогда не говори "до" — верхней границы нет.

ФОРМАТ: Только текст ответа клиенту (1-2 предложения). Ничего больше."""

# === SCENARIOS ===

SCENARIOS = [
    {
        "name": "investor_sochi",
        "desc": "Инвестор, юг, бюджет 15М, рассрочка, соглашается на встречу",
        "client_turns": [
            "Привет",
            "Хочу инвестировать в недвижимость на юге",
            "Ну где-то пятнадцать миллионов",
            "Рассрочку бы, полностью сразу не готов",
            "А какая доходность в Сочи сейчас?",
            "Ладно, давайте созвонимся с вашим экспертом",
            "Завтра после обеда удобно",
        ],
    },
    {
        "name": "family_budget_10m",
        "desc": "Семья, для себя, бюджет 10М, ипотека, сомневается",
        "client_turns": [
            "Здравствуйте",
            "Мы с семьёй хотим купить квартиру у моря",
            "Около десяти миллионов",
            "Скорее ипотека",
            "Это дорого, я видел дешевле у других",
            "Не знаю, мне надо подумать",
            "Ну ладно, а когда можно поговорить?",
        ],
    },
    {
        "name": "cold_skeptic",
        "desc": "Холодный клиент, мало говорит, скептик, отказывается",
        "client_turns": [
            "Да",
            "Просто смотрю",
            "Не решил ещё",
            "Не знаю бюджет",
            "Нет, созваниваться не хочу",
            "Нет",
        ],
    },
    {
        "name": "detailed_questions",
        "desc": "Клиент с кучей вопросов — проверяет контекст",
        "client_turns": [
            "Добрый день",
            "Интересует инвестиционная недвижимость",
            "А какие объекты есть?",
            "А какая доходность?",
            "А рассрочка есть?",
            "Бюджет двадцать миллионов",
            "Давайте поговорим с экспертом, когда можно?",
        ],
    },
]


# === MODELS ===

MODELS = [
    {
        "key": "openai",
        "label": "OpenAI gpt-5.4-mini",
        "model": OPENAI_MODEL,
        "provider": "openai",
        "prompt": VOICE_SYSTEM_PROMPT,
    },
    {
        "key": "llama4",
        "label": "Groq llama-4-scout",
        "model": GROQ_LLAMA_MODEL,
        "provider": "groq",
        "prompt": VOICE_SYSTEM_PROMPT_V3,
    },
]


# === STREAMING FUNCTIONS ===


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
        # Strip think tags just in case
        if "<think>" in full_response:
            full_response = re.sub(
                r"<think>.*?</think>", "", full_response, flags=re.DOTALL
            ).strip()
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


# === QUALITY CHECKS ===


def check_turn(turn_num, response, history):
    """Check quality of a single turn in multi-turn dialog."""
    if not response:
        return {"pass": False, "issues": ["empty_response"]}

    issues = []
    lower = response.lower().strip()

    # Forbidden starts
    for word in ["поняла", "понял,", "понятно", "ясно,"]:
        if lower.startswith(word):
            issues.append(f"forbidden_start_{word.rstrip(',')}")

    # Multiple questions
    if response.count("?") >= 2:
        issues.append("multiple_questions")

    # Specific time hallucination
    if re.search(r"\d{1,2}:\d{2}", response):
        issues.append("specific_time")
    if re.search(r"\d{1,2}\s*(часов|часа|час)\b", response):
        issues.append("specific_time")

    # Latin chars (3+ consecutive, excluding [END])
    latin_words = re.findall(r"[a-zA-Z]{3,}", response)
    latin_words = [w for w in latin_words if w != "END"]
    if latin_words:
        issues.append(f"latin ({', '.join(latin_words[:2])})")

    # URL / email
    if re.search(r"https?://", response) or "@" in response:
        issues.append("url_or_email")

    # Too long
    sentences = [s.strip() for s in re.split(r"[.!?]+", response) if s.strip()]
    if len(sentences) > 4:
        issues.append(f"too_long_{len(sentences)}")

    # Repeating already-answered questions
    client_said = " ".join(h["content"] for h in history if h["role"] == "user").lower()

    budget_kw = ["миллион", "млн", "тысяч"]
    if (
        any(k in client_said for k in budget_kw)
        and any(k in lower for k in ["какой бюджет", "какую сумму", "сколько готовы"])
        and turn_num > 2
    ):
        issues.append("repeats_budget_q")

    goal_kw = ["инвестир", "для себя", "семь", "аренд"]
    if (
        any(k in client_said for k in goal_kw)
        and any(k in lower for k in ["для чего", "какая цель", "для себя или инвестиц"])
        and turn_num > 2
    ):
        issues.append("repeats_goal_q")

    # Looping — too similar to previous assistant response
    assistant_msgs = [h["content"] for h in history if h["role"] == "assistant"]
    if assistant_msgs:
        prev = set(assistant_msgs[-1].lower().split())
        curr = set(lower.split())
        if curr and len(prev & curr) > 0.7 * len(curr):
            issues.append("looping")

    return {"pass": len(issues) == 0, "issues": issues}


def detect_stage(response, history):
    """Heuristic: which script stage is the model at based on response."""
    lower = response.lower()

    if any(k in lower for k in ["представ", "оазис эстэйт", "чем могу"]):
        return "GREETING"
    if any(
        k in lower
        for k in [
            "для себя или",
            "инвестици",
            "аренд",
            "для отдых",
            "доход",
        ]
    ):
        return "GOAL"
    if any(k in lower for k in ["бюджет", "сумм", "миллион", "студи"]):
        return "BUDGET"
    if any(k in lower for k in ["рассрочк", "ипотек", "полн", "оплат", "наличн"]):
        return "PAYMENT"
    if any(
        k in lower for k in ["созвон", "эксперт", "пятнадцать минут", "когда удобно"]
    ):
        return "MEETING"
    if "[end]" in lower or "подборк" in lower:
        return "CLOSING"
    return "?"


# === MAIN ===


async def run_multiturn_test():
    """Run multi-turn dialog test for each model and scenario."""

    print(f"Models: {', '.join(m['label'] for m in MODELS)}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Groq delay: {GROQ_DELAY}s between requests\n")

    all_results = {}

    for scenario in SCENARIOS:
        sname = scenario["name"]
        turns = scenario["client_turns"]

        print(f"\n{'='*70}")
        print(f"SCENARIO: {sname}")
        print(f"  {scenario['desc']}")
        print(f"  Turns: {len(turns)}")

        all_results[sname] = {}

        for mcfg in MODELS:
            key = mcfg["key"]
            label = mcfg["label"]
            prompt = mcfg["prompt"]

            print(f"\n  --- {label} ---")

            history = []
            turn_results = []

            for t_idx, client_msg in enumerate(turns):
                turn_num = t_idx + 1

                # Add client message to history
                history.append({"role": "user", "content": client_msg})

                # Call model
                if mcfg["provider"] == "openai":
                    r = await asyncio.to_thread(run_openai_streaming, prompt, history)
                else:
                    await asyncio.sleep(GROQ_DELAY)
                    r = await run_groq_streaming(mcfg["model"], prompt, history)

                response = r["response"] or ""
                ttft = r["ttft_ms"]
                error = r["error"]

                # Quality check
                q = check_turn(turn_num, response, history)
                stage = detect_stage(response, history)

                # Add assistant response to history
                if response:
                    history.append({"role": "assistant", "content": response})

                # Store result
                turn_results.append(
                    {
                        "turn": turn_num,
                        "user": client_msg,
                        "response": response,
                        "ttft_ms": ttft,
                        "total_ms": r["total_ms"],
                        "quality": q,
                        "stage": stage,
                        "error": error,
                    }
                )

                # Print
                status = "PASS" if q["pass"] else f"FAIL {q['issues']}"
                ttft_str = f"{ttft:.0f}ms" if ttft else "ERR"
                rl = " [RL]" if ttft and ttft > 1000 else ""
                print(
                    f"  Turn {turn_num} "
                    f"(TTFT {ttft_str}{rl}, stage={stage}) "
                    f"{status}"
                )
                print(f"    User:  {client_msg}")
                print(f"    Sofia: {response[:140]}")

            all_results[sname][key] = turn_results

    # === SUMMARY ===
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")

    # Table header
    print(
        f"{'Scenario':<22s} {'Model':<22s} "
        f"{'OK':>4s} {'Total':>5s} "
        f"{'TTFT med':>8s} {'Repeat':>6s} "
        f"{'Loop':>5s} {'Halluc':>6s} {'Stages':>20s}"
    )
    print("-" * 100)

    model_stats = {m["key"]: {"ok": 0, "total": 0, "ttfts": []} for m in MODELS}

    for scenario in SCENARIOS:
        sname = scenario["name"]
        for mcfg in MODELS:
            key = mcfg["key"]
            trs = all_results[sname][key]

            passed = sum(1 for t in trs if t["quality"]["pass"])
            total = len(trs)
            # Filter out rate-limited for TTFT stats
            ttfts = [t["ttft_ms"] for t in trs if t["ttft_ms"] and t["ttft_ms"] < 1000]
            median_ttft = sorted(ttfts)[len(ttfts) // 2] if ttfts else 0
            repeats = sum(
                1 for t in trs if any("repeats_" in i for i in t["quality"]["issues"])
            )
            loops = sum(1 for t in trs if "looping" in t["quality"]["issues"])
            halluc = sum(
                1
                for t in trs
                if any(i in ["specific_time", "latin"] for i in t["quality"]["issues"])
            )
            stages = " → ".join(t["stage"] for t in trs)

            model_stats[key]["ok"] += passed
            model_stats[key]["total"] += total
            model_stats[key]["ttfts"].extend(ttfts)

            print(
                f"{sname:<22s} {mcfg['label']:<22s} "
                f"{passed:>3d}/{total:<2d} "
                f"{median_ttft:>7.0f}ms "
                f"{repeats:>6d} {loops:>5d} {halluc:>6d} "
                f"{stages:>20s}"
            )

    # Overall stats
    print(f"\n{'OVERALL':=^70}\n")
    for mcfg in MODELS:
        key = mcfg["key"]
        s = model_stats[key]
        ttfts = sorted(s["ttfts"]) if s["ttfts"] else [0]
        median = ttfts[len(ttfts) // 2]
        print(
            f"{mcfg['label']}: "
            f"{s['ok']}/{s['total']} turns passed "
            f"({100*s['ok']/s['total']:.0f}%), "
            f"TTFT median={median:.0f}ms "
            f"(min={min(ttfts):.0f}ms, max={max(ttfts):.0f}ms)"
        )

    # Save full results
    output_dir = os.path.join(os.getenv("SOFIA_PATH", "/opt/sofia-gpt-dev"), "tests")
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "multiturn_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results: {json_path}")

    # Markdown report
    md_path = os.path.join(output_dir, "multiturn_results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Multi-turn Test: " "gpt-5.4-mini vs llama-4-scout\n\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n\n")

        for scenario in SCENARIOS:
            sname = scenario["name"]
            f.write(f"## {sname}: {scenario['desc']}\n\n")

            for mcfg in MODELS:
                key = mcfg["key"]
                trs = all_results[sname][key]
                f.write(f"### {mcfg['label']}\n\n")

                for t in trs:
                    status = (
                        "PASS"
                        if t["quality"]["pass"]
                        else f"FAIL {t['quality']['issues']}"
                    )
                    ttft_str = f"{t['ttft_ms']:.0f}ms" if t["ttft_ms"] else "ERR"
                    f.write(
                        f"**Turn {t['turn']}** "
                        f"(TTFT {ttft_str}, {t['stage']}) "
                        f"{status}\n"
                    )
                    f.write(f"- User: {t['user']}\n")
                    f.write(f"- Sofia: {t['response']}\n\n")

                f.write("---\n\n")

    print(f"Report: {md_path}")


if __name__ == "__main__":
    asyncio.run(run_multiturn_test())
