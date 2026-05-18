import os
import json
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8629705630:AAFIC4QVLD3B5XV8BOZV45Edng5H0ePcls4")
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
- Если тебе описывают задачи голосом — вычленяй главное и фиксируй по проектам
- Отвечай на русском

Формат ежедневного лога:
🔴 Горит сегодня
🟡 В процессе
✅ Сделано
📌 Не забыть

Если пользователь спрашивает про файлы — они хранятся в системе, скажи что для поиска файла нужно написать: /файлы [название проекта]"""

# ─── STORAGE ──────────────────────────────────────────────────────────────────
def load_storage():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}, "tasks": {}, "history": {}}

def save_storage(data):
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_history(chat_id: str):
    storage = load_storage()
    return storage.get("history", {}).get(chat_id, [])

def save_history(chat_id: str, history: list):
    storage = load_storage()
    if "history" not in storage:
        storage["history"] = {}
    # Храним последние 20 сообщений
    storage["history"][chat_id] = history[-20:]
    save_storage(storage)

def save_file_meta(project: str, file_name: str, file_id: str, file_type: str, chat_id: str):
    storage = load_storage()
    if "files" not in storage:
        storage["files"] = {}
    if project not in storage["files"]:
        storage["files"][project] = []
    storage["files"][project].append({
        "name": file_name,
        "file_id": file_id,
        "type": file_type,
        "chat_id": chat_id,
    })
    save_storage(storage)

def get_files_for_project(project: str):
    storage = load_storage()
    return storage.get("files", {}).get(project, [])

# ─── AI ───────────────────────────────────────────────────────────────────────
async def ask_claude(user_message: str, chat_id: str) -> str:
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

def detect_project(text: str) -> str | None:
    text_lower = text.lower()
    for project in PROJECTS:
        words = project.lower().split()
        if any(w in text_lower for w in words if len(w) > 3):
            return project
    return None

# ─── HANDLERS ─────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я менеджер студии Леты 👋\n\n"
        "Что умею:\n"
        "• Принимать задачи голосом или текстом\n"
        "• Хранить файлы по проектам\n"
        "• Структурировать день\n\n"
        "Команды:\n"
        "/лог — план дня\n"
        "/проекты — список проектов\n"
        "/файлы — файлы по проекту\n\n"
        "Просто пиши или отправляй голосовое 🎙"
    )
    await update.message.reply_text(text)

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("Формирую лог дня...")
    reply = await ask_claude("Составь мой лог дня в формате 🔴🟡✅📌. Если задач нет — попроси меня рассказать что сейчас в работе.", chat_id)
    await update.message.reply_text(reply)

async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📁 Активные проекты:\n\n"
    for i, p in enumerate(PROJECTS, 1):
        text += f"{i}. {p}\n"
    text += "\nДля файлов: /файлы [название]"
    await update.message.reply_text(text)

async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args) if context.args else ""
    
    if not args:
        # Показываем кнопки выбора проекта
        keyboard = []
        for p in PROJECTS:
            keyboard.append([InlineKeyboardButton(p, callback_data=f"files:{p}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("По какому проекту показать файлы?", reply_markup=reply_markup)
        return
    
    project = detect_project(args) or args
    files = get_files_for_project(project)
    
    if not files:
        await update.message.reply_text(f"По проекту «{project}» файлов пока нет.\n\nПросто скинь файл в чат — я спрошу к какому проекту его прикрепить.")
        return
    
    text = f"📁 {project}\n\n"
    for f in files[-10:]:  # последние 10
        icon = "📄" if f["type"] == "document" else "🖼"
        text += f"{icon} {f['name']}\n"
    
    await update.message.reply_text(text)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("files:"):
        project = query.data[6:]
        files = get_files_for_project(project)
        
        if not files:
            await query.edit_message_text(f"По проекту «{project}» файлов пока нет.\n\nПросто скинь файл — я привяжу к проекту.")
            return
        
        text = f"📁 {project}\n\n"
        for f in files[-10:]:
            icon = "📄" if f["type"] == "document" else "🖼"
            text += f"{icon} {f['name']}\n"
        await query.edit_message_text(text)
    
    elif query.data.startswith("attach:"):
        parts = query.data.split(":", 2)
        project = parts[1]
        file_key = parts[2]
        
        # Достаём из context.user_data
        pending = context.user_data.get("pending_files", {})
        if file_key in pending:
            file_info = pending[file_key]
            save_file_meta(
                project=project,
                file_name=file_info["name"],
                file_id=file_info["file_id"],
                file_type=file_info["type"],
                chat_id=str(update.effective_chat.id),
            )
            del pending[file_key]
            context.user_data["pending_files"] = pending
            await query.edit_message_text(f"✅ Файл «{file_info['name']}» сохранён в проект «{project}»")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = update.message.text
    
    await update.message.chat.send_action("typing")
    reply = await ask_claude(text, chat_id)
    await update.message.reply_text(reply)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("🎙 Голосовое получено. Обрабатываю...")
    
    # Telegram даёт voice как аудио файл — скачиваем и транскрибируем через Whisper/Claude
    # Для простоты — просим пользователя написать текстом пока
    # (для полной реализации нужен Whisper API)
    await update.message.reply_text(
        "Голосовые принимаю! Для транскрипции включи в Telegram: "
        "Настройки → Чаты → Транскрибировать голосовые.\n\n"
        "Или просто скопируй текст и пришли мне — разберём по проектам 💪"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file_name = doc.file_name or "документ"
    file_id = doc.file_id
    
    # Сохраняем как pending
    if "pending_files" not in context.user_data:
        context.user_data["pending_files"] = {}
    
    file_key = file_id[:20]
    context.user_data["pending_files"][file_key] = {
        "name": file_name,
        "file_id": file_id,
        "type": "document",
    }
    
    # Кнопки выбора проекта
    keyboard = []
    for p in PROJECTS:
        keyboard.append([InlineKeyboardButton(p, callback_data=f"attach:{p}:{file_key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📄 {file_name}\n\nК какому проекту прикрепить?",
        reply_markup=reply_markup
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]  # берём лучшее качество
    file_id = photo.file_id
    caption = update.message.caption or "фото"
    
    if "pending_files" not in context.user_data:
        context.user_data["pending_files"] = {}
    
    file_key = file_id[:20]
    context.user_data["pending_files"][file_key] = {
        "name": caption,
        "file_id": file_id,
        "type": "photo",
    }
    
    keyboard = []
    for p in PROJECTS:
        keyboard.append([InlineKeyboardButton(p, callback_data=f"attach:{p}:{file_key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🖼 Фото получено\n\nК какому проекту прикрепить?",
        reply_markup=reply_markup
    )

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("лог", log_command))
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("проекты", projects_command))
    app.add_handler(CommandHandler("файлы", files_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
