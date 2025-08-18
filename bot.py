import os
import asyncio
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", "8080"))

chat_id = None  # глобальная переменная для хранения chat_id

# Обработчик команды /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_id
    chat_id = update.effective_chat.id  # получаем chat_id из сообщения
    await update.message.reply_text('Привет!')  # отправляем ответ

# HTTP обработчик для Render (чтобы не засыпать)
async def handle(request):
    return web.Response(text="OK")

# Запуск фейкового сервера
async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

# Периодический GET-запрос каждые 10 минут
async def periodic_get_request():
    global chat_id
    async with ClientSession() as session:
        while True:
            if chat_id is not None:
                try:
                    await asyncio.sleep(600)  # ждем 10 минут
                    async with session.get(TARGET_URL) as response:
                        status = response.status
                        logging.info(f"GET {TARGET_URL} вернул статус {status}")
                except Exception as e:
                    logging.error(f"Ошибка при GET-запросе: {e}")
            else:
                await asyncio.sleep(10)  # если chat_id еще не получен, ждем немного

async def main():
    # Запускаем сервер для Render
    await start_web_server()

    # Создаем Application с токеном
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчик /start
    application.add_handler(CommandHandler('start', start_command))

    # Запускаем задачу периодического GET-запроса в фоне
    asyncio.create_task(periodic_get_request())

    # Запускаем бота (бесконечно)
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
