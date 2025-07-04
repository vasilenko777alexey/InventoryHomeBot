import telebot
from os import environ

bot = telebot.TeleBot('TELEGRAM_TOKEN')

bot_text = '''
Howdy, how are you doing?
Source code on https://glitch.com/~{}
'''.format(environ['PROJECT_NAME'])

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
	bot.reply_to(message, bot_text)
from time import sleep
sleep(2)
#bot.set_webhook("https://{}.glitch.me/{}".format(environ['PROJECT_NAME'], environ['TELEGRAM_TOKEN']))
