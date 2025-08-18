import os  # Для получения переменных окружения
import asyncio  # Для асинхронных операций
from aiohttp import web  # Для создания фейкового HTTP-сервера
from telegram import Update  # Для обработки обновлений
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes  # Для бота

# Получаем токен бота из переменной окружения
TOKEN = os.getenv("BOT_TOKEN")  # В настройках Render добавьте переменную окружения BOT_TOKEN

# Получаем порт для сервера (обычно Render использует PORT)
PORT = int(os.getenv("PORT", "8080"))  # Значение по умолчанию — 8080

# Получаем chat_id для пинга (можно указать свой chat_id)
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))  # Введите свой chat_id в переменной окружения

# Создаем объект Application — основной компонент бота
application = ApplicationBuilder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет!")  # Отправляем сообщение "Привет!"

# Регистрация обработчика команды /start
application.add_handler(CommandHandler("start", start))

# Создаем фейковый HTTP-сервер для обхода автоотключения Render
async def handle(request):
    return web.Response(text="OK")  # Просто возвращает "OK" при любом запросе

async def start_web_server():
    app = web.Application()  # Создаем aiohttp приложение
    app.router.add_get('/', handle)  # Обработка GET-запросов по корню "/"
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)  # Запуск сервера на всех интерфейсах
    await site.start()

# Функция для самопинга бота каждые 10 минут
async def ping_self():
    while True:
        try:
            await asyncio.sleep(600)  # Ждем 600 секунд (10 минут)
            await application.bot.send_message(MY_CHAT_ID, "Пинг!")  # Отправляем сообщение себе или в чат
        except Exception as e:
            print(f"Ошибка при пинге: {e}")

# Основная функция запуска сервиса
async def main():
    await start_web_server()   # Запускаем фейковый HTTP-сервер
    asyncio.create_task(ping_self())   # Запускаем задачу пинга каждые 10 минут
    await application.run_polling()   # Запускаем polling для обработки команд

# Точка входа при запуске скрипта
if __name__ == "__main__":
    asyncio.run(main())   # Запускаем асинхронную функцию main()
