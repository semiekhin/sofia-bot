#!/usr/bin/env python3
"""
Batch обработка диалогов для Sofia Bot
Использование:
    # Только эвристики (быстро, бесплатно)
    python batch_process.py ./dialogs/ --output dataset.jsonl
    
    # Эвристики + LLM GPT-5.2 (точно)
    python batch_process.py ./dialogs/ --llm --provider openai --api-key sk-xxx --output dataset.jsonl
"""

import argparse
import json
import time
from pathlib import Path
from dialog_processor import process_file, DialogScore, llm_score_dialog, parse_dialog, decode_rtf, dialog_to_jsonl
from typing import List, Dict

def print_report(results: List[Dict], llm_used: bool = False):
    """Печатает красивый отчёт"""
    
    print("\n" + "="*70)
    print("📊 АНАЛИТИКА ДИАЛОГОВ OAZIS ESTATE")
    print("="*70)
    
    total = len(results)
    llm_evaluated = sum(1 for r in results if r.get('llm_evaluated', False))
    goals_achieved = sum(1 for r in results if r.get('goal_achieved', False))
    
    # Подсчёт по навыкам
    good_for_qualification = sum(1 for r in results if r.get('good_for_qualification', False))
    good_for_closing = sum(1 for r in results if r.get('good_for_closing', False))
    good_for_objections = sum(1 for r in results if r.get('good_for_objections', False))
    good_for_anything = sum(1 for r in results if r.get('good_for_training', False))
    
    # Результаты
    by_result = {}
    for r in results:
        by_result[r['result']] = by_result.get(r['result'], 0) + 1
    
    print(f"\n📁 Всего диалогов: {total}")
    if llm_used:
        print(f"🤖 LLM-оценено: {llm_evaluated}")
    print(f"🎯 Цель достигнута (созвон): {goals_achieved} ({goals_achieved/total*100:.1f}%)")
    
    print(f"\n{'='*70}")
    print("📈 РЕЗУЛЬТАТЫ ДИАЛОГОВ")
    print("="*70)
    result_labels = {
        'созвон': '🎯 Созвон назначен',
        'договорённость': '🤝 Есть договорённость',
        'в_процессе': '⏳ В процессе',
        'отказ': '❌ Отказ',
        'игнор': '👻 Игнор/заглох',
        'неопределён': '❓ Неопределён'
    }
    for res, count in sorted(by_result.items(), key=lambda x: -x[1]):
        pct = count/total*100
        bar = "█" * int(pct/3)
        label = result_labels.get(res, res)
        print(f"   {label:25} {count:3} ({pct:5.1f}%) {bar}")
    
    # === СТАТИСТИКА ПО НАВЫКАМ ===
    if llm_used:
        print(f"\n{'='*70}")
        print("🎓 ПОДХОДЯТ ДЛЯ ОБУЧЕНИЯ (по навыкам)")
        print("="*70)
        
        skills_data = [
            ("📋 Квалификация", good_for_qualification, "good_for_qualification"),
            ("📞 Закрытие на созвон", good_for_closing, "good_for_closing"),
            ("🛡️ Отработка возражений", good_for_objections, "good_for_objections"),
        ]
        
        for label, count, _ in skills_data:
            pct = count/llm_evaluated*100 if llm_evaluated else 0
            bar = "█" * int(pct/3)
            print(f"   {label:30} {count:3} ({pct:5.1f}%) {bar}")
        
        print(f"\n   {'─'*50}")
        print(f"   📦 Всего полезных диалогов:    {good_for_anything:3} ({good_for_anything/llm_evaluated*100:.1f}%)")
        
        # Средние оценки по навыкам
        qual_scores = [r['qualification'].get('score', 0) for r in results if r.get('qualification')]
        close_scores = [r['closing'].get('score', 0) for r in results if r.get('closing')]
        obj_scores = [r['objection_handling'].get('score', 0) for r in results 
                      if r.get('objection_handling') and r['objection_handling'].get('score') is not None]
        
        print(f"\n{'='*70}")
        print("📊 СРЕДНИЕ ОЦЕНКИ ПО НАВЫКАМ")
        print("="*70)
        if qual_scores:
            avg = sum(qual_scores)/len(qual_scores)
            bar = "█" * int(avg)
            print(f"   📋 Квалификация:           {avg:.1f}/10 {bar}")
        if close_scores:
            avg = sum(close_scores)/len(close_scores)
            bar = "█" * int(avg)
            print(f"   📞 Закрытие на созвон:     {avg:.1f}/10 {bar}")
        if obj_scores:
            avg = sum(obj_scores)/len(obj_scores)
            bar = "█" * int(avg)
            print(f"   🛡️ Отработка возражений:   {avg:.1f}/10 {bar}")
    
    # === ДЕТАЛЬНЫЙ РАЗБОР ПО КАЖДОМУ ДИАЛОГУ ===
    print(f"\n{'='*70}")
    print("📋 ДЕТАЛЬНЫЙ РАЗБОР ДИАЛОГОВ")
    print("="*70)
    
    for r in results:
        if not r.get('llm_evaluated'):
            continue
        
        print(f"\n{'─'*70}")
        print(f"📁 {r['file']}")
        print(f"📊 Общая оценка: {r['score']}/10 | Результат: {r['result']} | Цель: {'🎯 Да' if r.get('goal_achieved') else '❌ Нет'}")
        
        # Квалификация
        qual = r.get('qualification', {})
        if qual:
            status = "✅" if qual.get('good_for_training') else "❌"
            score = qual.get('score', '?')
            learned = []
            if qual.get('learned_goal'): learned.append('цель')
            if qual.get('learned_location'): learned.append('локация')
            if qual.get('learned_budget'): learned.append('бюджет')
            learned_str = ', '.join(learned) if learned else 'ничего'
            print(f"\n   📋 КВАЛИФИКАЦИЯ: {score}/10 {status}")
            print(f"      Узнал: {learned_str}")
            if qual.get('verdict'):
                print(f"      → {qual['verdict']}")
        
        # Закрытие
        close = r.get('closing', {})
        if close:
            status = "✅" if close.get('good_for_training') else "❌"
            score = close.get('score', '?')
            actions = []
            if close.get('call_offered'): actions.append('предложил созвон')
            if close.get('call_scheduled'): actions.append('назначил')
            if close.get('value_explained'): actions.append('объяснил ценность')
            actions_str = ', '.join(actions) if actions else 'не предлагал'
            print(f"\n   📞 ЗАКРЫТИЕ НА СОЗВОН: {score}/10 {status}")
            print(f"      Действия: {actions_str}")
            if close.get('verdict'):
                print(f"      → {close['verdict']}")
        
        # Возражения
        obj = r.get('objection_handling', {})
        if obj and obj.get('had_objections'):
            status = "✅" if obj.get('good_for_training') else "❌"
            score = obj.get('score', '?')
            handled = "да" if obj.get('handled_well') else "нет"
            print(f"\n   🛡️ ВОЗРАЖЕНИЯ: {score}/10 {status}")
            print(f"      Были возражения: да, отработал хорошо: {handled}")
            if obj.get('verdict'):
                print(f"      → {obj['verdict']}")
        
        # Ошибки
        if r.get('mistakes'):
            print(f"\n   ❌ Ошибки:")
            for m in r['mistakes'][:3]:
                print(f"      • {m[:75]}")
        
        # Резюме
        if r.get('summary'):
            print(f"\n   💬 {r['summary']}")
    
    # === ФИНАЛЬНОЕ РЕЗЮМЕ ПО НАВЫКАМ ===
    print(f"\n{'='*70}")
    print("📝 ИТОГОВОЕ РЕЗЮМЕ: ЧТО МОЖНО ИСПОЛЬЗОВАТЬ")
    print("="*70)
    
    # Для квалификации
    qual_dialogs = [r for r in results if r.get('good_for_qualification')]
    print(f"\n📋 ДЛЯ ОБУЧЕНИЯ КВАЛИФИКАЦИИ: {len(qual_dialogs)} диалогов")
    for r in qual_dialogs[:5]:
        verdict = r.get('qualification', {}).get('verdict', '')[:60]
        print(f"   ✅ {r['file'][:35]}")
        if verdict:
            print(f"      {verdict}")
    if len(qual_dialogs) > 5:
        print(f"   ... и ещё {len(qual_dialogs) - 5}")
    
    # Для закрытия
    close_dialogs = [r for r in results if r.get('good_for_closing')]
    print(f"\n📞 ДЛЯ ОБУЧЕНИЯ ЗАКРЫТИЯ НА СОЗВОН: {len(close_dialogs)} диалогов")
    for r in close_dialogs[:5]:
        verdict = r.get('closing', {}).get('verdict', '')[:60]
        print(f"   ✅ {r['file'][:35]}")
        if verdict:
            print(f"      {verdict}")
    if len(close_dialogs) > 5:
        print(f"   ... и ещё {len(close_dialogs) - 5}")
    
    # Для возражений
    obj_dialogs = [r for r in results if r.get('good_for_objections')]
    print(f"\n🛡️ ДЛЯ ОБУЧЕНИЯ ВОЗРАЖЕНИЙ: {len(obj_dialogs)} диалогов")
    for r in obj_dialogs[:5]:
        verdict = r.get('objection_handling', {}).get('verdict', '')[:60]
        print(f"   ✅ {r['file'][:35]}")
        if verdict:
            print(f"      {verdict}")
    if len(obj_dialogs) > 5:
        print(f"   ... и ещё {len(obj_dialogs) - 5}")
    
    # Не подходят ни для чего
    useless = [r for r in results if r.get('llm_evaluated') and not r.get('good_for_training')]
    print(f"\n❌ НЕ ПОДХОДЯТ НИ ДЛЯ ЧЕГО: {len(useless)} диалогов")

def save_jsonl(results: List[Dict], output_path: str, min_score: int = 5):
    """Сохраняет хорошие диалоги в JSONL"""
    
    good_dialogs = [r for r in results if r['score'] >= min_score and r['jsonl']]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for r in good_dialogs:
            f.write(json.dumps(r['jsonl'], ensure_ascii=False) + '\n')
    
    print(f"\n💾 Сохранено {len(good_dialogs)} диалогов в {output_path}")
    print(f"   (score >= {min_score})")

def main():
    parser = argparse.ArgumentParser(description='Batch обработка диалогов')
    parser.add_argument('input', help='Путь к папке с диалогами или файлу')
    parser.add_argument('--min-score', type=int, default=5, help='Минимальный score для включения в датасет')
    parser.add_argument('--output', '-o', default='dataset.jsonl', help='Путь для сохранения JSONL')
    parser.add_argument('--managers', nargs='+', default=['София', 'Сергей', 'Виктория', 'Оксана', 'Юлия', 'Игорь'],
                       help='Имена менеджеров')
    
    # LLM параметры
    parser.add_argument('--llm', action='store_true', help='Использовать LLM для оценки кандидатов')
    parser.add_argument('--provider', choices=['openai', 'anthropic'], default='openai', help='LLM провайдер')
    parser.add_argument('--api-key', help='API ключ (или переменная окружения OPENAI_API_KEY / ANTHROPIC_API_KEY)')
    parser.add_argument('--model', help='Модель (default: gpt-5.2 или claude-3-haiku)')
    parser.add_argument('--llm-threshold', type=int, default=4, help='Минимальный эвристический score для LLM-оценки')
    
    args = parser.parse_args()
    
    # Получаем API key
    api_key = args.api_key
    if args.llm and not api_key:
        import os
        if args.provider == 'openai':
            api_key = os.environ.get('OPENAI_API_KEY')
        else:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
        
        if not api_key:
            print(f"❌ Нужен API ключ! Укажите --api-key или установите переменную окружения")
            return
    
    input_path = Path(args.input)
    results = []
    
    # Собираем файлы
    if input_path.is_file():
        files = [input_path]
    else:
        files = list(input_path.glob('*.txt')) + list(input_path.glob('*.rtf'))
    
    print(f"🔍 Найдено файлов: {len(files)}")
    if args.llm:
        print(f"🤖 LLM-оценка включена: {args.provider} (threshold >= {args.llm_threshold})")
    
    # Обрабатываем
    llm_count = 0
    for i, filepath in enumerate(files, 1):
        try:
            messages, score, jsonl_data = process_file(str(filepath), args.managers)
            
            result_entry = {
                'file': filepath.name,
                'messages_count': len(messages),
                'heuristic_score': score.total,
                'score': score.total,
                'result': score.result,
                'goal_achieved': False,
                'qualification': {},
                'closing': {},
                'objection_handling': {},
                'communication': {},
                'good_for_qualification': False,
                'good_for_closing': False,
                'good_for_objections': False,
                'good_for_training': False,
                'strengths': [],
                'mistakes': [],
                'summary': '',
                'llm_evaluated': False,
                'jsonl': None
            }
            
            # LLM-оценка для кандидатов
            if args.llm and score.total >= args.llm_threshold:
                try:
                    print(f"   🤖 LLM-оценка: {filepath.name[:30]}...")
                    llm_result = llm_score_dialog(messages, api_key, args.provider, args.model)
                    
                    result_entry['score'] = llm_result.get('overall_score', score.total)
                    result_entry['result'] = llm_result.get('result', score.result)
                    result_entry['goal_achieved'] = llm_result.get('goal_achieved', False)
                    
                    # Оценки по навыкам
                    result_entry['qualification'] = llm_result.get('qualification', {})
                    result_entry['closing'] = llm_result.get('closing', {})
                    result_entry['objection_handling'] = llm_result.get('objection_handling', {})
                    result_entry['communication'] = llm_result.get('communication', {})
                    
                    result_entry['strengths'] = llm_result.get('strengths', [])
                    result_entry['mistakes'] = llm_result.get('mistakes', [])
                    result_entry['summary'] = llm_result.get('summary', '')
                    
                    # Флаги для обучения по навыкам
                    result_entry['good_for_qualification'] = result_entry['qualification'].get('good_for_training', False)
                    result_entry['good_for_closing'] = result_entry['closing'].get('good_for_training', False)
                    result_entry['good_for_objections'] = result_entry['objection_handling'].get('good_for_training', False)
                    
                    # Общий флаг — подходит хотя бы для чего-то
                    result_entry['good_for_training'] = (
                        result_entry['good_for_qualification'] or 
                        result_entry['good_for_closing'] or 
                        result_entry['good_for_objections']
                    )
                    
                    result_entry['llm_evaluated'] = True
                    llm_count += 1
                    
                    # === ВЫВОД РЕЗУЛЬТАТА СРАЗУ ===
                    goal_icon = "🎯" if result_entry['goal_achieved'] else "❌"
                    qual = result_entry['qualification']
                    close = result_entry['closing']
                    obj = result_entry['objection_handling']
                    
                    qual_score = qual.get('score', '-')
                    qual_ok = "✅" if result_entry['good_for_qualification'] else "❌"
                    close_score = close.get('score', '-')
                    close_ok = "✅" if result_entry['good_for_closing'] else "❌"
                    obj_score = obj.get('score', '-') if obj.get('had_objections') else "—"
                    obj_ok = "✅" if result_entry['good_for_objections'] else ("❌" if obj.get('had_objections') else "—")
                    
                    print(f"      📊 {result_entry['score']}/10 | {result_entry['result']} | Цель: {goal_icon}")
                    print(f"      📋 Квалиф: {qual_score}/10 {qual_ok} | 📞 Закрытие: {close_score}/10 {close_ok} | 🛡️ Возраж: {obj_score} {obj_ok}")
                    
                    if result_entry['good_for_training']:
                        skills = []
                        if result_entry['good_for_qualification']: skills.append("квалификация")
                        if result_entry['good_for_closing']: skills.append("закрытие")
                        if result_entry['good_for_objections']: skills.append("возражения")
                        print(f"      ✅ ПОДХОДИТ для: {', '.join(skills)}")
                    else:
                        print(f"      ❌ Не подходит для обучения")
                    
                    if result_entry['summary']:
                        print(f"      💬 {result_entry['summary'][:80]}...")
                    print()
                    
                    # Небольшая пауза чтобы не превысить rate limit
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"   ⚠️ LLM ошибка: {e}")
            
            # Добавляем jsonl если score достаточный
            final_score = result_entry['score']
            if final_score >= args.min_score:
                # Для LLM-оценённых проверяем good_for_training
                if result_entry['llm_evaluated']:
                    if result_entry.get('good_for_training', False):
                        result_entry['jsonl'] = jsonl_data
                else:
                    result_entry['jsonl'] = jsonl_data
            
            results.append(result_entry)
            
            # Прогресс
            if i % 10 == 0:
                print(f"   Обработано: {i}/{len(files)}")
                
        except Exception as e:
            print(f"   ❌ Ошибка в {filepath.name}: {e}")
    
    # Сортируем по score
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    # Отчёт
    print_report(results, llm_used=args.llm)
    
    # Сохраняем
    save_jsonl(results, args.output, args.min_score)
    
    # Также сохраняем полный отчёт
    report_path = args.output.replace('.jsonl', '_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        # Убираем jsonl из отчёта (слишком большой)
        report_results = [{k: v for k, v in r.items() if k != 'jsonl'} for r in results]
        json.dump(report_results, f, ensure_ascii=False, indent=2)
    print(f"📋 Отчёт сохранён в {report_path}")
    
    if args.llm:
        print(f"\n🤖 LLM-оценено диалогов: {llm_count}")

if __name__ == '__main__':
    main()
