import os, asyncio
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==========================
# ВАШ Токен бота
# Получите у BotFather в Telegram
# TOKEN = 'ВАШ_ТОКЕН_ЗДЕСЬ'  # Замените на ваш токен

# URL вашего сервиса (после деплоя на Render)
# Например: https://your-app-name.onrender.com/
# APP_URL = 'https://your-app-name.onrender.com/'  # Замените на ваш URL

TOKEN   = os.environ["TELEGRAM_TOKEN"]
APP_URL = os.environ["RENDER_EXTERNAL_URL"]     # Render выдаёт значение сам
print("URL   = os.environ[RENDER_EXTERNAL_URL]")
print(os.environ["RENDER_EXTERNAL_URL"])
PORT  = int(os.getenv("PORT", 10000))          # Render слушает этот PORT

# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start.
    Отправляет сообщение "Привет!" пользователю.
    """
    await update.message.reply_text("Привет!")

async def handle(request):
    """
    Обработчик GET-запросов к веб-серверу.
    Возвращает простое сообщение "OK".
    Это необходимо для Render, чтобы сервис не отключился.
    """
    return web.Response(text="OK")

async def keep_alive():
    """
    Функция для периодического пинга собственного сервиса.
    Каждые 5 минут делает GET-запрос к APP_URL,
    чтобы поддерживать активность сервиса.
    """
    while True:
        try:
            async with ClientSession() as session:
                # Пингуем свой же URL
                await session.get(APP_URL)
                print(f"Пинг выполнен: {APP_URL}")
        except Exception as e:
            print(f"Ошибка при пинге: {e}")
        # Ждем 300 секунд (5 минут)
        await asyncio.sleep(300)

async def main():
    """
    Основная асинхронная функция.
    Запускает веб-сервер и бота.
    """

    # Создаем веб-приложение для Render
    app = web.Application()
    
    # Добавляем маршрут для GET-запросов по корню "/"
    app.router.add_get('/', handle)

    # Запускаем веб-сервер на порту 8080 (стандартный для Render)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Создаем сайт и запускаем его на всех интерфейсах (0.0.0.0) и порту 8080
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    print("Веб-сервер запущен.")

    # Запускаем задачу периодического пинга в фоне
    asyncio.create_task(keep_alive())

    print("# Запускаем задачу периодического пинга в фоне - ok")
    print("asyncio.create_task(keep_alive()) - ok")

    # Создаем экземпляр бота с помощью ApplicationBuilder
    application = Application.Builder().token(TOKEN).build()

    print("# Создаем экземпляр бота с помощью ApplicationBuilder - ok")
    print("application = ApplicationBuilder().token(TOKEN).build() - ok")

    # Добавляем обработчик команды /start
    application.add_handler(CommandHandler('start', start))

    print("Бот запущен.")
    
    # Запускаем polling — опрос сервера Telegram за событиями
    await application.run_polling()

#if __name__ == '__main__':
#    # Запускаем основную функцию в asyncio-цикле
#    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
