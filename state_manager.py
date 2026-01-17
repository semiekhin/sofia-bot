"""
state_manager.py — управление состоянием клиента
=================================================
Хранит квалификационные данные с разделением на:
- confirmed: клиент явно подтвердил
- mentioned: клиент упомянул, но не подтвердил
"""

import sqlite3
import json
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime

ConfidenceLevel = Literal["confirmed", "mentioned"]


@dataclass
class ClientState:
    """Состояние клиента в диалоге"""
    user_id: int
    
    # Подтверждённые факты
    goal: Optional[str] = None                    # 'investment' | 'personal'
    goal_confidence: Optional[ConfidenceLevel] = None
    
    location: Optional[str] = None                # 'sochi' | 'crimea' | 'altai' | etc
    location_confidence: Optional[ConfidenceLevel] = None
    
    budget: Optional[int] = None                  # в рублях
    budget_confidence: Optional[ConfidenceLevel] = None
    
    payment_type: Optional[str] = None            # 'full' | 'mortgage' | 'installment'
    payment_type_confidence: Optional[ConfidenceLevel] = None
    
    first_payment: Optional[int] = None           # в рублях (для ипотеки)
    first_payment_confidence: Optional[ConfidenceLevel] = None
    
    lpr: Optional[str] = None                     # 'alone' | 'with_spouse' | 'with_partner'
    lpr_confidence: Optional[ConfidenceLevel] = None
    
    # Статус диалога
    meeting_agreed: bool = False
    meeting_datetime: Optional[str] = None
    materials_sent: bool = False
    call_refused: bool = False  # Клиент отказался от созвона
    
    # Временные флаги (сбрасываются после обработки)
    current_question_type: Optional[str] = None   # 'price' | 'availability' | 'process'
    current_objection: Optional[str] = None       # 'expensive' | 'think' | 'busy'
    wants_materials: bool = False
    
    # Упоминания (не подтверждённые)
    mentioned_location: Optional[str] = None
    mentioned_price: Optional[int] = None
    
    # Мета
    updated_at: Optional[datetime] = None
    qualification_score: float = 0.0
    
    # Счётчики попыток по слотам (защита от повторов)
    slot_attempts: dict = field(default_factory=lambda: {
        "goal": {"ask": 0, "help": 0},
        "location": {"ask": 0, "help": 0},
        "budget": {"ask": 0, "help": 0},
        "payment_type": {"ask": 0, "help": 0},
        "first_payment": {"ask": 0, "help": 0},
        "lpr": {"ask": 0, "help": 0}
    })
    
    def is_qualified(self) -> bool:
        """Проверка полноты квалификации (минимум для созвона)"""
        return all([
            self.goal is not None and self.goal_confidence == "confirmed",
            self.location is not None and self.location_confidence == "confirmed",
            self.budget is not None and self.budget_confidence == "confirmed"
        ])
    
    def is_fully_qualified(self) -> bool:
        """Полная квалификация включая LPR"""
        return self.is_qualified() and (
            self.lpr is not None and self.lpr_confidence == "confirmed"
        )
    
    def get_missing_fields(self) -> list[str]:
        """Возвращает список неподтверждённых обязательных полей"""
        missing = []
        if not self.goal or self.goal_confidence != "confirmed":
            missing.append("goal")
        if not self.location or self.location_confidence != "confirmed":
            missing.append("location")
        if not self.budget or self.budget_confidence != "confirmed":
            missing.append("budget")
        if self.payment_type == "mortgage" and not self.first_payment:
            missing.append("first_payment")
        if not self.lpr or self.lpr_confidence != "confirmed":
            missing.append("lpr")
        return missing
    
    def get_next_question(self) -> Optional[str]:
        """Возвращает следующий вопрос для квалификации"""
        missing = self.get_missing_fields()
        if not missing:
            return None
        # Приоритет: goal → location → budget → payment → first_payment → lpr
        priority = ["goal", "location", "budget", "payment_type", "first_payment", "lpr"]
        for field in priority:
            if field in missing:
                return field
        return missing[0] if missing else None
    
    def calculate_qualification_score(self) -> float:
        """Расчёт скора квалификации 0.0 - 1.0"""
        fields = ["goal", "location", "budget", "payment_type", "lpr"]
        confirmed = 0
        mentioned = 0
        
        for f in fields:
            conf = getattr(self, f"{f}_confidence", None)
            if conf == "confirmed":
                confirmed += 1
            elif conf == "mentioned":
                mentioned += 1
        
        # confirmed = 1.0, mentioned = 0.3
        score = (confirmed * 1.0 + mentioned * 0.3) / len(fields)
        return min(score, 1.0)
    
    def to_dict(self) -> dict:
        """Конвертация в словарь для логирования/промпта"""
        return {
            "goal": self.goal,
            "goal_confidence": self.goal_confidence,
            "location": self.location,
            "location_confidence": self.location_confidence,
            "budget": self.budget,
            "budget_confidence": self.budget_confidence,
            "payment_type": self.payment_type,
            "payment_type_confidence": self.payment_type_confidence,
            "first_payment": self.first_payment,
            "lpr": self.lpr,
            "lpr_confidence": self.lpr_confidence,
            "meeting_agreed": self.meeting_agreed,
            "meeting_datetime": self.meeting_datetime,
            "qualification_score": self.qualification_score,
            # "is_qualified": вычисляемое поле, не сохраняем
            # "missing_fields": вычисляемое поле, не сохраняем
        }
    
    def summary(self) -> str:
        """Краткая сводка для промпта"""
        parts = []
        if self.goal:
            parts.append(f"Цель: {self.goal} ({self.goal_confidence})")
        if self.location:
            parts.append(f"Локация: {self.location} ({self.location_confidence})")
        if self.budget:
            parts.append(f"Бюджет: {self.budget/1_000_000:.1f} млн ({self.budget_confidence})")
        if self.payment_type:
            parts.append(f"Оплата: {self.payment_type} ({self.payment_type_confidence})")
        if self.lpr:
            parts.append(f"ЛПР: {self.lpr} ({self.lpr_confidence})")
        if self.meeting_agreed:
            parts.append(f"Созвон: {self.meeting_datetime or 'согласован'}")
        
        if not parts:
            return "Квалификация: не начата"
        
        return f"Квалификация ({self.qualification_score:.0%}): " + ", ".join(parts)


class StateManager:
    """Менеджер состояния клиентов с персистентностью в SQLite"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Создание таблицы если не существует"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_state (
                user_id INTEGER PRIMARY KEY,
                
                goal TEXT,
                goal_confidence TEXT,
                
                location TEXT,
                location_confidence TEXT,
                
                budget INTEGER,
                budget_confidence TEXT,
                
                payment_type TEXT,
                payment_type_confidence TEXT,
                
                first_payment INTEGER,
                first_payment_confidence TEXT,
                
                lpr TEXT,
                lpr_confidence TEXT,
                
                meeting_agreed BOOLEAN DEFAULT 0,
                meeting_datetime TEXT,
                materials_sent BOOLEAN DEFAULT 0,
                
                current_question_type TEXT,
                current_objection TEXT,
                wants_materials BOOLEAN DEFAULT 0,
                
                mentioned_location TEXT,
                mentioned_price INTEGER,
                
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                qualification_score REAL DEFAULT 0.0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_client_state_user ON client_state(user_id)")
        conn.commit()
        conn.close()
    
    def get_state(self, user_id: int) -> ClientState:
        """Получить состояние клиента (создаёт новое если нет)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM client_state WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return ClientState(user_id=user_id)
        
        state = ClientState(
            user_id=row["user_id"],
            goal=row["goal"],
            goal_confidence=row["goal_confidence"],
            location=row["location"],
            location_confidence=row["location_confidence"],
            budget=row["budget"],
            budget_confidence=row["budget_confidence"],
            payment_type=row["payment_type"],
            payment_type_confidence=row["payment_type_confidence"],
            first_payment=row["first_payment"],
            first_payment_confidence=row["first_payment_confidence"],
            lpr=row["lpr"],
            lpr_confidence=row["lpr_confidence"],
            meeting_agreed=bool(row["meeting_agreed"]),
            meeting_datetime=row["meeting_datetime"],
            materials_sent=bool(row["materials_sent"]),
            call_refused=bool(row["call_refused"]) if "call_refused" in row.keys() else False,
            current_question_type=row["current_question_type"],
            current_objection=row["current_objection"],
            wants_materials=bool(row["wants_materials"]),
            mentioned_location=row["mentioned_location"],
            mentioned_price=row["mentioned_price"],
            qualification_score=row["qualification_score"] or 0.0,
            slot_attempts=json.loads(row["slot_attempts"]) if row["slot_attempts"] else {}
        )
        return state
    
    def update_state(self, user_id: int, updates: dict) -> ClientState:
        """Обновить состояние клиента"""
        state = self.get_state(user_id)
        
        # Поля которые нельзя перезаписывать (методы и вычисляемые)
        PROTECTED_FIELDS = {'is_qualified', 'is_fully_qualified', 'get_missing_fields', 
                           'get_next_question', 'calculate_qualification_score', 
                           'to_dict', 'summary', 'missing_fields'}
        
        # Применяем обновления
        for key, value in updates.items():
            if key in PROTECTED_FIELDS:
                continue  # Пропускаем вычисляемые поля
            if hasattr(state, key) and not callable(getattr(state, key)):
                setattr(state, key, value)
        
        # Пересчитываем скор
        state.qualification_score = state.calculate_qualification_score()
        state.updated_at = datetime.now()
        
        # Сохраняем
        self._save_state(state)
        return state
    
    def _save_state(self, state: ClientState):
        """Сохранить состояние в БД"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO client_state (
                user_id, goal, goal_confidence, location, location_confidence,
                budget, budget_confidence, payment_type, payment_type_confidence,
                first_payment, first_payment_confidence, lpr, lpr_confidence,
                meeting_agreed, meeting_datetime, materials_sent, call_refused,
                current_question_type, current_objection, wants_materials,
                mentioned_location, mentioned_price, updated_at, qualification_score,
                slot_attempts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.user_id, state.goal, state.goal_confidence,
            state.location, state.location_confidence,
            state.budget, state.budget_confidence,
            state.payment_type, state.payment_type_confidence,
            state.first_payment, state.first_payment_confidence,
            state.lpr, state.lpr_confidence,
            state.meeting_agreed, state.meeting_datetime, state.materials_sent, state.call_refused,
            state.current_question_type, state.current_objection, state.wants_materials,
            state.mentioned_location, state.mentioned_price,
            state.updated_at, state.qualification_score,
            json.dumps(state.slot_attempts)
        ))
        conn.commit()
        conn.close()
    
    def reset_state(self, user_id: int):
        """Сбросить состояние клиента"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM client_state WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def clear_temporary_flags(self, user_id: int):
        """Очистить временные флаги после обработки сообщения"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE client_state 
            SET current_question_type = NULL,
                current_objection = NULL,
                wants_materials = 0
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
    
    def set_meeting_agreed(self, user_id: int, datetime_str: str = None):
        """Отметить что созвон согласован"""
        self.update_state(user_id, {
            "meeting_agreed": True,
            "meeting_datetime": datetime_str
        })


# === ТЕСТЫ ===

def test_state_manager():
    """Тест StateManager"""
    import tempfile
    import os
    
    # Создаём временную БД
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    try:
        sm = StateManager(db_path)
        
        # Тест 1: новый клиент
        state = sm.get_state(123)
        assert state.user_id == 123
        assert state.goal is None
        assert state.is_qualified() == False
        print("✅ Тест 1: новый клиент")
        
        # Тест 2: обновление
        state = sm.update_state(123, {
            "goal": "investment",
            "goal_confidence": "confirmed",
            "location": "sochi",
            "location_confidence": "mentioned"
        })
        assert state.goal == "investment"
        assert state.location_confidence == "mentioned"
        print("✅ Тест 2: обновление")
        
        # Тест 3: персистентность
        state2 = sm.get_state(123)
        assert state2.goal == "investment"
        assert state2.location == "sochi"
        print("✅ Тест 3: персистентность")
        
        # Тест 4: квалификация
        sm.update_state(123, {
            "location_confidence": "confirmed",
            "budget": 10_000_000,
            "budget_confidence": "confirmed"
        })
        state3 = sm.get_state(123)
        assert state3.is_qualified() == True
        print("✅ Тест 4: квалификация")
        
        # Тест 5: missing fields
        missing = state3.get_missing_fields()
        assert "lpr" in missing
        assert "goal" not in missing
        print("✅ Тест 5: missing fields")
        
        # Тест 6: score
        score = state3.calculate_qualification_score()
        assert score > 0.5
        print(f"✅ Тест 6: score = {score:.2f}")
        
        # Тест 7: summary
        summary = state3.summary()
        assert "investment" in summary
        assert "sochi" in summary
        print(f"✅ Тест 7: summary = {summary[:60]}...")
        
        print("\n✅ Все тесты пройдены!")
        
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_state_manager()
