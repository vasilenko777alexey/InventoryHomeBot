#import telebot
#from os import environ

import os
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler

# Вставьте сюда ваш токен бота от BotFather
#TOKEN = 'ВАШ_ТОКЕН_ЗДЕСЬ'
TOKEN = environ['TELEGRAM_TOKEN']
app = Flask(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# Логирование для отладки
logging.basicConfig(level=logging.INFO)

# Обработчик команды /start
def start(update: Update, context):
    update.message.reply_text('Привет!')

# Регистрируем обработчик команды /start
dispatcher.add_handler(CommandHandler('start', start))

# Фейковый HTTP-сервер для обхода автоотключения Render
@app.route('/', methods=['GET'])
def index():
    return 'Бот запущен!'

# Обработка входящих обновлений через webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    return 'ok'

if __name__ == '__main__':
    # Запускаем сервер на порту 8080 (Render использует этот порт по умолчанию)
    port = int(os.environ.get('PORT', 10000))
	#port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
