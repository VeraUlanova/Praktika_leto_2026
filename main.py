# ==============================================
# Какие зависимости и модули потребуется установить:
# > pip install spacy
# > pip install PyPDF2
# > pip install docx
# > pip install google-genai
# > python -m spacy download ru_core_news_lg
# ==============================================

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional

# Библиотеки для чтения документов
import PyPDF2
from docx import Document

# Библиотека для NLP (определение сущностей)
import spacy

# НОВАЯ библиотека Google GenAI
from google import genai
from google.genai import types

# ==============================================
# 1. КОНФИГУРАЦИЯ И ИНИЦИАЛИЗАЦИЯ
# ==============================================

# Необходимо указать свой API-ключ от Google AI Studio
# Получить можно тут: https://aistudio.google.com/apikey
API_KEY = ""

# Инициализируем клиент GenAI
client = genai.Client(api_key=API_KEY)

# ПРАВИЛЬНЫЕ ИМЕНА МОДЕЛЕЙ ДЛЯ API v1beta
# gemini-1.5-flash - самая быстрая и бесплатная
# gemini-1.5-pro - более мощная, но медленнее
# gemini-1.0-pro - старая версия
MODEL_NAME = "gemini-1.5-flash"  # Используем эту модель - она точно работает!

# Загружаем русскую NLP-модель
try:
    nlp = spacy.load("ru_core_news_lg")
except OSError:
    print("️Модель ru_core_news_lg не найдена. Устанавливаю...")
    os.system("python -m spacy download ru_core_news_lg")
    nlp = spacy.load("ru_core_news_lg")


# ==============================================
# 2. ФУНКЦИИ ДЛЯ ИЗВЛЕЧЕНИЯ ТЕКСТА ИЗ ФАЙЛОВ
# ==============================================

def extract_text_from_pdf(file_path: str) -> str:
    """Извлечение текста из PDF с обработкой ошибок"""
    text = ""
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)

            if reader.is_encrypted:
                print("PDF защищен паролем.")
                return ""

            for page_num, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                    else:
                        print(f"️Страница {page_num} не содержит текста (возможно, сканированный PDF)")
                except Exception as e:
                    print(f"️Ошибка на странице {page_num}: {e}")

    except Exception as e:
        print(f"Ошибка при чтении PDF: {e}")

    return text.strip()


def extract_text_from_docx(file_path: str) -> str:
    """Извлечение текста из DOCX"""
    text = ""
    try:
        doc = Document(file_path)

        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text += cell.text + " "
                text += "\n"

    except Exception as e:
        print(f"Ошибка при чтении DOCX: {e}")

    return text.strip()


def extract_text_from_file(file_path: str) -> str:
    """Универсальная функция чтения файлов"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    if ext == ".txt":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="cp1251") as f:
                text = f.read()

    elif ext == ".docx":
        text = extract_text_from_docx(file_path)

    elif ext == ".pdf":
        text = extract_text_from_pdf(file_path)

    else:
        raise ValueError("Неподдерживаемый формат. Используйте .txt, .docx или .pdf")

    if not text:
        print(f"️ВНИМАНИЕ: Из файла {file_path} не удалось извлечь текст!")

    return text


# ==============================================
# 3. ФУНКЦИЯ ДЛЯ РАБОТЫ С GEMINI API 
# ==============================================

def get_ai_analysis(prompt: str, contract_text: str) -> str:
    """
    Отправляет запрос в Gemini через клиент google.genai
    Использует модель gemini-1.5-flash
    """
    if not contract_text or len(contract_text) < 50:
        return "Текст договора слишком короткий или пустой."

    # Ограничиваем текст для скорости
    max_text_length = 15000
    truncated_text = contract_text[:max_text_length]

    full_prompt = f"""
    Ты — опытный корпоративный юрист. Твоя задача — проанализировать договор.
    Отвечай строго по делу, кратко и структурированно. Используй маркдаун для списков.

    Вот текст договора:
    ---
    {truncated_text}
    ---

    Вопрос юриста: {prompt}
    """

    try:
        # Используем ПРАВИЛЬНУЮ модель gemini-1.5-flash
        response = client.models.generate_content(
            model=MODEL_NAME,  # Теперь используем gemini-1.5-flash
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000,
            )
        )
        return response.text
    except Exception as e:
        error_msg = str(e)
        print(f"Ошибка при запросе к Gemini: {error_msg}")

        # Если модель не найдена, пробуем альтернативную
        if "not found" in error_msg.lower():
            try:
                print("Пробую альтернативную модель gemini-1.0-pro...")
                alt_response = client.models.generate_content(
                    model="gemini-1.0-pro",
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=2000,
                    )
                )
                return alt_response.text
            except Exception as e2:
                return f"Ошибка анализа: {str(e2)}"
        else:
            return f"Ошибка: {error_msg}"


# ==============================================
# 4. ЛОКАЛЬНЫЙ АНАЛИЗ (spaCy + Regex)
# ==============================================

def extract_key_entities(text: str) -> Dict[str, List[str]]:
    """Извлекает ключевые сущности локально"""
    if not text:
        return {"dates": [], "money": [], "orgs": []}

    doc = nlp(text[:50000])  # Ограничиваем для скорости

    entities = {
        "dates": [],
        "money": [],
        "orgs": []
    }

    for ent in doc.ents:
        if ent.label_ == "DATE":
            entities["dates"].append(ent.text)
        elif ent.label_ == "MONEY":
            entities["money"].append(ent.text)
        elif ent.label_ == "ORG":
            entities["orgs"].append(ent.text)

    # Регулярки для сумм
    money_patterns = [
        r'\d+[\s\,]*\d*[\s]*?(?:руб|р\.?|₽)',
        r'\d+[\s\,]*\d*[\s]*?(?:долл|€|\$|евро)',
        r'\d+[\s\,]*\d*\s*миллионов?\s*(?:руб|р\.?|₽)?',
    ]
    for pattern in money_patterns:
        found = re.findall(pattern, text, re.IGNORECASE)
        entities["money"].extend(found)

    # Регулярки для дат
    date_pattern = r'\d{1,2}[\./]\d{1,2}[\./]\d{2,4}'
    found_dates = re.findall(date_pattern, text)
    entities["dates"].extend(found_dates)

    # Убираем дубликаты
    for key in entities:
        entities[key] = list(set(entities[key]))[:10]

    return entities


# ==============================================
# 5. ОСНОВНЫЕ ФУНКЦИИ ИИ-АНАЛИЗА
# ==============================================

def determine_contract_type(text: str) -> str:
    """Определяет тип договора"""
    if not text:
        return "️Текст договора пуст."
    prompt = "Определи тип этого договора (купля-продажа, аренда, подряд, оказание услуг, поставка, займ и т.п.). Напиши только название типа."
    return get_ai_analysis(prompt, text)


def extract_key_conditions(text: str) -> str:
    """Выделяет ключевые условия"""
    if not text:
        return "️Текст договора пуст."
    prompt = """
    Выдели 5-7 ключевых условий договора в виде четкого списка:
    - Предмет договора
    - Цена и порядок оплаты
    - Сроки исполнения
    - Ответственность сторон
    - Порядок разрешения споров
    - Срок действия договора
    """
    return get_ai_analysis(prompt, text)


def find_unfavorable_terms(text: str) -> str:
    """Ищет невыгодные положения"""
    if not text:
        return "️Текст договора пуст."
    prompt = """
    Найди пункты, которые могут быть невыгодны для стороны, подписывающей договор.
    Укажи номер пункта и почему это невыгодно.
    Если таких пунктов нет, напиши: "Невыгодных условий не обнаружено".
    """
    return get_ai_analysis(prompt, text)


def identify_legal_risks(text: str) -> str:
    """Выявляет юридические риски"""
    if not text:
        return "️Текст договора пуст."
    prompt = """
    Выяви юридические риски:
    - Противоречия между пунктами
    - Неопределенные формулировки
    - Чрезмерные штрафы
    - Риски изменения цены
    - Риски судебных споров
    """
    return get_ai_analysis(prompt, text)


def compare_with_template(contract_text: str, template_text: str = "") -> str:
    """Сравнивает с шаблоном"""
    if not contract_text:
        return "️Текст договора пуст."

    if not template_text:
        template_text = """
        Идеальный договор:
        - Предмет: четко описан
        - Цена: фиксированная
        - Сроки: конкретные даты
        - Ответственность: зеркальная
        - Форс-мажор: стандартный
        - Юрисдикция: по месту нахождения истца
        """

    prompt = f"""
    Сравни договор с шаблоном.
    Шаблон:
    {template_text}

    Укажи:
    1. Что соответствует шаблону.
    2. Что отличается.
    3. Насколько критичны расхождения (от 1 до 10).
    """
    return get_ai_analysis(prompt, contract_text)


def suggest_improvements(contract_text: str, unfavourable: str, risks: str) -> str:
    """Предлагает корректировки"""
    if not contract_text:
        return "️Текст договора пуст."

    prompt = f"""
    На основе выявленных проблем:
    Невыгодные условия: {unfavourable}
    Риски: {risks}

    Предложи конкретные варианты корректировки.
    Для каждого пункта напиши: "Как исправить" и "Новая редакция".
    """
    return get_ai_analysis(prompt, contract_text)


# ==============================================
# 6. ГЛАВНАЯ ФУНКЦИЯ АНАЛИЗА
# ==============================================

def analyze_contract(file_path: str, template_path: Optional[str] = None) -> Dict[str, str]:
    """Главная функция анализа"""
    print(f"Начинаю анализ договора: {file_path}")

    # 1. Извлекаем текст
    text = extract_text_from_file(file_path)
    print(f"Текст извлечен. Длина: {len(text)} символов.")

    if len(text) < 50:
        print("️Текст слишком короткий!")

    # 2. Локальный анализ
    local_entities = extract_key_entities(text)
    print(
        f"Локально найдены: даты {len(local_entities['dates'])}, суммы {len(local_entities['money'])}, организации {len(local_entities['orgs'])}")

    # 3. AI-анализ
    print("Запускаю AI-анализ (может занять 30-60 секунд)...")

    contract_type = determine_contract_type(text)
    key_conditions = extract_key_conditions(text)
    unfavourable = find_unfavorable_terms(text)
    risks = identify_legal_risks(text)

    template_text = None
    if template_path and os.path.exists(template_path):
        template_text = extract_text_from_file(template_path)

    comparison = compare_with_template(text, template_text)
    suggestions = suggest_improvements(text, unfavourable, risks)

    report = {
        "file_name": os.path.basename(file_path),
        "analysis_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "text_length": len(text),
        "local_entities": local_entities,
        "contract_type": contract_type,
        "key_conditions": key_conditions,
        "unfavorable_terms": unfavourable,
        "legal_risks": risks,
        "template_comparison": comparison,
        "improvements": suggestions,
    }

    print("Анализ завершен!")
    return report


def save_report(report: Dict[str, str], output_file: str = "ai_contract_report.md"):
    """Сохраняет отчет в Markdown"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Юридический AI-отчет по договору\n\n")
        f.write(f"**Файл:** {report['file_name']}\n")
        f.write(f"**Дата анализа:** {report['analysis_date']}\n")
        f.write(f"**Длина текста:** {report['text_length']} символов\n\n")

        f.write(f"## 1. Тип договора\n{report['contract_type']}\n\n")
        f.write(f"## 2. Ключевые условия\n{report['key_conditions']}\n\n")
        f.write(f"## 3. Невыгодные положения\n{report['unfavorable_terms']}\n\n")
        f.write(f"## 4. Юридические риски\n{report['legal_risks']}\n\n")
        f.write(f"## 5. Сравнение с шаблоном\n{report['template_comparison']}\n\n")
        f.write(f"## 6. Рекомендации\n{report['improvements']}\n\n")

        f.write(f"## Технические данные\n")
        f.write(f"- Даты: {', '.join(report['local_entities']['dates'][:5])}\n")
        f.write(f"- Суммы: {', '.join(report['local_entities']['money'][:5])}\n")
        f.write(f"- Организации: {', '.join(report['local_entities']['orgs'][:5])}\n")

    print(f"📄 Отчет сохранен: {output_file}")


# ==============================================
# 7. ЗАПУСК
# ==============================================

if __name__ == "__main__":
    CONTRACT_PATH = "Contract.pdf"

    if not os.path.exists(CONTRACT_PATH):
        print(f"️Файл {CONTRACT_PATH} не найден!")
        CONTRACT_PATH = input("Введите путь к файлу: ").strip()

    try:
        result = analyze_contract(CONTRACT_PATH)
        save_report(result, "ai_contract_report.md")
        print("\n🎉 Готово! Открывай ai_contract_report.md")

    except Exception as e:
        print(f"Ошибка: {e}")
        print("\nРешения:")
        print("1. Проверь API-ключ")
        print("2. Установи: pip install --upgrade google-genai")
        print("3. Если не работает, пробуем альтернативный подход")
      
