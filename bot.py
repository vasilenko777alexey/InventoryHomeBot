"""
Простой Telegram-бот для Render (Free plan) + webhook через Flask
- /start -> "Привет!"
- /health -> текст "OK" (для проверок/healthcheck)
- / -> "OK"
- /webhook/<секрет> -> приём апдейтов от Telegram

Особенности:
- Автопостановка webhook на внешний URL сервиса (RENDER_EXTERNAL_URL).
- Фоновый поток самопинга внешнего URL, чтобы не дать сервису уснуть.
- Проверка секретного заголовка Telegram (X-Telegram-Bot-Api-Secret-Token).
"""
import logging
import os
import time
import threading
import requests
from flask import Flask, request, abort
import telebot  # библиотека pyTelegramBotAPI

print('Запуск бота...') 

# ---------------------------------------------------------------------
# Конфигурация из переменных окружения
# ---------------------------------------------------------------------
#TELEGRAM_TOKEN
#TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    # Чтобы не получить тихую ошибку: без токена боту работать нельзя.
    raise RuntimeError("Не задан TELEGRAM_TOKEN")

# Секрет для пути вебхука и для проверки заголовка X-Telegram-Bot-Api-Secret-Token
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-secret-change-me")

# На Render внешний URL доступен в RENDER_EXTERNAL_URL (например, https://<name>.onrender.com)
# Локально можно задать EXTERNAL_URL вручную (например, через ngrok).
BASE_URL = (
    os.environ.get("EXTERNAL_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")  # Render сам подставит это значение
)

# Как часто пинговать себя (сек)
PING_INTERVAL_SECONDS = int(os.environ.get("PING_INTERVAL_SECONDS", "600"))
# Включение/выключение самопинга
SELF_PING_ENABLED = os.environ.get("SELF_PING", "1") == "1"

log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=log_fmt, level=logging.INFO)

# ---------------------------------------------------------------------
# Инициализация Flask и бота
# ---------------------------------------------------------------------

print('Инициализация Flask и бота') 
app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode=None)  # без Markdown — нам не нужен
app.logger.setLevel(logging.INFO)
print('Завершение. Инициализация Flask и бота') 

# ---------------------------------------------------------------------
# Хэндлеры Telegram
# ---------------------------------------------------------------------

@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message) -> None:
    """Ответ на /start: одно слово "Привет!"."""
    bot.send_message(message.chat.id, "Привет!")

@bot.message_handler(commands=["save"])
def handle_save(message: telebot.types.Message) -> None:
    """Ответ на /start: одно слово "Привет!"."""
    app.logger.info("перед удалением ")
    message_save = bot.send_message(message.chat.id, "Привет!")    
    bot.delete_message(message.chat.id, message_save.message_id)
    bot.send_message(message.chat.id, message_save.message_id) 
    print("Удалили сообщение message_id:" )
    print( str(message_save.message_id) )
    app.logger.info("Удалили сообщение message_id: %s", message_save.message_id)
    for i in range(1, message_save.message_id):  
        i += 1  
        if i >= 570:
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=i, text='EditText')
                app.logger.info("Изменили сообщение: %s", i)
                return "Изменили сообщение" , 200
            except Exception as e:
                app.logger.exception("Ошибка при изменении сообщения: %s", e)
                app.logger.exception("Ошибка при изменении сообщения: %s", i)           
    message_doc= bot.forward_message(chat_id=message.chat.id, from_chat_id=message.chat.id, message_id=9)  
    bot.delete_message(message.chat.id, message_doc.message_id)
    if 'document' in message_doc:
        document = message_doc['document']
        filename = document.get('file_name', '')
        if filename == 'test.xlsx':
            bot.send_message(message.chat.id, "Документ есть!")
            


                




# ---------------------------------------------------------------------
# HTTP-маршруты
# ---------------------------------------------------------------------

@app.get("/")
def root_ok():
    """Быстрая проверка корня сервиса."""
    return "OK"

@app.get("/health")
def health():
    """Health-check эндпойнт. Удобно для мониторинга и самопинга."""
    return "OK"

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def telegram_webhook():
    """
    Основной webhook-эндпойнт.
    Telegram присылает сюда Update-ы методом POST с JSON в теле запроса.
    """
    # (Опционально) Проверяем секретный заголовок, который Telegram добавляет,
    # если мы передали secret_token при setWebhook.
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header and secret_header != WEBHOOK_SECRET:
        # Если заголовок присутствует, но не совпал — отклоняем запрос.
        abort(403)

    # Забираем JSON и передаём во внутреннюю обработку pyTelegramBotAPI
    try:
        json_update = request.get_json(force=True, silent=False)
        if not json_update:
            return "empty json", 400
        update = telebot.types.Update.de_json(json_update)
        bot.process_new_updates([update])
    except Exception as e:
        app.logger.exception("Ошибка при обработке апдейта: %s", e)
        return "bad update", 500

    # Важно отвечать быстро (200 OK), иначе Telegram может считать webhook медленным.
    return "OK", 200


# ---------------------------------------------------------------------
# Фоновая логика: автопостановка webhook и самопинг
# ---------------------------------------------------------------------

def ensure_webhook():
    """
    Ставит webhook на внешний URL сервиса.
    Работает и при рестарте; Telegram просто перезапишет URL.
    """
    if not BASE_URL:
        app.logger.warning(
            "BASE_URL не задан (нет EXTERNAL_URL/RENDER_EXTERNAL_URL). "
            "Webhook не будет установлен автоматически."
        )
        return

    webhook_url = f"{BASE_URL}/webhook/{WEBHOOK_SECRET}"
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"

    # Параметры:
    # - url: куда слать апдейты
    # - secret_token: Telegram будет присылать его в заголовке X-Telegram-Bot-Api-Secret-Token
    # - drop_pending_updates: чтобы не получать «старые» апдейты после перезапуска
    params = {
        "url": webhook_url,
        "secret_token": WEBHOOK_SECRET,
        "drop_pending_updates": True,
        # Можно добавить ограничение типов или max_connections по желанию
    }
    try:
        r = requests.get(api_url, params=params, timeout=10)
        app.logger.info("setWebhook -> %s %s", r.status_code, r.text)
    except Exception as e:
        app.logger.error("Не удалось вызвать setWebhook: %s", e)


def self_ping_loop():
    """
    Периодически пингует /health через внешний URL.
    Это создаёт входящий HTTP-трафик и предотвращает автоусыпление на Free плане.
    Примечание: у Render Free Web Services засыпают после ~15 минут без входящего трафика.
    """
    if not BASE_URL:
        app.logger.warning(
            "BASE_URL не задан; самопинг отключён (не знаем, куда стучаться)."
        )
        return

    ping_url = f"{BASE_URL}/health"
    app.logger.info("Самопинг включён, URL: %s, интервал: %s сек", ping_url, PING_INTERVAL_SECONDS)
    while True:
        try:
            requests.get(ping_url, timeout=10)
        except Exception as e:
            app.logger.warning("Ошибка самопинга: %s", e)
        time.sleep(PING_INTERVAL_SECONDS)


# Старт фоновых потоков при импортировании модуля (когда процесс поднимается gunicorn-ом)
threading.Thread(target=ensure_webhook, daemon=True).start()
if SELF_PING_ENABLED:
    threading.Thread(target=self_ping_loop, daemon=True).start()


# Локальный запуск (для отладки)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    # host=0.0.0.0 важен на Render; локально тоже не мешает.
    app.run(host="0.0.0.0", port=port)
