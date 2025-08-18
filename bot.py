#
# -*- coding: utf-8 -*-  # Указываем кодировку исходника

import os  # Работа с переменными окружения
import asyncio  # Асинхронный цикл событий
import logging  # Логирование для отладки
from typing import Optional  # Подсказки типов (необязательно, но полезно)

from aiohttp import web  # Лёгкий асинхронный веб-сервер для health-check
import aiohttp  # HTTP-клиент для самопинга

from telegram import Update  # Тип апдейта Telegram
from telegram.ext import Application, Updater, CommandHandler, ContextTypes  # Ядро PTB v20

# -------------------------- БАЗОВЫЕ НАСТРОЙКИ --------------------------

logging.basicConfig(  # Базовая настройка логов
    level=logging.INFO,  # Уровень логирования
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",  # Формат логов
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()  # Токен бота из переменных окружения
if not TELEGRAM_TOKEN:  # Если токен не задан — останавливаемся с понятной ошибкой
    raise RuntimeError("Переменная окружения TELEGRAM_TOKEN не установлена")  # Сообщаем о проблеме

PORT = int(os.getenv("PORT", "10000"))  # Порт, который выдаёт Render (или дефолт для локального запуска)

# URL для самопинга: приоритетно берем KEEP_ALIVE_URL, затем RENDER_EXTERNAL_URL, затем BASE_URL (на случай других хостингов)
KEEP_ALIVE_URL = (
    os.getenv("KEEP_ALIVE_URL")  # Ручная установка публичного URL сервиса (опционально)
    or os.getenv("RENDER_EXTERNAL_URL")  # Автопеременная Render с публичным URL (доступна на рантайме)
    or os.getenv("BASE_URL")  # Запасной вариант (например, для Railway/Heroku)
)
# Примечание: если ни один из URL не задан, бот будет работать, но самопинг будет пропущен (без падения приложения)

# -------------------------- ОБРАБОТЧИКИ TELEGRAM --------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # Хэндлер /start
    """Отвечает на /start кратким приветствием."""  # Докстринг (для IDE и читаемости)
    if update.message:  # Проверяем, что апдейт содержит текстовое сообщение
        await update.message.reply_text("Привет!")  # Отправляем ответ пользователю

# -------------------------- ФЕЙКОВЫЙ HTTP-СЕРВЕР --------------------------

async def handle_root(request: web.Request) -> web.Response:  # Обработчик GET /
    """Простой корень для теста, логов и внешних проверок."""  # Докстринг
    return web.Response(text="OK")  # Возвращаем 200 ОК

async def handle_health(request: web.Request) -> web.Response:  # Обработчик GET /health
    """Эндпойнт для health-check и самопинга."""  # Докстринг
    return web.Response(text="healthy")  # Возвращаем 200 и короткий текст

async def start_aiohttp_server() -> web.BaseSite:  # Функция запуска aiohttp-сервера
    """Создаёт и запускает aiohttp-сервер на заданном порту."""  # Докстринг
    app = web.Application()  # Создаём приложение aiohttp
    app.add_routes([  # Регистрируем маршруты
        web.get("/", handle_root),  # GET /
        web.get("/health", handle_health),  # GET /health
    ])
    runner = web.AppRunner(app)  # Обёртка для запуска приложения
    await runner.setup()  # Подготовка раннера
    site = web.TCPSite(runner, "0.0.0.0", PORT)  # Создаём TCP-сайт (слушает на всех интерфейсах)
    await site.start()  # Запускаем сайт (не блокирующе)
    logging.info("HTTP server started on port %s", PORT)  # Логируем результат
    return site  # Возвращаем ссылку на сайт (на всякий случай)

# -------------------------- САМОПИНГ (ANTI-SLEEP) --------------------------

async def ping_self(_: ContextTypes.DEFAULT_TYPE) -> None:  # Периодическая задача JobQueue
    """Каждые 10 минут шлёт GET на /health собственного сервиса."""  # Докстринг
    if not KEEP_ALIVE_URL:  # Если публичный URL неизвестен, просто выходим
        logging.warning("KEEP_ALIVE_URL/RENDER_EXTERNAL_URL не задан — пропускаю самопинг")  # Предупреждение
        return  # Прерываем задачу без ошибки
    url = KEEP_ALIVE_URL.rstrip("/") + "/health"  # Формируем конечный URL с /health
    try:  # Безопасный запрос с таймаутом
        async with aiohttp.ClientSession() as session:  # Создаём HTTP-сессию
            async with session.get(url, timeout=10) as resp:  # Делаем GET запрос
                text = await resp.text()  # Читаем текст ответа (для логов)
                logging.info("Self-ping %s -> %s (%s)", url, resp.status, text)  # Логируем результат
    except Exception as e:  # Ловим любые сетевые ошибки
        logging.exception("Ошибка самопинга: %s", e)  # Пишем стек-трейс в логи, но не падаем

# -------------------------- ОСНОВНОЙ ЗАПУСК --------------------------

async def main() -> None:  # Главная асинхронная функция
    # 1) Стартуем HTTP-сервер заранее (Render проверяет порт и ожидает открытый сокет)
    await start_aiohttp_server()  # Поднимаем health-сервер

    # 2) Создаём приложение Telegram-бота (PTB v20+)
    application = Application.builder().token(TELEGRAM_TOKEN).updater(None).write_timeout(30).read_timeout(30).build()  # Строим Application

    # 3) Регистрируем хэндлеры команд
    application.add_handler(CommandHandler("start", start_command))  # Вешаем обработчик для /start

    # 4) Планируем периодический самопинг через JobQueue PTB (каждые 600 секунд)
    application.job_queue.run_repeating(  # Регистрируем задачу повторения
        callback=ping_self,  # Что выполнять
        interval=600,  # Интервал 10 минут (в секундах)
        first=10,  # Первое выполнение через 10 секунд после старта
        name="self_ping",  # Имя задачи (для дебага)
    )

    # 5) Запускаем получение апдейтов через long-polling (проще и бесплатнее, чем webhook)
    #    run_polling сам управляет инициализацией/завершением, поэтому просто await.
    await application.run_polling(  # Запускаем бесконечный цикл получения апдейтов
        allowed_updates=Update.ALL_TYPES,  # Разрешаем все типы апдейтов (на будущее)
        close_loop=False,  # Не закрываем внешний event loop (мы управляем им сами)
    )

if __name__ == "__main__":  # Точка входа при запуске скрипта
    try:  # Защитный блок от неожиданных исключений верхнего уровня
        asyncio.run(main())  # Запускаем главный async-цикл
    except (KeyboardInterrupt, SystemExit):  # Корректная остановка по сигналам
        logging.info("Остановка приложения по сигналу")  # Сообщаем в лог
