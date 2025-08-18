import os  # Для доступа к переменным окружения
import asyncio  # Для асинхронных операций
from aiohttp import web, ClientSession  # Для веб-сервера и HTTP-запросов
from telegram import Update  # Для обработки обновлений
from telegram.ext import Application, CommandHandler, ContextTypes  # Для работы с ботом
import logging  # Для логирования

# Настройка логирования для отладки и мониторинга
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение токена бота из переменной окружения TELEGRAM_TOKEN
TOKEN = os.getenv("TELEGRAM_TOKEN")  # В Render добавьте переменную окружения TELEGRAM_TOKEN

# Получение URL для GET-запроса из переменной окружения RENDER_EXTERNAL_URL
TARGET_URL = os.getenv("RENDER_EXTERNAL_URL")  # В Render добавьте RENDER_EXTERNAL_URL

# Получение порта для сервера (Render использует PORT)
PORT = int(os.getenv("PORT", "8080"))  # Значение по умолчанию — 8080

# Глобальная переменная для хранения chat_id пользователя
chat_id = None

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_id  # Объявляем глобальную переменную для изменения внутри функции
    chat_id = update.message.chat.id  # Запоминаем chat_id из сообщения пользователя
    await update.message.reply_text('Привет!')  # Отправляем ответ "Привет!"

# Создаем простое HTTP-приложение для Render (чтобы не засыпать)
async def handle(request):
    return web.Response(text="OK")  # Возвращает "OK" при любом запросе

# Запуск фейкового HTTP-сервера на порту PORT
async def start_web_server():
    app = web.Application()  # Создаем aiohttp приложение
    app.router.add_get('/', handle)  # Обработка GET-запросов по корню "/"
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)  # Запуск сервера на всех интерфейсах
    await site.start()

# Функция, которая каждые 10 минут делает GET-запрос на TARGET_URL
async def periodic_get_request():
    global chat_id
    async with ClientSession() as session:  # Создаем HTTP-сессию для повторных запросов
        while True:
            if chat_id is not None:
                try:
                    await asyncio.sleep(600)  # Ждем 600 секунд (10 минут)
                    async with session.get(TARGET_URL) as response:
                        status = response.status
                        logging.info(f"GET {TARGET_URL} вернул статус {status}")
                except Exception as e:
                    logging.error(f"Ошибка при GET-запросе: {e}")
            else:
                await asyncio.sleep(10)  # Если chat_id еще не получен, ждем немного и проверяем снова

# Основная функция запуска бота и сервера
async def main():
    # Запускаем фейковый HTTP-сервер для Render (чтобы не засыпать)
    await start_web_server()

    # Создаем приложение Telegram бота с токеном из переменной окружения
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчик команды /start
    application.add_handler(CommandHandler('start', start_command))

    # Запускаем задачу периодического GET-запроса в фоне
    asyncio.create_task(periodic_get_request())

    # Запускаем polling для обработки команд Telegram (бесконечный цикл)
    await application.run_polling()

# Точка входа при запуске скрипта
if __name__ == '__main__':
    asyncio.run(main())  # Запускаем асинхронную функцию main()
