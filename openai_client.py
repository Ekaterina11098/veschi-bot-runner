import os
import re
from difflib import SequenceMatcher

from dotenv import load_dotenv
from openai import OpenAI

from validator import validate_answer
from review_benchmarks import example_context, recent_benchmarks
from review_purchase_context import purchase_instructions

load_dotenv()
_SOURCE_DIR = os.path.join(os.path.dirname(__file__), "private-source")
_PROMPT_DIR = _SOURCE_DIR if os.path.isfile(os.path.join(_SOURCE_DIR, "system_prompt.md")) else os.path.dirname(__file__)
PROMPT_PATH = os.path.join(_PROMPT_DIR, "system_prompt.md")
QUESTIONS_PROMPT_PATH = os.path.join(_PROMPT_DIR, "questions_prompt.md")


MATERIAL_COMPLAINT_INSTRUCTIONS = "\n\n# УТОЧНЕНИЕ ВЛАДЕЛЬЦА: СОМНЕНИЯ В НАТУРАЛЬНОСТИ КОЖИ\nЭто уточнение имеет приоритет над общими примерами и формулировками о натуральной коже выше.\nЕсли покупатель пишет «не кожа», «кожзам», «сомневаюсь в натуральности» или аналогичное:\n- спокойно признай его сомнение; не спорь и не обесценивай впечатления;\n- используй известные сведения о материале именно этой модели/артикула и именно обсуждаемой детали (корпус, ручки, ремешок); не переноси материал корпуса на ремешок и наоборот;\n- утверждай, что модель/деталь выполнена из натуральной кожи, только если это подтверждено доступными данными о ней. Если данных не хватает или они противоречат друг другу, не давай категоричного заверения;\n- не придумывай выделку, финишную обработку, гладкое/матовое защитное покрытие, пропитку, вид/слой кожи, износостойкость или причины сходства с искусственным материалом. Объясняй конкретные свойства только при наличии подтверждения для этой модели/детали;\n- лабораторную сертификацию упоминай только при подтверждении её применимости к конкретной модели. Общая база и пример не заменяют такого подтверждения;\n- не используй общебрендовые абсолютные заверения «мы всегда честно указываем материалы», «не используем искусственные аналоги» как доказательство состава конкретного изделия;\n- отзыв с таким сомнением, жалобой или неоднозначностью при любой оценке, включая 5★, остаётся на согласовании человека. Это правило подготовки черновика НЕ разрешает автоматическую публикацию нареканий.\n\nПример тона и структуры, ТОЛЬКО если натуральная кожа для обсуждаемой модели подтверждена:\n«Светлана, добрый день. Спасибо, что поделились своими сомнениями. По данным производителя, эта модель выполнена из натуральной кожи. Понимаем, что материал мог не совпасть с вашими ожиданиями.\nС уважением, команда VESCHI 👜✨»\n\nИмя, материал и формулировку адаптируй к фактам. Не копируй «по данным производителя», если источник этих данных иной или отсутствует. Пояснение об обработке добавляй только по подтверждённым сведениям о конкретной модели; при их отсутствии заканчивай без выдуманного объяснения.\n"

def load_system_prompt():
    with open(PROMPT_PATH, encoding="utf-8") as prompt_file:
        return prompt_file.read() + MATERIAL_COMPLAINT_INSTRUCTIONS


def _main_text(answer):
    body=answer.split("С уважением")[0].strip().casefold()
    # Mandatory identical greeting is not evidence that two answer bodies repeat.
    return re.sub(r'^(?:[^.!?\n]{1,80},\s*)?добрый день[.!]\s*','',body).strip()


def _sufficiently_different(first, second):
    a, b = _main_text(first), _main_text(second)
    return bool(a and b) and SequenceMatcher(None, a, b).ratio() < 0.75


def generate_draft(feedback):
    """Create two independent, validated answers with different wording."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Не настроен OPENAI_API_KEY в Secrets")
    purchase_context = purchase_instructions(feedback)
    system_prompt = load_system_prompt() + '\n\nОбязательная проверка статуса именно этого отзыва:\n' + purchase_context
    details = feedback.get("productDetails") or {}
    user_content = (
        f"Покупатель: {feedback.get('userName') or 'имя не указано'}\n"
        f"Оценка: {feedback.get('productValuation')}\n"
        f"{purchase_context}\n"
        f"Товар: {details.get('productName') or feedback.get('productName') or 'не указан'}\n"
        f"Отзыв: {feedback.get('text') or 'нет текста'}\n"
        f"Достоинства: {feedback.get('pros') or 'нет'}\n"
        f"Недостатки: {feedback.get('cons') or 'нет'}"
    )
    benchmark_warning = ""
    try:
        examples = example_context(feedback, recent_benchmarks())
        user_content += examples
    except RuntimeError:
        examples = ""
        benchmark_warning = "Эталоны временно недоступны: черновики подготовлены по правилам промпта без примеров ваших правок."
    client = OpenAI(api_key=api_key)
    customer_name = str(feedback.get("userName") or "").strip()
    if customer_name and customer_name.casefold() not in ("покупатель", "гость", "аноним"):
        opening = f"{customer_name}, добрый день."
    else:
        opening = "Добрый день!"

    validation_errors = []

    def create(style):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content + "\n\nНачни ответ СТРОГО с «" + opening + "». "
                 "Это обязательное приветствие, даже если имя уже есть в отзыве. " + style +
                 ("\nИсправь замечания предыдущей проверки: " + "; ".join(validation_errors) if validation_errors else "")},
            ],
            temperature=0.9,
        )
        answer = (response.choices[0].message.content or "").strip()
        # Restore only display whitespace in the mandatory greeting. Keep the
        # original customer name and body; all safety validation still runs.
        pattern = r"^" + r"\s+".join(re.escape(x) for x in opening.split()) + r"\s*"
        match = re.match(pattern, answer, re.IGNORECASE)
        if match:
            answer = opening + " " + answer[match.end():].lstrip()
        return answer

    try:
        first = ""
        for _ in range(3):
            first = create("Вариант 1: короткий, сдержанный ответ. Сразу отреагируй на главную мысль отзыва. Выдай только готовый ответ.")
            validation = validate_answer(first, feedback)
            validation_errors = validation["errors"]
            if validation["approved"]:
                break
        else:
            raise RuntimeError("ИИ не смог подготовить допустимый первый ответ. Попробуйте ещё раз")

        validation_errors = []
        for _ in range(3):
            second = create(
                "Вариант 2: более тёплый ответ, иной порядок мыслей и заметно другие формулировки. "
                "Не копируй текст варианта 1, который приведён ниже; сохрани те же факты и правила бренда. "
                "Выдай только готовый ответ.\nВариант 1:\n" + first
            )
            validation = validate_answer(second, feedback)
            validation_errors = validation["errors"]
            if validation["approved"] and _sufficiently_different(first, second):
                return {"variant1": first, "variant2": second,
                        "benchmarks_used": examples.count("Одобренная редакция"),
                        "benchmark_warning": benchmark_warning}
        raise RuntimeError("ИИ не смог создать достаточно отличающийся второй ответ. Нажмите генерацию ещё раз")
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("Не удалось создать черновики. Проверьте настройки OpenAI и попробуйте ещё раз") from error


def generate_question_drafts(question):
    """Generate two distinct answers to a product question for manual review."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Не настроен OPENAI_API_KEY в Secrets")
    with open(QUESTIONS_PROMPT_PATH, encoding="utf-8") as prompt_file:
        prompt = prompt_file.read()
    details = question.get("productDetails") or {}
    name = str(question.get("userName") or "").strip()
    if name.casefold() in ("покупатель", "гость", "аноним"):
        name = ""
    opening = f"{name}, добрый день." if name else "Добрый день!"
    context = (f"Имя покупателя: {name or 'не указано'}\n"
               f"Модель: {details.get('productName') or 'не указана'}\n"
               f"Артикул продавца: {details.get('supplierArticle') or 'не указан'}\n"
               f"Вопрос: {question.get('text') or ''}\n"
               f"Начни строго с «{opening}».")
    try:
        # The same manager-approved examples are shared across all cabinets.
        context += example_context(question,recent_benchmarks())
    except RuntimeError:
        pass
    check_data = {"userName": name, "text": question.get("text") or "", "productValuation": 0}
    client = OpenAI(api_key=api_key)

    def create(direction):
        response = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.9,
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": context + "\n" + direction}],
        )
        return (response.choices[0].message.content or "").strip()

    try:
        for _ in range(3):
            first = create("Вариант 1: конкретный, краткий и деловой. Только текст ответа.")
            if validate_answer(first, check_data)["approved"]:
                break
        else:
            raise RuntimeError("Не удалось подготовить корректный ответ на вопрос")
        for _ in range(3):
            second = create("Вариант 2: более тёплый, другие формулировки и порядок мыслей. "
                            "Не копируй вариант 1. Только текст ответа.\nВариант 1:\n" + first)
            if validate_answer(second, check_data)["approved"] and _sufficiently_different(first, second):
                return {"variant1": first, "variant2": second}
        raise RuntimeError("Не удалось получить достаточно отличающийся второй ответ на вопрос")
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("Не удалось подготовить ответы на вопрос. Повторите позже") from error
