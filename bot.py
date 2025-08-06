# bot.py
"""
Telegram-бот для Render (webhook + self-ping keep-alive).

⸺ Зависимости (requirements.txt) ⸺
python-telegram-bot==20.10
openpyxl==3.1.2
requests>=2.31
"""

import os
import json
import logging
import threading
import time
import asyncio
from pathlib import Path

import requests
from openpyxl import Workbook
from telegram import (
    Update,
    InputMediaDocument,
    constants,        # для parse_mode, если понадобится
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ────────────────────────────────
# Конфигурация окружения
# ────────────────────────────────
BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]                     # токен бота
# URL внешней страницы в Render доступен через переменную окружения
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")      # например  my-service.onrender.com
PORT       = int(os.environ.get("PORT", 10000))         # Render задаёт PORT сам

# Путь webhook-а (добавляем токен, чтобы Telegram проверял secret)
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = f"https://{RENDER_URL}{WEBHOOK_PATH}"

# Файл, в котором храним связи chat_id → message_id
DATA_DIR        = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MSG_STORE_FILE  = DATA_DIR / "msg_store.json"

# Настраиваем логирование
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ────────────────────────────────
# Утилиты для хранения message_id
# ────────────────────────────────
def _load_store() -> dict:
    if MSG_STORE_FILE.exists():
        try:
            return json.loads(MSG_STORE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Файл msg_store повреждён, создаю заново")
    return {}


def _save_store(store: dict) -> None:
    MSG_STORE_FILE.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


# ────────────────────────────────
# Хендлеры команд
# ────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start  →  Привет!
    """
    await update.message.reply_text("Привет!")


async def excel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /excel → создать/заменить Excel-файл и переслать (или отредактировать первое своё сообщение).
    """
    chat_id = update.effective_chat.id

    # 1️⃣ Создаём Excel-файл «test.xlsx» с A1 = "тест"
    file_name = "test.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "тест"
    wb.save(file_name)

    # 2️⃣ Пытаемся найти сохранённый message_id
    store = _load_store()
    msg_id = store.get(str(chat_id))

    if msg_id:  # файл уже был отправлен раньше — редактируем сообщение
        try:
            logger.info(f"Попытка обновить документ в сообщении {msg_id=}")
            with open(file_name, "rb") as f:
                media = InputMediaDocument(media=f, filename=file_name)
                await context.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=msg_id,
                    media=media,
                )
            await update.message.reply_text("Файл обновлён ✅")
            return
        except Exception as exc:  # noqa: BLE001
            # Если не получилось (сообщение удалено, истёк TTL и т.д.) — логируем и продолжаем
            logger.warning("Не удалось изменить сообщение: %s", exc)

    # 3️⃣ Иначе отправляем новый документ и запоминаем message_id
    logger.info("Отправка нового документа")
    sent_msg = await context.bot.send_document(
        chat_id=chat_id,
        document=open(file_name, "rb"),  # pylint: disable=consider-using-with
        filename=file_name,
    )
    # Сохраняем id первого сообщения с Excel-файлом
    store[str(chat_id)] = sent_msg.message_id
    _save_store(store)
    await update.message.reply_text("Файл отправлен ✅")


# ────────────────────────────────
# Фоновый поток для keep-alive
# ────────────────────────────────
def _keep_awake(url: str, interval: int = 600) -> None:
    """
    Каждые `interval` секунд отправляет GET на свой адрес,
    чтобы Render не перевёл сервис в спящий режим.
    Запускается как daemon-поток при импорте модуля.
    """
    def _ping() -> None:
        while True:
            try:
                # Запрашиваем некритичный URL: может быть 200 или 404 — не важно,
                # главное, чтобы был любой входящий HTTP-трафик.
                logger.debug("Self-ping %s", url)
                requests.get(url, timeout=10)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ошибочный self-ping: %s", exc)
            time.sleep(interval)

    threading.Thread(target=_ping, daemon=True, name="keep-awake").start()


# Запускаем keep-alive сразу при импорте (gunicorn импортирует модуль ➞ поток уже работает)
if RENDER_URL:        # Проверяем, чтобы не упасть локально
    _keep_awake(f"https://{RENDER_URL}")


# ────────────────────────────────
# Функция main запускает webhook-сервер
# ────────────────────────────────
def main() -> None:
    """
    Точка входа для Render/Gunicorn: создаёт Application и запускает webhook-сервер.
    """
    # Build Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем хендлеры напрямую
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("excel", excel_cmd))

    # Устанавливаем webhook (Telegram будет отправлять апдейты на WEBHOOK_URL)
    # run_webhook поднимает внутр. Tornado-сервер (функции fake HTTP-сервера достаточно).
    logger.info("Запуск run_webhook на порту %s", PORT)
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_path=WEBHOOK_PATH,
        # Адрес, под которым Telegram будет стучаться
        webhook_url=WEBHOOK_URL,
        # Запускаем без сертификатов (Render уже работает за HTTPS-прокси)
        cert=None,
        key=None,
        secret_token=None,  # можно добавить, если хочется >1 слова
    )


# Для локального теста: python bot.py
if __name__ == "__main__":
    #main()
    asyncio.run(main())
