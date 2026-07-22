import os
from dotenv import load_dotenv

load_dotenv()  # Загружает токен из файла .env
import logging
import random
import asyncio
import json
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === 1. НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === НАСТРОЙКИ И ПЕРЕМЕННЫЕ ===
ADMIN_TELEGRAM_ID = 123456789  # Вставьте сюда ваш Telegram ID
DATA_FILE = "users.json"

# База данных кулинарных фактов
COOKING_FACTS = [
    "Белый шоколад на самом деле не шоколад, так как он не содержит какао-порошка — только какао-масло.",
    "Мед — единственный продукт питания, который никогда не портится. Его находили в египетских гробницах вполне съедобным.",
    "Чтобы лук не колол глаза при резке, положите его в холодильник на 30 минут перед приготовлением.",
    "Яблоки плавают в воде, потому что они на 25% состоят из воздуха."
]

# База данных рецептов
RECIPES_DATABASE = [
    {
        "id": 1,
        "title": "Простая яичница с луком 🍳",
        "ingredients": {"яйца", "лук"},
        "instruction": "Обжарьте мелко нарезанный лук, затем разбейте туда яйца. Готовьте 3-5 минут.",
        "photo": "https://images.unsplash.com/photo-1525351484163-7529414344d8?w=500" 
    },
    {
        "id": 2,
        "title": "Классический омлет 🥛",
        "ingredients": {"яйца", "молоко"},
        "instruction": "Взбейте яйца с молоком. Вылейте на сковороду и готовьте под крышкой.",
        "photo": "https://images.unsplash.com/photo-1494597564530-871f2b93ac55?w=500"
    }
]

ALL_KNOWN_INGREDIENTS = set().union(*(r["ingredients"] for r in RECIPES_DATABASE))

# Глобальные словари
USERS_DATA = {}   # База пользователей (сохраняется в JSON)
USER_STATES = {}  # Временные состояния анкеты (в памяти)

# === 2. ФУНКЦИИ РАБОТЫ С JSON ===
def load_data():
    """Загружает данные пользователей из JSON-файла при старте бота."""
    global USERS_DATA
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                USERS_DATA = json.load(f)
            logging.info("Данные пользователей успешно загружены из JSON.")
        except Exception as e:
            logging.error(f"Ошибка при загрузке JSON: {e}")
            USERS_DATA = {}
    else:
        USERS_DATA = {}

def save_data():
    """Сохраняет текущий словарь USERS_DATA в JSON-файл."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(USERS_DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка при сохранении JSON: {e}")

def init_user_if_not_exists(user_id_str):
    """Инициализирует структуру данных для нового пользователя."""
    if user_id_str not in USERS_DATA:
        USERS_DATA[user_id_str] = {
            "favorites": [],
            "profile": {
                "name": "Не указано",
                "age": "Не указано",
                "address": "Не указано",
                "preferences": "Не указано",
                "color": "Не указано"
            }
        }
        save_data()

# === 3. КЛАВИАТУРЫ ===
def get_main_keyboard():
    buttons = [
        ['🎲 Случайный рецепт', '❤️ Избранное'],
        ['⏱️ Кухонный таймер', '✍️ Предложить рецепт'],
        ['👤 Профиль', 'Настроение', 'Совет дня'],
        ['О боте']
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_timer_keyboard():
    buttons = [
        ['🥚 Всмятку (4 мин)', '🥚 Вкрутую (9 мин)'],
        ['☕ Чай (3 мин)', '❌ Отмена']
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# === 4. КОМАНДЫ И ОБРАБОТЧИКИ ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исправленный обработчик команды /start без ошибки разметки."""
    user_id_str = str(update.effective_user.id)
    init_user_if_not_exists(user_id_str)
    USER_STATES[update.effective_user.id] = None 
    
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👨‍🍳\n\n"
        f"Я твой кулинарный помощник.\n\n"
        f"Нажми кнопку «👤 Профиль» ниже или отправь /edit_profile, чтобы настроить анкету!",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    await update.message.reply_text(
        "📚 Памятка по командам:\n"
        "— Кнопка '👤 Профиль': просмотр ваших данных.\n"
        "— Команда /edit_profile: запуск анкеты для редактирования профиля.\n"
        "— Кнопка '✍️ Предложить рецепт': отправка рецепта автору бота.",
        reply_markup=get_main_keyboard()
    )

async def edit_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск пошагового заполнения профиля."""
    USER_STATES[update.effective_user.id] = "профиль_имя"
    await update.message.reply_text(
        "📝 Начинаем заполнение профиля!\nКак вас зовут? (или отправьте '❌ Отмена' для выхода):"
    )

async def run_cooking_timer(update: Update, seconds: int, dish_name: str):
    """Фоновая задача для кухонного таймера."""
    await asyncio.sleep(seconds)
    await update.message.reply_text(
        f"🔔 ДЗЫНЬ! Прошло {seconds // 60} мин. Ваше блюдо '{dish_name}' готово! 👨‍🍳",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик входящих текстовых сообщений."""
    user_id = update.effective_user.id
    user_id_str = str(user_id)  # Преобразуем ID в строку для ключа JSON
    user_text = update.message.text
    user_text_lower = user_text.lower()

    init_user_if_not_exists(user_id_str)
    current_state = USER_STATES.get(user_id)

    # --- ОТМЕНА ДЕЙСТВИЯ ---
    if 'отмена' in user_text_lower:
        USER_STATES[user_id] = None
        await update.message.reply_text("Действие отменено.", reply_markup=get_main_keyboard())
        return

    # --- ИСПРАВЛЕННЫЙ ПРОСМОТР ПРОФИЛЯ (без ошибки Markdown) ---
    if 'профиль' in user_text_lower:
        USER_STATES[user_id] = None  
        profile = USERS_DATA[user_id_str]["profile"]
        profile_text = (
            f"📋 Ваш кулинарный профиль:\n\n"
            f"👤 Имя: {profile.get('name', 'Не указано')}\n"
            f"🎂 Возраст: {profile.get('age', 'Не указано')}\n"
            f"🏠 Адрес: {profile.get('address', 'Не указано')}\n"
            f"🥗 Предпочтения: {profile.get('preferences', 'Не указано')}\n"
            f"🎨 Любимый цвет: {profile.get('color', 'Не указано')}\n\n"
            f"💡 Чтобы изменить данные, нажмите: /edit_profile"
        )
        await update.message.reply_text(profile_text, reply_markup=get_main_keyboard())
        return

    # --- ПОШАГОВАЯ АНКЕТА ПРОФИЛЯ (FSM) ---
    if current_state and current_state.startswith("профиль_"):
        if current_state == "профиль_имя":
            USERS_DATA[user_id_str]["profile"]["name"] = user_text
            USER_STATES[user_id] = "профиль_возраст"
            await update.message.reply_text("Отлично! Теперь введите ваш возраст:")
        elif current_state == "профиль_возраст":
            USERS_DATA[user_id_str]["profile"]["age"] = user_text
            USER_STATES[user_id] = "профиль_адрес"
            await update.message.reply_text("Введите ваш адрес (город/страну):")
        elif current_state == "профиль_адрес":
            USERS_DATA[user_id_str]["profile"]["address"] = user_text
            USER_STATES[user_id] = "профиль_предпочтения"
            await update.message.reply_text("Каковы ваши кулинарные предпочтения? (например: веган):")
        elif current_state == "профиль_предпочтения":
            USERS_DATA[user_id_str]["profile"]["preferences"] = user_text
            USER_STATES[user_id] = "профиль_цвет"
            await update.message.reply_text("И последний вопрос: какой ваш любимый цвет?")
        elif current_state == "профиль_цвет":
            USERS_DATA[user_id_str]["profile"]["color"] = user_text
            USER_STATES[user_id] = None
            save_data()  # Сохраняем обновленные данные в JSON
            await update.message.reply_text("🎉 Профиль успешно сохранен в базу JSON!", reply_markup=get_main_keyboard())
        return

    # --- КУХОННЫЙ ТАЙМЕР ---
    if 'таймер' in user_text_lower:
        await update.message.reply_text("Что будем варить? Выберите режим:", reply_markup=get_timer_keyboard())
        return
    elif 'мин)' in user_text:
        if 'Всмятку' in user_text:
            await update.message.reply_text("Поставил таймер на 4 минуты.", reply_markup=get_main_keyboard())
            asyncio.create_task(run_cooking_timer(update, 240, "Яйца всмятку"))
        elif 'Вкрутую' in user_text:
            await update.message.reply_text("Поставил таймер на 9 минут.", reply_markup=get_main_keyboard())
            asyncio.create_task(run_cooking_timer(update, 540, "Яйца вкрутую"))
        elif 'Чай' in user_text:
            await update.message.reply_text("Поставил таймер на 3 минуты.", reply_markup=get_main_keyboard())
            asyncio.create_task(run_cooking_timer(update, 180, "Идеальный чай"))
        return

    # --- ПРЕДЛОЖИТЬ РЕЦЕПТ АДМИНУ ---
    if current_state == "ожидание_рецепта":
        USER_STATES[user_id] = None
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=f"✉️ Новый рецепт от @{update.effective_user.username} (ID: {user_id}):\n\n{user_text}"
        )
        await update.message.reply_text("Спасибо! Ваш рецепт успешно отправлен. 👍", reply_markup=get_main_keyboard())
        return

    if 'предложить рецепт' in user_text_lower:
        USER_STATES[user_id] = "ожидание_рецепта"
        await update.message.reply_text("Напишите ваш рецепт в одном сообщении.", reply_markup=get_main_keyboard())
        return

    # --- ИЗБРАННОЕ ---
    if 'избранное' in user_text_lower:
        fav_ids = USERS_DATA[user_id_str].get("favorites", [])
        if not fav_ids:
            await update.message.reply_text("Ваша книга закладок пока пуста.")
            return
        await update.message.reply_text("❤️ Ваши сохраненные рецепты:")
        for recipe in RECIPES_DATABASE:
            if recipe["id"] in fav_ids:
                caption_text = f"{recipe['title']}\n\n📖 {recipe['instruction']}"
                await update.message.reply_photo(photo=recipe["photo"], caption=caption_text)
        return

    # --- СЛУЧАЙНЫЙ РЕЦЕПТ ---
    if 'случайный рецепт' in user_text_lower:
        recipe = random.choice(RECIPES_DATABASE)
        caption_text = f"🎲 Случайный выбор:\n\n{recipe['title']}\n\n📖 {recipe['instruction']}"
        await update.message.reply_photo(photo=recipe["photo"], caption=caption_text)
        return

    # --- ДОПОЛНИТЕЛЬНЫЕ КНОПКИ ---
    if user_text_lower == 'настроение':
        await update.message.reply_text("📊 Отличное! Готов к готовке! 👨‍🍳")
        return
    elif user_text_lower == 'совет дня':
        await update.message.reply_text("💡 Совет дня: Пересоленный соус спасет сырая картофелина на 10 минут.")
        return
    elif user_text_lower == 'о боте':
        await update.message.reply_text("👨‍🍳 Кулинарный бот с рецептами который сможет помочь в любую минуту.")
        return

    # Если ни одна команда не подошла — присылаем случайный кулинарный факт
    random_fact = random.choice(COOKING_FACTS)
    await update.message.reply_text(f"💡 Интересный факт:\n{random_fact}")

# === 5. ЗАПУСК БОТА ===
def main():
    load_data()

    # Берем токен из файла .env
    token = os.getenv("BOT_TOKEN")

    # Указываем прокси PythonAnywhere
    proxy_url = "http://proxy.server:3128"

    application = (
        Application.builder()
        .token(token)
        .proxy(proxy_url)
        .get_updates_proxy(proxy_url)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("edit_profile", edit_profile_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот успешно запущен и готов к работе...")

    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()