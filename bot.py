import os
import json
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
STORAGE_FILE = "storage.json"

PROJECTS = [
    "Вилла Нетания",
    "Лия Рамат-Авив",
    "Нетания Ксения и Пётр",
    "Марат",
    "Ирина Кейсария",
    "Ирис Ришон-леЦион",
    "Марат Тбилиси",
]

SYSTEM_PROMPT = """Ты ассистент-менеджер дизайн-студии Леты.

Проекты студии:
1. Вилла Нетания
2. Лия Рамат-Авив
3. Нетания Ксения и Пётр
4. Марат
5. Ирина Кейсария
6. Ирис Ришон-леЦион
7. Марат Тбилиси

Правила:
- Короткие ответы, никаких длинных текстов
- Всегда заканчивай конкретным action step
- Пушь на действие
- Отвечай на русском

Формат лога:
🔴 Горит сегодня
🟡 В процессе
✅ Сделано
📌 Не забыть"""


def load_storage():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}, "history": {}}


def save_storage(data):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_history(chat_id):
    return load_storage().get("history", {}).get(str(chat_id), [])


def save_history(chat_id, history):
    storage = load_storage()
    storage.setdefault("history", {})[str(chat_id)] = history[-20:]
    save_storage(storage)


def save_file_meta(project, file_name, file_id, file_type):
    storage = load_storage()
    storage.setdefault("files", {}).setdefault(project, []).append(
        {"name": file_name, "file_id": file_id, "type": file_type}
    )
    save_storage(storage)


async def ask_claude(user_message, chat_id):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    history = get_history(chat_id)
    history.append({"role": "user", "content": user_message})
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)
    return reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я менеджер студии Леты 👋\n\n"
        "/log — план дня\n"
        "/projects — список проектов\n"
        "/files — файлы по проекту\n\n"
        "Просто пиши — отвечу как менеджер 🎙"
    )


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Формирую лог...")
    reply = await ask_claude("Составь лог дня в формате 🔴🟡✅📌. Если задач нет — попроси рассказать что в работе.", update.effective_chat.id)
    await update.message.reply_text(reply)


async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📁 Активные проекты:\n\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(PROJECTS, 1))
    await update.message.reply_text(text)


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(p, callback_data=f"files:{p}")] for p in PROJECTS]
    await update.message.reply_text("По какому проекту?", reply_markup=InlineKeyboardMarkup(keyboard))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("files:"):
        project = query.data[6:]
        files = load_storage().get("files", {}).get(project, [])
        if not files:
            await query.edit_message_text(f"По «{project}» файлов нет. Скинь — привяжу.")
            return
        text = f"📁 {project}\n\n" + "\n".join(
            ("📄" if f["type"] == "document" else "🖼") + " " + f["name"] for f in files[-10:]
        )
        await query.edit_message_text(text)
    elif query.data.startswith("attach:"):
        _, project, file_key = query.data.split(":", 2)
        pending = context.user_data.get("pending_files", {})
        if file_key in pending:
            fi = pending.pop(file_key)
            context.user_data["pending_files"] = pending
            save_file_meta(project, fi["name"], fi["file_id"], fi["type"])
            await query.edit_message_text(f"✅ «{fi['name']}» → «{project}»")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")
    reply = await ask_claude(update.message.text, update.effective_chat.id)
    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙 Включи транскрипцию в Telegram: Настройки → Чаты → Транскрибировать голосовые.\nПотом пришли текст — разберём по проектам."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    fk = doc.file_id[:20]
    context.user_data.setdefault("pending_files", {})[fk] = {"name": doc.file_name or "документ", "file_id": doc.file_id, "type": "document"}
    keyboard = [[InlineKeyboardButton(p, callback_data=f"attach:{p}:{fk}")] for p in PROJECTS]
    await update.message.reply_text(f"📄 {doc.file_name}\n\nК какому проекту?", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    fk = photo.file_id[:20]
    context.user_data.setdefault("pending_files", {})[fk] = {"name": update.message.caption or "фото", "file_id": photo.file_id, "type": "photo"}
    keyboard = [[InlineKeyboardButton(p, callback_data=f"attach:{p}:{fk}")] for p in PROJECTS]
    await update.message.reply_text("🖼 К какому проекту?", reply_markup=InlineKeyboardMarkup(keyboard))


if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("projects", projects_command))
    app.add_handler(CommandHandler("files", files_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен ✅")
    app.run_polling()
