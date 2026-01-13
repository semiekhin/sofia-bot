# rag_module.py — Векторный RAG для Sofia Bot
# ChromaDB + OpenAI text-embedding-3-small
# Версия: 2.0

import json
import os
from typing import List, Dict, Optional
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# Путь к датасету
RAG_DATA_PATH = Path(__file__).parent / "rag_training_data.json"
CHROMA_PATH = Path(__file__).parent / "chroma_db"

# OpenAI API ключ (из .env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Глобальные объекты
_collection = None
_dataset_cache = None


def init_vector_store() -> bool:
    """
    Инициализирует векторное хранилище ChromaDB.
    Вызывать один раз при старте бота.
    """
    global _collection, _dataset_cache, OPENAI_API_KEY
    
    # Перечитываем ключ (мог загрузиться после import)
    if not OPENAI_API_KEY:
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY не установлен! Векторный RAG не будет работать.")
        return False
    
    try:
        # OpenAI embedding function
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=OPENAI_API_KEY,
            model_name="text-embedding-3-small"  # $0.02 / 1M токенов, 1536 dimensions
        )
        
        # Создаём или открываем ChromaDB
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        
        # Проверяем, есть ли уже коллекция
        existing_collections = [c.name for c in client.list_collections()]
        
        if "sofia_examples" in existing_collections:
            _collection = client.get_collection(
                name="sofia_examples",
                embedding_function=openai_ef
            )
            count = _collection.count()
            print(f"✅ Векторный RAG загружен: {count} примеров")
            return True
        
        # Создаём новую коллекцию и загружаем данные
        _collection = client.create_collection(
            name="sofia_examples",
            embedding_function=openai_ef,
            metadata={"hnsw:space": "cosine"}  # Косинусное расстояние
        )
        
        # Загружаем датасет
        dataset = load_dataset()
        exchanges = get_all_exchanges_raw(dataset)
        
        if not exchanges:
            print("⚠️ Датасет пустой, нечего индексировать")
            return False
        
        # Подготавливаем данные для ChromaDB
        documents = []
        metadatas = []
        ids = []
        
        for i, ex in enumerate(exchanges):
            # Текст для эмбеддинга: сообщение клиента + контекст
            doc_text = f"Клиент: {ex.get('client', '')}"
            
            documents.append(doc_text)
            metadatas.append({
                "stage": ex.get("stage", "UNKNOWN"),
                "substage": ex.get("substage", "general"),
                "manager_response": ex.get("manager", ""),
                "quality": ex.get("quality", "unknown"),
                "note": ex.get("note", "")[:500],  # Ограничиваем длину
                "dialog_id": ex.get("dialog_id", ""),
            })
            ids.append(f"ex_{i}")
        
        # Добавляем в ChromaDB (батчами по 100)
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            
            _collection.add(
                documents=batch_docs,
                metadatas=batch_meta,
                ids=batch_ids
            )
            print(f"📦 Добавлено {min(i+batch_size, len(documents))}/{len(documents)} примеров")
        
        print(f"✅ Векторный RAG создан: {len(documents)} примеров проиндексировано")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации векторного RAG: {e}")
        import traceback
        traceback.print_exc()
        return False


def load_dataset() -> Dict:
    """Загружает RAG датасет из JSON."""
    global _dataset_cache
    
    if _dataset_cache is not None:
        return _dataset_cache
    
    try:
        with open(RAG_DATA_PATH, "r", encoding="utf-8") as f:
            _dataset_cache = json.load(f)
        return _dataset_cache
    except FileNotFoundError:
        print(f"⚠️ RAG датасет не найден: {RAG_DATA_PATH}")
        return {"dialogs": []}
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга RAG датасета: {e}")
        return {"dialogs": []}


def get_all_exchanges_raw(dataset: Dict = None) -> List[Dict]:
    """Возвращает все exchanges из всех диалогов."""
    if dataset is None:
        dataset = load_dataset()
    
    exchanges = []
    
    for dialog in dataset.get("dialogs", []):
        dialog_id = dialog.get("dialog_id", "unknown")
        client_profile = dialog.get("client_profile", {})
        
        for exchange in dialog.get("exchanges", []):
            exchange_copy = exchange.copy()
            exchange_copy["dialog_id"] = dialog_id
            exchange_copy["client_name"] = client_profile.get("name", "Клиент")
            exchanges.append(exchange_copy)
    
    return exchanges


def search_examples(
    stage: str,
    client_message: str,
    limit: int = 3,
    quality_filter: Optional[List[str]] = None
) -> List[Dict]:
    """
    Векторный поиск примеров по сообщению клиента.
    
    Args:
        stage: Этап продаж (используется как фильтр)
        client_message: Сообщение клиента для поиска похожих
        limit: Максимум примеров
        quality_filter: Фильтр по качеству ["excellent", "good"]
    
    Returns:
        Список примеров с полями: stage, substage, client, manager, quality, note
    """
    global _collection
    
    if quality_filter is None:
        quality_filter = ["excellent", "good"]
    
    # Если коллекция не инициализирована, пробуем инициализировать
    if _collection is None:
        if not init_vector_store():
            print("⚠️ Векторный RAG недоступен, возвращаю пустой результат")
            return []
    
    try:
        # Формируем запрос
        query_text = f"Клиент: {client_message}"
        
        # Фильтр по этапу и качеству
        where_filter = {
            "$and": [
                {"stage": {"$eq": stage}},
                {"quality": {"$in": quality_filter}}
            ]
        }
        
        # Поиск
        results = _collection.query(
            query_texts=[query_text],
            n_results=limit * 2,  # Берём больше, потом отфильтруем
            where=where_filter,
            include=["metadatas", "documents", "distances"]
        )
        
        # Если по этапу мало результатов, ищем без фильтра этапа
        if not results["ids"][0]:
            results = _collection.query(
                query_texts=[query_text],
                n_results=limit,
                where={"quality": {"$in": quality_filter}},
                include=["metadatas", "documents", "distances"]
            )
        
        # Форматируем результаты
        examples = []
        for i, doc_id in enumerate(results["ids"][0][:limit]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0
            
            examples.append({
                "id": doc_id,
                "stage": metadata.get("stage", ""),
                "substage": metadata.get("substage", ""),
                "client": results["documents"][0][i].replace("Клиент: ", ""),
                "manager": metadata.get("manager_response", ""),
                "quality": metadata.get("quality", ""),
                "note": metadata.get("note", ""),
                "similarity": round(1 - distance, 3)  # Косинусное сходство
            })
        
        return examples
        
    except Exception as e:
        print(f"❌ Ошибка поиска в векторном RAG: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_by_substage(
    stage: str,
    substage: str,
    limit: int = 3
) -> List[Dict]:
    """Ищет примеры по конкретному подэтапу."""
    global _collection
    
    if _collection is None:
        if not init_vector_store():
            return []
    
    try:
        results = _collection.query(
            query_texts=[f"Этап: {stage}, подэтап: {substage}"],
            n_results=limit,
            where={
                "$and": [
                    {"stage": {"$eq": stage}},
                    {"substage": {"$eq": substage}}
                ]
            },
            include=["metadatas", "documents"]
        )
        
        examples = []
        for i, doc_id in enumerate(results["ids"][0]):
            metadata = results["metadatas"][0][i]
            examples.append({
                "id": doc_id,
                "stage": metadata.get("stage", ""),
                "substage": metadata.get("substage", ""),
                "client": results["documents"][0][i].replace("Клиент: ", ""),
                "manager": metadata.get("manager_response", ""),
                "quality": metadata.get("quality", ""),
                "note": metadata.get("note", ""),
            })
        
        return examples
        
    except Exception as e:
        print(f"❌ Ошибка поиска по substage: {e}")
        return []


def get_golden_moments(stage: Optional[str] = None, limit: int = 5) -> List[Dict]:
    """Возвращает 'золотые моменты' — лучшие примеры."""
    global _collection
    
    if _collection is None:
        if not init_vector_store():
            return []
    
    try:
        # Ищем примеры с "ЗОЛОТОЙ" в note
        where_filter = {"note": {"$contains": "ЗОЛОТОЙ"}}
        if stage:
            where_filter = {
                "$and": [
                    {"stage": {"$eq": stage}},
                    {"note": {"$contains": "ЗОЛОТОЙ"}}
                ]
            }
        
        results = _collection.get(
            where=where_filter,
            limit=limit,
            include=["metadatas", "documents"]
        )
        
        examples = []
        for i, doc_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i]
            examples.append({
                "id": doc_id,
                "stage": metadata.get("stage", ""),
                "substage": metadata.get("substage", ""),
                "client": results["documents"][i].replace("Клиент: ", ""),
                "manager": metadata.get("manager_response", ""),
                "quality": metadata.get("quality", ""),
                "note": metadata.get("note", ""),
            })
        
        return examples
        
    except Exception as e:
        print(f"❌ Ошибка получения golden moments: {e}")
        return []


def format_examples_for_prompt(examples: List[Dict], include_notes: bool = True) -> str:
    """
    Форматирует примеры для добавления в промпт.
    """
    if not examples:
        return ""
    
    lines = ["ПРИМЕРЫ УСПЕШНЫХ ДИАЛОГОВ НА ЭТОМ ЭТАПЕ:", ""]
    
    for i, ex in enumerate(examples, 1):
        similarity = ex.get("similarity", "")
        sim_str = f" (сходство: {similarity})" if similarity else ""
        
        lines.append(f"Пример {i}{sim_str}:")
        lines.append(f"  Клиент: «{ex.get('client', '')}»")
        lines.append(f"  Менеджер: «{ex.get('manager', '')}»")
        
        if include_notes and ex.get("note"):
            lines.append(f"  📌 {ex.get('note')}")
        
        lines.append("")
    
    return "\n".join(lines)


def get_collection_stats() -> Dict:
    """Возвращает статистику коллекции."""
    global _collection
    
    if _collection is None:
        return {"status": "not_initialized", "count": 0}
    
    try:
        count = _collection.count()
        
        # Получаем распределение по этапам
        all_items = _collection.get(include=["metadatas"])
        stages = {}
        for meta in all_items["metadatas"]:
            stage = meta.get("stage", "UNKNOWN")
            stages[stage] = stages.get(stage, 0) + 1
        
        return {
            "status": "ready",
            "count": count,
            "stages": stages
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def rebuild_index():
    """Пересоздаёт индекс (если обновился датасет)."""
    global _collection
    
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        
        # Удаляем старую коллекцию
        try:
            client.delete_collection("sofia_examples")
            print("🗑️ Старый индекс удалён")
        except:
            pass
        
        _collection = None
        
        # Создаём новый
        return init_vector_store()
        
    except Exception as e:
        print(f"❌ Ошибка пересоздания индекса: {e}")
        return False


# Для тестирования
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Инициализация векторного RAG...")
    if init_vector_store():
        print("\n--- Тест поиска ---")
        examples = search_examples("QUALIFICATION", "Хочу квартиру чтобы сдавать в аренду", limit=3)
        print(format_examples_for_prompt(examples))
        
        print("\n--- Статистика ---")
        stats = get_collection_stats()
        print(f"Всего примеров: {stats.get('count', 0)}")
        print(f"По этапам: {stats.get('stages', {})}")
    else:
        print("Не удалось инициализировать RAG")
