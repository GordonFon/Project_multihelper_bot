import sqlite3
import requests
import speech_recognition as sr
import random
import pytz
from config_reader import config
from check_components import check_database, check_folders
from telegram import Update, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CallbackContext, CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters
from moviepy import AudioFileClip, VideoFileClip
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

VIDEO = 1
NAME, PURPOSE = range(2)
CHOOSING_METHOD, WAITING_COORDS, WAITING_ADDRESS = range(3)
TIMEZONE, DATE, TIME, EVENT_NAME = range(4)

user_states = {}

scheduler = AsyncIOScheduler()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "Вас приветствует бот-помощник!\n"
        "Используйте команду /register, чтобы зарегистрироваться."
        "Если регистрация не пройдена, вы не сможете добавить меня в беседу."
    )
    await update.message.reply_text(welcome_message)

    info_message = (
        "Вот что я могу:\n"
        "- Присоединиться к твоей беседе и помогать там\n"
        "- Расшифровывать аудио и видео сообщения\n"
        "- Отправить карту местности по написанному тобой адресу\n"
        "- Напоминать о важных событиях\n"
        "- Для того чтобы узнать о всех возможностях, введите /help\n"
    )
    await update.message.reply_text(info_message)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_message = (
        "Вот что я могу:\n"
        "/menu - Вызов меню команд\n"
        "/event - Установка напоминания на заданную дату\n"
        "/map - Отправить карту местности по написанному тобой адресу\n"
        "/gif - Преобразование вашего видео в gif\n"
        "/dice 'Число без кавычек' - Бросок кубика заданного размера\n"
        "/check - Проверить регистрацию\n"
        "/my_geo - Важно! Эта команда работает только при вызове из меню. Отправка вашей текущей геолокации\n"
        "Важно! Расшифровка аудио и видео сообщений включена автоматически! Чтобы отключить или включить расшифровку напишите /stop_decode или /start_decode соответственно\n"
    )
    await update.message.reply_text(info_message)


async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().split()

    if len(text) == 2 and text[0] == "/dice":
        try:
            sides = int(text[1])

            result = random.randint(1, sides)

            await update.message.reply_text(f"Выпало {result}")
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректное число для кубика")
    else:
        await update.message.reply_text("Используйте формат: /dice 'число'")

# Регистрация
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    with sqlite3.connect("users_db.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM registered_users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            await update.message.reply_text("Вы уже зарегистрированы!")
            return ConversationHandler.END

    await update.message.reply_text(
        "Вы начали процесс регистрации, для отмены введите /cancel\n"
        "Пожалуйста, введите ваше имя:")

    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["username"] = update.message.text
    await update.message.reply_text("Введите цель использования бота:")
    return PURPOSE


async def get_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = context.user_data["username"]
    purpose = update.message.text

    with sqlite3.connect("users_db.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO registered_users (user_id, name, purpose) VALUES (?, ?, ?)",
            (user_id, username, purpose)
        )
        conn.commit()

    await update.message.reply_text("Вы успешно зарегистрированы!")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена")
    return ConversationHandler.END


async def check_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    with sqlite3.connect("users_db.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM registered_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        if result is None:
            await update.message.reply_text("Пожалуйста, пройдите регистрацию с помощью команды /register")
        else:
            await update.message.reply_text("Вы зарегистрированы!")

# Проверка регистрации при добавлении
async def handle_added_to_group(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id

    try:
        with sqlite3.connect("users_db.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM registered_users")
            registered_user_id = [row[0] for row in cursor.fetchall()]

        registered_user_found = False

        for user_id in registered_user_id:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status not in ["left", "kicked"]:
                    registered_user_found = True
                    break
            except Exception as e:
                pass

        if not registered_user_found:
            await update.message.reply_text("Бот покинул чат, так как ни один участник не зарегистрирован")
            await context.bot.leave_chat(chat_id)
        else:
            await update.message.reply_text("Всем привет! Чтобы узнать о моих возможностях, напишите /help")

    except Exception as e:
        print(f"Error: {e}")
        await context.bot.leave_chat(chat_id)

# Напоминание
async def event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, укажите смещение часового пояса\n"
        "Например, для Москвы введите +3, для Владивостока +10, для Вашингтона -4."
        "Для отмены создания напоминания введите /cancel"
    )
    return TIMEZONE


async def get_timezone(update, context) -> int:
    user_input = update.message.text.strip()
    try:
        offset = int(user_input)
        if offset < -12 or offset > 14:
            await update.message.reply_text(
                "Ошибка: смещение должно быть в диапазоне от -12 до +14. Пожалуйста, введите корректное значение:"
            )
            return TIMEZONE
        timezone_str = f'Etc/GMT{"-" if offset >= 0 else ""}{abs(offset)}'
        context.user_data["timezone"] = timezone_str
    except ValueError:
        await update.message.reply_text(
            "Ошибка: введите целое число со знаком. Например, +3 или -4."
        )
        return TIMEZONE

    await update.message.reply_text("Теперь введите дату события (в формате ДД.ММ.ГГГГ):")
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    timezone_str = context.user_data.get("timezone")
    try:
        event_date = datetime.strptime(user_input, "%d.%m.%Y")
        current_date = datetime.now(pytz.timezone(timezone_str)).date()

        if event_date.date() < current_date:
            await update.message.reply_text(
                "Ошибка: дата не может быть меньше сегодняшней. Пожалуйста, введите корректную дату (в формате ДД.ММ.ГГГГ):")
            return DATE

        context.user_data['date'] = user_input
        await update.message.reply_text("Введите время события (в формате ЧЧ:ММ):")
        return TIME
    except ValueError:
        await update.message.reply_text("Ошибка: неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.")
        return DATE


async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    timezone_str = context.user_data.get("timezone", "UTC")
    try:
        event_time = datetime.strptime(user_input, "%H:%M").time()
        current_time = datetime.now(pytz.timezone(timezone_str)).time()

        if context.user_data['date'] == datetime.now(pytz.timezone(timezone_str)).strftime("%d.%m.%Y") and event_time < current_time:
            await update.message.reply_text(
                "Ошибка: время не может быть меньше текущего. Пожалуйста, введите корректное время (в формате ЧЧ:ММ):")
            return TIME

        context.user_data["time"] = user_input
        await update.message.reply_text("Введите название события:")
        return EVENT_NAME
    except ValueError:
        await update.message.reply_text("Ошибка: неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.")
        return TIME


async def get_event_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event_name'] = update.message.text
    date = context.user_data['date']
    time = context.user_data['time']
    event_name = context.user_data['event_name']
    timezone_str = context.user_data['timezone']

    event_datetime_str = f"{date} {time}"
    event_datetime = datetime.strptime(event_datetime_str, "%d.%m.%Y %H:%M")

    tz = pytz.timezone(timezone_str)

    event_datetime = event_datetime.replace(tzinfo=tz)

    scheduler.add_job(send_reminder, 'date', run_date=event_datetime,
                      args=[update.message.chat.id, event_name, context.application])
    scheduler.start()

    await update.message.reply_text(
        f"Напоминание на событие '{event_name}' запланировано на {event_datetime_str}")
    return ConversationHandler.END

async def send_reminder(chat_id, event_name, application):
    await application.bot.send_message(chat_id, f"Напоминание: {event_name}")


# Флаги для БД
def set_flag(chat_id, flag):
    conn = sqlite3.connect("users_db.db")
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO decode_flag (chat_id, flag) VALUES (?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET flag=excluded.flag
    ''', (chat_id, flag))
    conn.commit()
    conn.close()


def get_flag(chat_id):
    conn = sqlite3.connect("users_db.db")
    cursor = conn.cursor()
    cursor.execute("SELECT flag FROM decode_flag WHERE chat_id = ?", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 1


# Расшифровка голосовых сообщений
async def check_decode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    text = update.message.text.lower()

    if text == "/start_decode":
        set_flag(chat_id, 1)
        await update.message.reply_text("Расшифровка аудио сообщений включена!")
    elif text == "/stop_decode":
        set_flag(chat_id, 0)
        await update.message.reply_text("Расшифровка аудио сообщений отключена!")


async def get_content(bot, file_id: str, filename: str):
    new_file = await bot.get_file(file_id)
    await new_file.download_to_drive(filename)


async def voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    flag = get_flag(chat_id)
    if flag == 0:
        return

    file_id = update.message.voice.file_id
    filename = "audio_folder/audio.ogg"
    await get_content(context.bot, file_id, filename)
    text = recognize(filename)
    await update.message.reply_text(text)


async def video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    flag = get_flag(chat_id)
    if flag == 0:
        return

    file_id = update.message.video_note.file_id
    filename = "audio_folder/video.mp4"
    await get_content(context.bot, file_id, filename)
    text = recognize(filename)
    await update.message.reply_text(text)


def recognize(filename: str):
    audio = AudioFileClip(filename)
    audio.write_audiofile("audio_folder/audio.wav")
    recognizer = sr.Recognizer()
    with sr.AudioFile("audio_folder/audio.wav") as source:
        audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language='ru-RU')
    return text


# Видео в гиф
def video_to_gif(video_path, gif_path):
    gif = VideoFileClip(video_path)
    gif.write_gif(gif_path)


async def gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте мне видео для преобразования его в gif\n"
                                    "Для отмены введите /cancel")
    return VIDEO


async def handle_video(update: Update, context: CallbackContext):
    video_id = update.message.video.file_id

    video_path = f"video_folder/video.mp4"
    gif_path = f"video_folder/videogif.gif"

    await get_content(context.bot, video_id, video_path)

    video_to_gif(video_path, gif_path)

    with open(gif_path, "rb") as gif:
        await update.message.reply_document(gif)

    return ConversationHandler.END

# Отправка карт
async def s_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Координаты", callback_data="coords"),
            InlineKeyboardButton("Адрес", callback_data="address"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Для отмены введите /cancel\n"
        "Выберите способ ввода:", reply_markup=reply_markup)
    user_states[update.effective_user.id] = None
    return CHOOSING_METHOD


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "coords":
        user_states[user_id] = WAITING_COORDS
        await query.message.reply_text("Введите координаты в формате: широта,долгота (например: 11.22,33.44)")
        return WAITING_COORDS
    elif query.data == "address":
        user_states[user_id] = WAITING_ADDRESS
        await query.message.reply_text("Введите адрес (например: Москва, МФТИ)")
        return WAITING_ADDRESS


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    if state == WAITING_COORDS:
        text = update.message.text.strip()
        try:
            lat_str, lon_str = [x.strip() for x in text.split(",")]
            lat, lon = float(lat_str), float(lon_str)
            await send_map(update, lat, lon)
        except Exception:
            await update.message.reply_text("Неверный формат координат. Попробуйте снова")
            return
        user_states[user_id] = None

    elif state == WAITING_ADDRESS:
        address = update.message.text.strip()
        coords = geocode(address)
        if coords:
            lat, lon = coords
            await send_map(update, lat, lon)
        else:
            await update.message.reply_text("Не удалось найти адрес. Попробуйте снова")
            return
        user_states[user_id] = None
    return ConversationHandler.END


async def send_map(update: Update, lat: float, lon: float):
    STATIC_API_URL = "https://static-maps.yandex.ru/v1"
    ll = f"{lon},{lat}"
    pt = f"{lon},{lat},pm2rdm"
    params = {
        "apikey": f"{config.static_api_token.get_secret_value()}",
        "ll": f"{ll}",
        "lang": "ru_RU",
        "size": "350,350",
        "z": 14,
        "pt": f"{pt}"
    }
    response = requests.get(STATIC_API_URL, params=params)

    if response.status_code == 200:
        await update.message.reply_photo(response.content)
    else:
        await update.message.reply_text("Ошибка при получении карты")


def geocode(address: str):
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        "apikey": config.geocoder_api_token.get_secret_value(),
        "format": "json",
        "geocode": address,
        "results": 1,
    }
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return None
    try:
        json_resp = resp.json()
        pos = json_resp["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        lon, lat = map(float, pos.split())
        return lat, lon
    except (KeyError, IndexError, ValueError):
        return None


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("/dice"), KeyboardButton("/check"), KeyboardButton("/gif")],
        [KeyboardButton("/event"), KeyboardButton("/map"), KeyboardButton("/my_geo", request_location=True)],
        [KeyboardButton("/help")],
        [KeyboardButton("/close")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Вот список того, что я умею:", reply_markup=reply_markup
    )


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню закрыто.", reply_markup=ReplyKeyboardRemove())


def main():
    db_name = "users_db.db"
    folders_to_check = ["audio_folder", "video_folder"]

    check_database(db_name)
    check_folders(folders_to_check)

    bot = Bot(token=config.bot_token.get_secret_value())
    application = ApplicationBuilder().bot(bot).build()

    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_purpose)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    event_handler = ConversationHandler(
        entry_points=[CommandHandler("event", event)],
        states={
            TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_timezone)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
            EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_event_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    gif_handler = ConversationHandler(
        entry_points=[CommandHandler("gif", gif)],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, handle_video)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    map_handler = ConversationHandler(
        entry_points=[CommandHandler("map", s_map)],
        states={
            CHOOSING_METHOD: [CallbackQueryHandler(button_handler)],
            WAITING_COORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            WAITING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    decode_handler = MessageHandler(
        filters.TEXT & (filters.Regex(r"^/start_decode$") | filters.Regex(r"^/stop_decode$")), check_decode)

    application.add_handler(decode_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("dice", dice))
    application.add_handler(CommandHandler("check", check_registration))
    application.add_handler(CommandHandler("close", close))

    application.add_handler(registration_handler)
    application.add_handler(event_handler)
    application.add_handler(gif_handler)
    application.add_handler(map_handler)

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_added_to_group))
    application.add_handler(MessageHandler(filters.VOICE, voice_message))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE, video_message))

    application.run_polling()

if __name__ == '__main__':
    main()
