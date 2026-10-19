"""Запуск: python bot.py. Секреты читаются только из локального .env."""
import asyncio
import logging
import os

from dotenv import load_dotenv
from pydantic import ValidationError
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from fitness.llm import LLMError
from fitness.models import Profile
from fitness.service import Service
from fitness.store import Store

load_dotenv()
# HTTP-client logs may contain Telegram token in URL. Do not enable request logging.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

FIELDS = [
    ("age", "Сколько вам лет? Сервис предназначен для взрослых от 18 лет.", None),
    ("goal", "Какая у вас основная цель тренировок?", ["Общая физическая форма", "Сила", "Выносливость"]),
    ("fitness_level", "Какой у вас опыт?", ["Начинающий", "Есть опыт", "Продвинутый"]),
    ("current_activity", "Опишите обычную физическую активность: работа, прогулки, занятия.", None),
    ("sessions_per_week", "Сколько занятий в неделю: от 1 до 7?", ["2", "3", "4"]),
    ("session_duration_minutes", "Сколько минут на занятие: от 10 до 180?", ["20", "30", "45", "60"]),
    ("training_location", "Где планируете заниматься?", ["Дома", "В зале", "На улице"]),
    ("equipment", "Перечислите оборудование через запятую или выберите «Без оборудования».", ["Без оборудования", "Коврик", "Гантели, коврик"]),
    ("health_info_status", "Хотите сообщить ограничения, травмы, боль или запреты врача? Можно отказаться; это ограничит персонализацию.", ["Сообщить", "Предпочитаю не отвечать"]),
    ("limitations", "Опишите ограничения либо явно напишите «Ограничений нет».", None),
    ("preferences", "Есть пожелания, например без прыжков? Или напишите «Нет».", None),
    ("data_consent", "Для подбора программы анкета будет сохранена и передана GigaChat без имени и Telegram ID. Вы согласны?", ["Согласен", "Не согласен"]),
]
MAPS = {
    "fitness_level": {"Начинающий": "beginner", "Есть опыт": "intermediate", "Продвинутый": "advanced"},
    "training_location": {"Дома": "home", "В зале": "gym", "На улице": "outdoor"},
    "health_info_status": {"Сообщить": "provided", "Предпочитаю не отвечать": "declined"},
}


class FitnessBot:
    def __init__(self, service):
        self.service, self.store = service, service.store

    @staticmethod
    def owner(update):
        return "telegram:"+str(update.effective_user.id)

    async def send(self, update, text, choices=None):
        keyboard = ReplyKeyboardMarkup([[c] for c in choices], resize_keyboard=True, one_time_keyboard=True) if choices else ReplyKeyboardRemove()
        # Plain text avoids HTML/Markdown injection from generated content.
        for start in range(0, len(text) or 1, 3800):
            await update.effective_message.reply_text(text[start:start+3800], reply_markup=keyboard)

    async def ask(self, update, state):
        i = state["index"]
        if i == 9 and state["data"].get("health_info_status") == "declined":
            state["data"]["limitations"] = None
            state["index"] += 1
            i += 1
        self.store.put_json("states", self.owner(update), state)
        if i >= len(FIELDS):
            text = "Проверьте анкету:\n" + profile_text(state["data"]) + "\n\nПодтвердите сохранение или начните заново через /profile."
            state["kind"] = "confirm_profile"
            self.store.put_json("states", self.owner(update), state)
            return await self.send(update, text, ["Подтвердить анкету"])
        _, question, choices = FIELDS[i]
        await self.send(update, question+"\n/cancel — отменить", choices)

    async def command(self, update, context):
        if update.effective_chat.type != "private":
            return await self.send(update, "Анкета доступна только в личном чате с ботом.")
        owner = self.owner(update)
        cmd = update.effective_message.text.split()[0].split("@")[0]
        try:
            if cmd in ("/start", "/help"):
                return await self.send(update, "ИИ-гид по фитнес-программам · 18+\nИнформационные рекомендации не заменяют тренера или врача.\n\n/profile — заполнить или изменить анкету\n/resume — продолжить анкету\n/program — текущая программа\n/generate — создать программу\n/feedback — отзыв\n/adapt — предложить изменения\n/history — история версий\n/explain НОМЕР_ПРОГРАММЫ НОМЕР_ЗАНЯТИЯ НОМЕР_УПРАЖНЕНИЯ\n/confirm НОМЕР_ПРОГРАММЫ — принять новую версию\n/cancel — отменить ввод")
            if cmd == "/cancel":
                self.store.put_json("states", owner, {})
                return await self.send(update, "Ввод отменён. Сохранённый профиль остался доступен.")
            if cmd == "/resume":
                state = self.store.get_json("states", owner) or {}
                if state.get("kind") == "profile":
                    return await self.ask(update, state)
                return await self.send(update, "Продолжите текущий ввод ответом или начните /profile заново.")
            if cmd == "/profile":
                state = {"kind": "profile", "index": 0, "data": {}}
                return await self.ask(update, state)
            if cmd == "/history":
                records = self.store.programs(owner)
                return await self.send(update, "\n".join(f"№{p['id']} · версия {p['version']} · {p['status']}" for p in records) or "Программ пока нет.")
            if cmd == "/program":
                record = next((r for r in self.store.programs(owner) if r["status"] == "current"), None)
                return await self.send(update, format_program(record) if record else "Программы пока нет. Заполните /profile, затем /generate.")
            if cmd == "/generate":
                await self.send(update, "Создаю программу. Это может занять около минуты…")
                response = await asyncio.to_thread(self.service.generate, owner)
                return await self.send(update, format_response(response))
            if cmd == "/confirm":
                if len(context.args) != 1:
                    return await self.send(update, "Пример: /confirm 2")
                self.store.confirm(owner, int(context.args[0]))
                return await self.send(update, "Новая версия принята. Предыдущая сохранена в /history.")
            if cmd == "/explain":
                if len(context.args) != 3:
                    return await self.send(update, "Пример: /explain 1 1 1. Номера занятий и упражнений указаны в /program.")
                pid, wi, ei = map(int, context.args)
                await self.send(update, "Подготавливаю объяснение…")
                result = await asyncio.to_thread(self.service.explain, owner, pid, wi-1, ei-1)
                text = result["message"] + "\n" + "\n".join(result["questions"])
                if result["explanation"]:
                    text += "\n" + explanation_text(result["explanation"])
                return await self.send(update, text)
            if cmd == "/adapt":
                self.store.put_json("states", owner, {"kind": "adapt"})
                return await self.send(update, "Что нужно изменить и почему? Если меняются время или оборудование, сначала обновите /profile. /cancel — отменить.")
            if cmd == "/feedback":
                record = next((r for r in self.store.programs(owner) if r["status"] == "current"), None)
                if not record:
                    return await self.send(update, "Сначала создайте программу.")
                self.store.put_json("states", owner, {"kind": "feedback", "index": 0, "data": {"program_id": record["id"]}})
                return await self.send(update, "Номер занятия из /program?")
        except (ValueError, LLMError, ValidationError):
            await self.send(update, "Не удалось выполнить действие. Проверьте анкету, номера и настройку GigaChat. Данные сохранены; повторите запрос.")

    async def message(self, update, context):
        if update.effective_chat.type != "private":
            return
        owner = self.owner(update)
        state = self.store.get_json("states", owner) or {}
        value = (update.effective_message.text or "").strip()
        if len(value) > 1500:
            return await self.send(update, "Сократите ответ до 1500 символов.")
        try:
            if state.get("kind") == "profile":
                field = FIELDS[state["index"]][0]
                if field in MAPS:
                    if value not in MAPS[field]:
                        return await self.ask(update, state)
                    value = MAPS[field][value]
                if field in {"age", "sessions_per_week", "session_duration_minutes"}:
                    value = int(value)
                    low, high = {"age": (18,120), "sessions_per_week": (1,7), "session_duration_minutes": (10,180)}[field]
                    if not low <= value <= high:
                        raise ValueError()
                if field == "equipment":
                    value = [] if value.casefold() == "без оборудования" else [v.strip() for v in value.split(",") if v.strip()]
                if field == "data_consent":
                    if value != "Согласен":
                        self.store.put_json("states", owner, {})
                        return await self.send(update, "Без согласия анкета не будет передана модели. /profile — начать заново.")
                    value = True
                state["data"][field] = value
                state["index"] += 1
                return await self.ask(update, state)
            if state.get("kind") == "confirm_profile":
                if value != "Подтвердить анкету":
                    return await self.send(update, "Нажмите «Подтвердить анкету» или /profile для исправления.", ["Подтвердить анкету"])
                self.service.save_profile(owner, state["data"])
                self.store.put_json("states", owner, {})
                return await self.send(update, "Анкета сохранена. /generate — создать программу.")
            if state.get("kind") == "adapt":
                await self.send(update, "Подготавливаю предложение изменений…")
                response = await asyncio.to_thread(self.service.generate, owner, value)
                self.store.put_json("states", owner, {})
                return await self.send(update, format_response(response))
            if state.get("kind") == "feedback":
                data, i = state["data"], state["index"]
                keys = ["workout_index", "completion_status", "actual_duration_minutes", "perceived_difficulty", "pain_reported", "comment"]
                questions = ["Номер занятия?", "Занятие выполнено?", "Сколько минут заняло?", "Сложность от 1 до 10?", "Была ли боль?", "Комментарий или «Нет»?"]
                options = {1: ["Полностью", "Частично", "Пропущено"], 4: ["Да", "Нет", "Не отвечать"]}
                if i == 0:
                    value = int(value)-1
                    record = self.store.program(owner, data["program_id"])
                    if not 0 <= value < len(record["body"]["program"]["workouts"]):
                        raise ValueError()
                elif i == 1:
                    value = {"Полностью":"completed", "Частично":"partial", "Пропущено":"skipped"}[value]
                elif i in (2,3):
                    value = int(value)
                    if not 1 <= value <= (360 if i==2 else 10):
                        raise ValueError()
                elif i == 4:
                    value = {"Да": True, "Нет": False, "Не отвечать": None}[value]
                data[keys[i]] = value
                i += 1
                if i == 2 and data["completion_status"] == "skipped":
                    i = 4
                state["index"] = i
                self.store.put_json("states", owner, state)
                if i == 6:
                    self.service.feedback(owner, data)
                    self.store.put_json("states", owner, {})
                    text = "Обратная связь сохранена. /adapt — предложить изменения."
                    if data.get("pain_reported"):
                        text += "\nНе продолжайте упражнение, вызывающее боль. Для оценки причины и допустимой нагрузки обратитесь к специалисту."
                    return await self.send(update, text)
                return await self.send(update, questions[i], options.get(i))
            await self.send(update, "Выберите действие: /profile, /program, /feedback или /help.")
        except LLMError as error:
            await self.send(update, str(error))
        except (ValueError, KeyError, ValidationError):
            await self.send(update, "Ответ не подходит. Проверьте значение и ответьте ещё раз. /cancel — отменить; /profile — исправить анкету.")


def profile_text(p):
    labels = {"age":"Возраст", "goal":"Цель", "fitness_level":"Уровень", "current_activity":"Активность", "sessions_per_week":"Занятий в неделю", "session_duration_minutes":"Минут на занятие", "training_location":"Место", "equipment":"Оборудование", "health_info_status":"Ответ об ограничениях", "limitations":"Ограничения", "preferences":"Пожелания"}
    values = {"beginner":"Начинающий", "intermediate":"Есть опыт", "advanced":"Продвинутый", "home":"Дома", "gym":"В зале", "outdoor":"На улице", "provided":"Сообщены", "declined":"Отказ от ответа"}
    return "\n".join(f"{label}: {', '.join(p[key]) or 'Без оборудования' if isinstance(p.get(key), list) else values.get(str(p.get(key)), str(p.get(key) or 'Не указано'))}" for key,label in labels.items())


def format_program(record):
    p = record["body"]["program"]
    lines = [f"{p['title']} · версия {record['version']} · №{record['id']}", p["rationale"]]
    for wi,w in enumerate(p["workouts"]):
        lines += [f"\nЗанятие {wi+1} · день {w['day']} · {w['name']} · ≈{w['duration_minutes']} мин", "Разминка: "+w["warmup"]]
        for ei,e in enumerate(w["exercises"]):
            dose = e["repetitions"] or str(e["seconds"])+" сек"
            lines += [f"{ei+1}. {e['name']} — {e['sets']} × {dose}, отдых {e['rest_seconds']} сек.", e["technique"], f"Техника: /explain {record['id']} {wi+1} {ei+1}"]
        lines += ["Завершение: "+w["cooldown"]]
    lines += ["\nВосстановление: "+p["recovery"], "Нагрузка: "+p["load_guidance"], "Дальше: "+p["progression"]]
    if record["status"] == "draft":
        lines += [f"Это предложение. Принять: /confirm {record['id']}"]
    return "\n".join(lines)


def format_response(response):
    result = response["result"]
    return "\n".join([result["message"], *result["questions"], *result.get("changes", [])]) + ("\n"+format_program(response["record"]) if response["record"] else "")


def explanation_text(explanation):
    labels = {"purpose":"Назначение", "equipment":"Оборудование", "starting_position":"Исходное положение", "steps":"Выполнение", "breathing":"Дыхание", "mistakes":"Частые ошибки", "easier_option":"Упрощение", "stop_when":"Когда прекратить"}
    return "\n\n".join(label+":\n"+("\n".join(value) if isinstance(value,list) else value) for key,label in labels.items() if (value:=explanation.get(key)))


async def on_error(update, context):
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Временная ошибка. Данные анкеты сохранены. Попробуйте ещё раз через /help.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Добавьте TELEGRAM_BOT_TOKEN в локальный .env. Создайте бота через @BotFather в Telegram.")
    bot = FitnessBot(Service(Store()))
    proxy = os.getenv("TELEGRAM_PROXY_URL") or None
    builder = Application.builder().token(token)
    if proxy:
        builder = builder.request(HTTPXRequest(proxy_url=proxy)).get_updates_request(HTTPXRequest(proxy_url=proxy))
    async def ready(application):
        print("Telegram подключён. Бот готов принимать /start.", flush=True)
    app = builder.post_init(ready).build()
    for command in ["start","help","cancel","resume","profile","history","program","generate","confirm","explain","adapt","feedback"]:
        app.add_handler(CommandHandler(command, bot.command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.message))
    app.add_error_handler(on_error)
    print("Запускается Telegram-бот. Для остановки: Ctrl+C.")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
