import logging
import os
import sqlite3
import sys
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Включаем логирование для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ORGANIZER_CHAT_ID = os.environ.get("ORGANIZER_CHAT_ID")

if not TELEGRAM_BOT_TOKEN:
    logger.error("Ошибка: Переменная окружения TELEGRAM_BOT_TOKEN не установлена!")
    sys.exit(1)
if not ORGANIZER_CHAT_ID:
    logger.error(
        "Ошибка: Переменная окружения ORGANIZER_CHAT_ID не установлена! "
        "Установите ваш Telegram User ID в качестве значения."
    )
    sys.exit(1)
else:
    try:
        ORGANIZER_CHAT_ID = int(ORGANIZER_CHAT_ID)
    except ValueError:
        logger.error("Ошибка: ORGANIZER_CHAT_ID должен быть числом (вашим Telegram User ID)!")
        sys.exit(1)

# --- Настройка базы данных (SQLite) ---
DB_NAME = "applications_data.db"

def init_db():
    """Инициализирует базу данных и создает таблицу, если её нет."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        application_text TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    conn.commit()
    conn.close()
    logger.info(f"База данных '{DB_NAME}' инициализирована.")

def save_application_to_db(
    user_id: int, username: str, first_name: str, last_name: str, application_text: str
):
    """Сохраняет заявку пользователя в базу данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO applications (user_id, username, first_name, last_name, application_text)
        VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, username, first_name, last_name, application_text),
        )
        conn.commit()
        logger.info(f"Заявка от user_id: {user_id} сохранена в БД.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении заявки в БД: {e}")
    finally:
        conn.close()

# --- Состояния для ConversationHandler ---
HANDLE_APPLICATION_SUBMISSION = 1

# --- Обработчики команд и сообщений ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и основную клавиатуру при команде /start."""
    user = update.effective_user
    welcome_message = (
        f"👋 Привет, {user.mention_html()}!\n\n"
        "Это бот для подачи заявок. Пожалуйста, ознакомьтесь с правилами:\n\n"
        "📜 **Правила:**\n"
        "1. Нажмите кнопку 'Подать заявку', чтобы увидеть шаблон.\n"
        "2. Внимательно заполните заявку согласно шаблону и отправьте ее ОДНИМ сообщением.\n"
        "3. Ваша заявка будет автоматически переслана организатору.\n\n"
        "Удачи!"
    )
    keyboard = [[KeyboardButton("Подать заявку")]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=False, resize_keyboard=True
    )
    await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    return ConversationHandler.END


async def request_application_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Вызывается при нажатии кнопки 'Подать заявку'.
    Отправляет шаблон заявки и переходит в состояние ожидания заявки.
    """
    application_template_message = (
        "📝 **Шаблон для заполнения заявки:**\n\n"
        "Пожалуйста, скопируйте этот шаблон, заполните его и отправьте одним сообщением.\n\n"
        "------------------------------------\n"
        "1. Ваше полное имя (ФИО):\n"
        "   [Ваш ответ]\n\n"
        "2. Ваш контактный номер телефона:\n"
        "   [Ваш ответ]\n\n"
        "3. Адрес электронной почты (Email):\n"
        "   [Ваш ответ]\n\n"
        "4. Подробное описание вашей идеи/предложения/запроса:\n"
        "   [Ваш развернутый ответ]\n\n"
        "5. Почему именно ваша заявка должна быть рассмотрена (ваши сильные стороны, мотивация и т.д.):\n"
        "   [Ваш ответ]\n"
        "------------------------------------\n\n"
        "🕒 **Ожидаю вашу заполненную заявку...**"
    )
    await update.message.reply_text(application_template_message)
    return HANDLE_APPLICATION_SUBMISSION


async def handle_application_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Обрабатывает текстовое сообщение пользователя, которое предполагается является заявкой.
    Сохраняет заявку в БД и пересылает организатору.
    """
    user = update.effective_user
    application_text = update.message.text

    if not application_text or len(application_text.strip()) < 20:
        await update.message.reply_text(
            "❗️ Ваша заявка кажется слишком короткой или пустой. "
            "Пожалуйста, убедитесь, что вы заполнили все поля шаблона и попробуйте снова."
        )
        return HANDLE_APPLICATION_SUBMISSION

    save_application_to_db(
        user_id=user.id,
        username=user.username or "N/A",
        first_name=user.first_name or "N/A",
        last_name=user.last_name or "",
        application_text=application_text,
    )

    await update.message.reply_text(
        "✅ Спасибо! Ваша заявка принята и успешно отправлена организатору.\n"
        "Ожидайте ответа."
    )

    organizer_message = (
        f"🔔 **Новая заявка!** 🔔\n\n"
        f"👤 **От пользователя:**\n"
        f"   - ID: {user.id}\n"
        f"   - Username: @{user.username if user.username else 'Не указан'}\n"
        f"   - Имя: {user.first_name} {user.last_name or ''}\n\n"
        f"📝 **Текст заявки:**\n"
        f"```\n{application_text}\n```"
    )
    try:
        await context.bot.send_message(
            chat_id=ORGANIZER_CHAT_ID, text=organizer_message, parse_mode="Markdown"
        )
        logger.info(f"Заявка от user_id: {user.id} переслана организатору (ID: {ORGANIZER_CHAT_ID}).")
    except Exception as e:
        logger.error(f"Не удалось отправить заявку организатору: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при пересылке вашей заявки организатору. "
            "Пожалуйста, попробуйте подать заявку позже или свяжитесь с поддержкой."
        )
        if str(user.id) != str(ORGANIZER_CHAT_ID):
            try:
                await context.bot.send_message(
                    chat_id=ORGANIZER_CHAT_ID,
                    text=f"🔴 ОШИБКА: Не удалось автоматически переслать заявку от пользователя @{user.username} (ID: {user.id}). Подробности в логах сервера."
                )
            except Exception as e_admin:
                logger.error(f"Не удалось уведомить организатора об ошибке пересылки: {e_admin}")
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Отменяет текущий диалог подачи заявки."""
    user = update.effective_user
    logger.info(f"Пользователь {user.first_name} (ID: {user.id}) отменил диалог.")
    await update.message.reply_text(
        "Подача заявки отменена. Вы можете начать заново в любой момент, нажав 'Подать заявку' или отправив команду /start.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Подать заявку")]],
            one_time_keyboard=False,
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END


async def unknown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает неизвестные команды."""
    await update.message.reply_text(
        "🤷‍♂️ Извините, я не понимаю эту команду. "
        "Используйте /start для начала работы или кнопку 'Подать заявку'."
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные обновлениями."""
    logger.error(msg="Исключение при обработке обновления:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😔 Произошла внутренняя ошибка. Мы уже работаем над этим. Пожалуйста, попробуйте позже."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

async def initiate_hourly_restart(context: ContextTypes.DEFAULT_TYPE):
    """Инициирует плановый перезапуск бота."""
    logger.info("Плановый перезапуск через 1 час. Бот будет остановлен для перезагрузки.")
    try:
        await context.bot.send_message(
            chat_id=ORGANIZER_CHAT_ID,
            text="⚙️ Бот будет планово перезапущен через несколько секунд для обновления."
        )
        logger.info(f"Уведомление о перезапуске отправлено организатору (ID: {ORGANIZER_CHAT_ID}).")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение о перезапуске организатору: {e}")

    await asyncio.sleep(10) # Пауза для отправки сообщения

    logger.info("Инициирую остановку бота для перезапуска...")
    sys.exit(0) # Завершение процесса для перезапуска Railway


def main() -> None:
    """Основная функция для запуска бота."""
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex("^Подать заявку$"),
                request_application_action,
            )
        ],
        states={
            HANDLE_APPLICATION_SUBMISSION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, handle_application_message
                )
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.Regex("^Подать заявку$"), request_application_action)
        ],
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command_handler))
    application.add_error_handler(error_handler)

    # Настройка ежечасного перезапуска
    # Убедитесь, что в requirements.txt указано: python-telegram-bot[job-queue]
    job_queue = application.job_queue
    if job_queue: # Проверка, что job_queue успешно инициализирован
        job_queue.run_once(initiate_hourly_restart, 3600, name="hourly_restart_job")
        logger.info("Запланирована задача на ежечасный перезапуск бота.")
    else:
        logger.warning("JobQueue не настроен. Ежечасный перезапуск не будет работать. "
                       "Проверьте установку: pip install python-telegram-bot[job-queue]")


    logger.info("Запуск бота...")
    application.run_polling()


if __name__ == "__main__":
    main()