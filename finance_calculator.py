"""
Финансовый калькулятор Sofia-GPT v1.0
Сравнение инвестиций: недвижимость vs депозит

Использование:
    from finance_calculator import compare_investments, format_comparison_for_prompt
    
    result = compare_investments(
        amount=10_000_000,
        construction_years=2,  # 2026-2027 стройка
        total_years=5          # до конца 2030
    )
    
    prompt_text = format_comparison_for_prompt(result)
"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path


def get_finance_data_path() -> str:
    """Найти finance_data.json"""
    possible_paths = [
        Path(__file__).parent / "finance_data.json",
        Path("/opt/sofia-gpt/finance_data.json"),
        Path("./finance_data.json")
    ]
    for p in possible_paths:
        if p.exists():
            return str(p)
    raise FileNotFoundError("finance_data.json not found")


def load_finance_data() -> dict:
    """Загрузить финансовые данные"""
    with open(get_finance_data_path(), 'r', encoding='utf-8') as f:
        return json.load(f)


@dataclass
class YearResult:
    """Результат за один год"""
    year: int
    phase: str
    value_start: float
    growth_rate: float
    growth_amount: float
    rental_income: float
    value_end: float


@dataclass  
class RealEstateResult:
    """Результат расчёта недвижимости"""
    initial_amount: float
    years: List[YearResult]
    final_value: float
    total_rental: float
    total_capital: float
    total_profit: float
    profit_percent: float


@dataclass
class DepositYearResult:
    """Результат депозита за год"""
    year: int
    rate: float
    capital_start: float
    interest: float
    capital_end: float


@dataclass
class DepositResult:
    """Результат расчёта депозита"""
    initial_amount: float
    years: List[DepositYearResult]
    final_capital_gross: float
    total_interest: float
    tax_amount: float
    final_capital_net: float
    total_profit: float
    profit_percent: float


@dataclass
class ComparisonResult:
    """Результат сравнения"""
    amount: float
    total_years: int
    construction_years: int
    completion_year: int
    real_estate: RealEstateResult
    deposit: DepositResult
    advantage_amount: float
    advantage_percent: float


def calculate_real_estate(
    amount: float,
    start_year: int = 2026,
    construction_years: int = 2,
    total_years: int = 5,
    data: Optional[dict] = None
) -> RealEstateResult:
    """Расчёт доходности недвижимости"""
    if data is None:
        data = load_finance_data()
    
    re_data = data["real_estate"]
    growth_construction = re_data["growth_construction"]
    growth_ready = re_data["growth_ready"]
    rental_yield = re_data["rental_yield_net"]
    
    years_results = []
    current_value = amount
    total_rental = 0.0
    
    for i in range(total_years):
        year = start_year + i
        is_construction = i < construction_years
        
        if is_construction:
            phase = "construction"
            growth_rate = growth_construction
            rental = 0.0
        else:
            phase = "ready"
            growth_rate = growth_ready
            rental = current_value * rental_yield
            total_rental += rental
        
        growth_amount = current_value * growth_rate
        value_end = current_value + growth_amount
        
        years_results.append(YearResult(
            year=year,
            phase=phase,
            value_start=current_value,
            growth_rate=growth_rate,
            growth_amount=growth_amount,
            rental_income=rental,
            value_end=value_end
        ))
        
        current_value = value_end
    
    total_capital = current_value + total_rental
    total_profit = total_capital - amount
    profit_percent = (total_profit / amount) * 100
    
    return RealEstateResult(
        initial_amount=amount,
        years=years_results,
        final_value=current_value,
        total_rental=total_rental,
        total_capital=total_capital,
        total_profit=total_profit,
        profit_percent=profit_percent
    )


def calculate_deposit(
    amount: float,
    start_year: int = 2026,
    total_years: int = 5,
    data: Optional[dict] = None
) -> DepositResult:
    """Расчёт доходности депозита с учётом налога"""
    if data is None:
        data = load_finance_data()
    
    dep_data = data["deposit"]
    cb_rates = data["cb_key_rate"]["forecast_avg"]
    spread = dep_data["spread_to_key_rate"]
    tax_threshold_base = dep_data["tax"]["threshold_base"]
    tax_rate = dep_data["tax"]["rate"]
    
    years_results = []
    current_capital = amount
    total_interest = 0.0
    total_tax = 0.0
    
    for i in range(total_years):
        year = start_year + i
        year_str = str(year)
        
        if year_str in cb_rates:
            key_rate = cb_rates[year_str]
        else:
            key_rate = cb_rates.get("2030", 7.5)
        
        deposit_rate = (key_rate + spread) / 100
        interest = current_capital * deposit_rate
        total_interest += interest
        
        tax_free = tax_threshold_base * (key_rate / 100)
        taxable = max(0, interest - tax_free)
        year_tax = taxable * tax_rate
        total_tax += year_tax
        
        capital_end = current_capital + interest
        
        years_results.append(DepositYearResult(
            year=year,
            rate=deposit_rate * 100,
            capital_start=current_capital,
            interest=interest,
            capital_end=capital_end
        ))
        
        current_capital = capital_end
    
    final_net = current_capital - total_tax
    total_profit = final_net - amount
    profit_percent = (total_profit / amount) * 100
    
    return DepositResult(
        initial_amount=amount,
        years=years_results,
        final_capital_gross=current_capital,
        total_interest=total_interest,
        tax_amount=total_tax,
        final_capital_net=final_net,
        total_profit=total_profit,
        profit_percent=profit_percent
    )


def compare_investments(
    amount: float,
    construction_years: int = 2,
    total_years: int = 5,
    start_year: int = 2026
) -> ComparisonResult:
    """Сравнить недвижимость и депозит"""
    data = load_finance_data()
    
    real_estate = calculate_real_estate(
        amount=amount,
        start_year=start_year,
        construction_years=construction_years,
        total_years=total_years,
        data=data
    )
    
    deposit = calculate_deposit(
        amount=amount,
        start_year=start_year,
        total_years=total_years,
        data=data
    )
    
    advantage = real_estate.total_capital - deposit.final_capital_net
    advantage_pct = real_estate.profit_percent - deposit.profit_percent
    
    return ComparisonResult(
        amount=amount,
        total_years=total_years,
        construction_years=construction_years,
        completion_year=start_year + construction_years,
        real_estate=real_estate,
        deposit=deposit,
        advantage_amount=advantage,
        advantage_percent=advantage_pct
    )


def format_millions(value: float) -> str:
    """Форматировать в миллионы"""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн"
    elif value >= 1_000:
        return f"{value / 1_000:.0f} тыс"
    else:
        return f"{value:.0f}"


def format_comparison_for_prompt(result: ComparisonResult) -> str:
    """Форматировать результат для включения в промпт генератора"""
    re = result.real_estate
    dep = result.deposit
    
    text = f"""ФИНАНСОВЫЙ РАСЧЁТ (сумма {format_millions(result.amount)} ₽, {result.total_years} лет):

📊 НЕДВИЖИМОСТЬ (ввод в {result.completion_year}):
- Стройка ({result.construction_years} года): рост +20%/год
- Готовый объект: рост +10%/год + аренда 10%/год
- Стоимость через {result.total_years} лет: {format_millions(re.final_value)} ₽
- Доход от аренды: {format_millions(re.total_rental)} ₽
- ИТОГО капитал: {format_millions(re.total_capital)} ₽
- Прибыль: +{format_millions(re.total_profit)} ₽ (+{re.profit_percent:.0f}%)

💰 ДЕПОЗИТ:
- Ставка: от 13% (2026) до 6.5% (2030) — снижается вслед за ЦБ
- Капитал через {result.total_years} лет: {format_millions(dep.final_capital_gross)} ₽
- Налог: -{format_millions(dep.tax_amount)} ₽
- ИТОГО после налога: {format_millions(dep.final_capital_net)} ₽
- Чистая прибыль: +{format_millions(dep.total_profit)} ₽ (+{dep.profit_percent:.0f}%)

🏆 ПРЕИМУЩЕСТВО НЕДВИЖИМОСТИ: +{format_millions(result.advantage_amount)} ₽"""
    return text


def format_short_comparison(result: ComparisonResult) -> str:
    """Краткая версия для разговора"""
    re = result.real_estate
    dep = result.deposit
    
    return f"""За {result.total_years} лет при вложении {format_millions(result.amount)} ₽:
- Недвижимость: ~{format_millions(re.total_capital)} ₽ (+{re.profit_percent:.0f}%)
- Депозит: ~{format_millions(dep.final_capital_net)} ₽ (+{dep.profit_percent:.0f}%)
- Разница: +{format_millions(result.advantage_amount)} ₽ в пользу недвижимости"""


def get_current_rates_info() -> str:
    """Получить текущую информацию о ставках для диалога"""
    data = load_finance_data()
    cb_rate = data["cb_key_rate"]["current"]
    dep_rates = data["deposit"]["current_rates"]
    
    return f"""Текущая ключевая ставка ЦБ: {cb_rate}%
Ставки по депозитам: {dep_rates['3_months']}% (3 мес), {dep_rates['6_months']}% (6 мес), {dep_rates['12_months']}% (год)
Прогноз ЦБ: снижение до 7.5-8% к 2027-2028"""


if __name__ == "__main__":
    print("=== Тест финансового калькулятора ===\n")
    result = compare_investments(amount=10_000_000, construction_years=2, total_years=5)
    print(format_comparison_for_prompt(result))
    print("\n" + "="*50 + "\n")
    print("Краткая версия:")
    print(format_short_comparison(result))


def add_finance_context(action_context: dict, extraction: dict, client_state) -> dict:
    """Добавляет финансовый контекст в action_context если нужно"""
    finance_interest = extraction.get("finance_interest", False)
    deposit_mention = extraction.get("deposit_mention", False)
    
    # Сохраняем флаг в state если клиент проявил интерес
    if finance_interest or deposit_mention:
        client_state.finance_interested = True
    
    # Проверяем и текущее сообщение, и сохранённый флаг
    finance_flag = finance_interest or deposit_mention or getattr(client_state, 'finance_interested', False)
    
    if finance_flag and client_state.budget and client_state.budget > 0:
        try:
            fin_result = compare_investments(
                amount=client_state.budget,
                construction_years=2,
                total_years=5
            )
            action_context["finance_context"] = format_short_comparison(fin_result)
            action_context["finance_hook"] = True
            print(f"💰 Finance calc: {client_state.budget/1_000_000:.1f} млн")
            return action_context
        except Exception as e:
            pass
    elif finance_flag and not client_state.budget:
        action_context["finance_hook"] = True
        action_context["finance_context"] = "Клиент интересуется доходностью, но бюджет пока не известен. Дай краткую информацию о доходности и спроси бюджет."
    
    return action_context
