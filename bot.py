# Импортируем необходимые библиотеки
import os, asyncio
import logging
import time
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests

# Настраиваем логирование для отслеживания работы бота
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Создаем глобальную переменную для хранения URL вебхука
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # URL для вебхука, который будет использоваться для получения обновлений

# Функция для создания фейкового HTTP-сервера
def create_fake_server():
    try:
        # Отправляем GET-запрос на URL бота каждые 10 минут
        while True:
            requests.get(WEBHOOK_URL)
            time.sleep(600)  # 600 секунд = 10 минут
    except Exception as e:
        logging.error(f"Ошибка при пинговании сервера: {str(e)}")

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Отправляем приветственное сообщение пользователю
        await update.message.reply_text('Привет!')
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /start: {str(e)}")

# Функция для настройки вебхука
async def setup_webhook(app: Application):
    try:
        # Устанавливаем вебхук для бота
        await app.bot.set_webhook(url=WEBHOOK_URL)
    except Exception as e:
        logging.error(f"Ошибка при настройке вебхука: {str(e)}")

# Основная функция для запуска бота
async def main():
    # Создаем приложение Telegram
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    # Добавляем обработчик команды /start
    app.add_handler(CommandHandler("start", start))
    
    # Настраиваем вебхук
    await setup_webhook(app)
    
    # Запускаем приложение
    await app.initialize()
    await app.updater.start_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "10000")), url_path=os.getenv("TELEGRAM_TOKEN"))
    await app.updater.bot.set_webhook(f"https://{os.getenv('EXTERNAL_URL')}/{os.getenv('TELEGRAM_TOKEN')}")
    await app.start()

# Функция для запуска фейкового сервера в отдельном потоке
def run_fake_server():
    server_thread = threading.Thread(target=create_fake_server)
    server_thread.daemon = True
    server_thread.start()

if __name__ == '__main__':
    # Запускаем фейковый сервер
    run_fake_server()
    
    # Запускаем основной цикл бота
    try:
        # Запускаем асинхронное приложение
        application = asyncio.run(main())
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {str(e)}")
