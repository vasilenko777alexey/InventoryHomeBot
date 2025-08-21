import os, asyncio, logging, uvicorn, telebot, openpyxl, io, random
from starlette.applications import Starlette
from starlette.responses import Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from telegram import Update, InputFile, InputMediaDocument, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, CommandHandler, CallbackContext, filters, ContextTypes, ApplicationBuilder

import threading
import requests
import time  # Небольшая пауза перед установкой webhook (устойчивее при рестартах)

print('Запуск бота...') 

TOKEN = os.environ["TELEGRAM_TOKEN"]
URL   = os.environ["RENDER_EXTERNAL_URL"]     # Render выдаёт значение сам
BASE_URL = URL
PING_INTERVAL_SECONDS = 600
print("URL   = os.environ[RENDER_EXTERNAL_URL]")
print(os.environ["RENDER_EXTERNAL_URL"])
PORT  = int(os.getenv("PORT", 10000))          # Render слушает этот PORT

log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=log_fmt, level=logging.INFO)

#logging.info(' logging.info Запуск бота...')

# --- классы --------------------------------------------------------------

# Класс Location — место в игре
class Location:
    def __init__(self, name, description, type = 'location', status = None, key = None ):
        self.name = name  # название локации
        self.description = description  # описание локации
        self.connections = {}   # список соседних локаций
        self.monster = None  # монстр в локации (может быть None)
        self.items = []      # предметы в локации
        self.type = type      # тип локации дверь/локация - door/location
        self.status = status #Статус двери, если тип дверь, открыта/закрыта/сломана - open/lock/broken
        self.key = key #Ключ для двери, если тип дверь, строка - Название ключа

    def connect(self, other_location, direction):
        # Создаем двунаправленное соединение по сторонам света
        # direction - строка типа 'Север'/'Юг'/'Восток'/'Запад'
        self.connections[direction] = other_location
        # Обратное направление для другой локации (противоположное)
        opposite_directions = { #словарь соответствий противоположных направлений
            'Север': 'Юг',
            'Юг': 'Север',
            'Восток': 'Запад',
            'Запад': 'Восток',
            'Дверь': 'Дверь'
        }
        other_location.connections[opposite_directions[direction]] = self
        
# Класс Game — управляет состоянием игры для каждого пользователя
class Game:
    def __init__(self):
        # Инициализация локаций
        self.locations = {}
        self.create_world()
         # Начальная локация игрока
        self.current_location = self.locations['Деревня']
        
        # Определяем комнаты (простая карта)
        self.rooms = {
            'entrance': {
                'description': 'Вы на входе в старый заброшенный дом.',
                'exits': {'⬆️ north': 'hall'}
            },
            'hall': {
                'description': 'В большой зале с разбросанными стульями.',
                'exits': {'⬇️ south': 'entrance', '➡️ east': 'kitchen'}
            },
            'kitchen': {
                'description': 'На кухне стоит старый холодильник.',
                'exits': {'⬅️ west': 'hall'}
            }
        }
        self.current_room = 'entrance'  # начальная комната
        
    def create_world(self):
        # Создаем локации
        village         = Location('Деревня', 'Маленькая уютная деревня.')
        forest          = Location('Лес', 'Тёмный дремучий лес.')
        castle          = Location('Замок', 'Древний заброшенный таинственный замок')
        d_castle_hallway  = Location('Дверь в замок', 'Массивная дубовая дверь', 'door', 'open' )
        hallway         = Location('Прихожая замка', 'Вы вошли в прихожую замка')
        mountain_path   = Location('Горная тропа', 'Тропа в горы.')
               
        # Соединяем локации
        # Соединяем по сторонам света
        village.connect(forest, 'Север')          # Лес южнее деревни
        forest.connect(mountain_path, 'Восток')  # Горная тропа восточнее леса
        forest.connect(castle, 'Север')
        castle.connect(d_castle_hallway, 'Дверь')  # Соединение с дверью
        d_castle_hallway.connect(hallway, 'Дверь') # Соединение с дверью
        
        # Заполняем словарь локаций для доступа по имени
        self.locations['Деревня'] = village
        self.locations['Лес'] = forest
        self.locations['Горная тропа'] = mountain_path
        self.locations['Замок'] = castle
        self.locations['Дверь в замок'] = d_castle_hallway
        self.locations['Прихожая замка'] = hallway
        
    def move_to(self, direction):
        # Перемещение по направлению (если есть)
        if direction in self.current_location.connections:
            self.current_location=self.current_location.connections[direction]
            return True
        return False

    def get_description(self):
        room = self.rooms[self.current_room]
        desc = room['description']
        exits = ', '.join(room['exits'].keys())
        return f"{desc}\nДоступные направления: {exits}"

    def move(self, direction):
        room = self.rooms[self.current_room]
        if direction in room['exits']:
            self.current_room = room['exits'][direction]
            return True
        else:
            return False

# Хранение игр для каждого пользователя
user_games = {}


# --- хендлеры --------------------------------------------------------------

async def echo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    #await update.message.reply_text(update.message.text + " , id message: "+ str(update.message.id) + " " + str(update.message.reply_to_message.message_id) + " " + str(update.message.reply_to_message))
    await update.message.reply_text(update.message.text )
async def def_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text    
    
    if text == 'test':
        await update.message.reply_text(update.message.text + " , id message: "+ str(update.message.id) + " " + str(update.message.reply_to_message.message_id) + " " + str(update.message.reply_to_message))
        return

    user_id = update.effective_user.id
    game = user_games.get(user_id)
    if not game:
        await update.message.reply_text("Пожалуйста, начните игру командой /start.")
        return
        
    if text == '⬆️ north' or text == '⬇️ south' or text == '➡️ east' or text == '⬅️ west' :
        #direction = context.args[0].lower()
        direction = text
        moved = game.move(direction)
        
        if moved:
            description = game.get_description()
            #await update.message.reply_text(description)
            
            # Создаем клавиатуру из доступных направлений (выходов)
            room_exits = list(game.rooms[game.current_room]['exits'].keys())  
            #keyboard = [[direction] for direction in room_exits]  # Каждая кнопка — отдельная строка 
            keyboard = [[direction for direction in room_exits],
                       ['🖐 Взять', '👁 Смот','🎒 Инв', '🚪 Открыть']]   
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)    
            await update.message.reply_text(description, reply_markup=reply_markup)
        else:
            await update.message.reply_text("Нельзя пройти в этом направлении.")
#⛔✅ 🤷🔎 🎒⚠️🤖🛑❓🧭📦

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Здравствуйте. Я бот. ")

async def game(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    # Создаем новую игру для пользователя или сбрасываем текущую
    user_games[user_id] = Game()
    await update.message.reply_text("Добро пожаловать в текстовую бродилку!\n" +
                                    "Используйте команды /look.")
    
# Обработчик команды /look — описание текущей комнаты
async def look(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = user_games.get(user_id)
    if not game:
        await update.message.reply_text("Пожалуйста, начните игру командой /game.")
        return
        
    description = game.get_description()
    location = game.current_location
    location_desc = game.current_location.description
    #await update.message.reply_text(location)
    await update.message.reply_text(location_desc)
    connections = list(game.current_location.connections.keys())
    await update.message.reply_text(connections)
    connections = ', '.join(game.current_location.connections.keys())
    
    await update.message.reply_text(connections)
    
    # Создаем клавиатуру из доступных направлений (выходов)
    room_exits = list(game.rooms[game.current_room]['exits'].keys())    
    keyboard = [[direction] for direction in room_exits]  # Каждая кнопка — отдельная строка    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)    
    await update.message.reply_text(description, reply_markup=reply_markup)

    #keyboard = ReplyKeyboardMarkup(keyboard=[
    #            ['Button 1', 'Button 2'],
    #            ['Button 3', 'Button 4']
    #        ])
    #await update.message.reply_text(room_exits, reply_markup=keyboard)
    
    

# Обработчик команды /go <направление>
async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = user_games.get(user_id)
    if not game:
        await update.message.reply_text("Пожалуйста, начните игру командой /start.")
        return
    
    if len(context.args) == 0:
        await update.message.reply_text("Укажите направление. Например: /go north")
        return
    
    direction = context.args[0].lower()
    moved = game.move(direction)
    
    if moved:
        description = game.get_description()
        await update.message.reply_text(description)
    else:
        await update.message.reply_text("Нельзя пройти в этом направлении.")

    

async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Начало обработки excel файла")
    
    chat_id = update.effective_chat.id

    # Ищем в старых сообщениях файла Excel
    # Получим последние 50 сообщений (можно больше или меньше)

    message_id = 9
   
    message_to_copy = await context.bot.forward_message(chat_id, chat_id, message_id)
    if message_to_copy.text:
        await update.message.reply_text(text=message_to_copy.text)
    
    await update.message.reply_text("Этап 1 обработки excel файла")

    if message_to_copy.document:
    #if message_to_copy.text:
        await context.bot.send_document(chat_id=chat_id, document=message_to_copy.document.file_id)
        text="Документ id: " + str(message_to_copy.document.file_id)
        await context.bot.send_message(chat_id=chat_id, text=text)
        file = await message_to_copy.document.get_file()
        TEMP_FILE_PATH = 'temp_excel.xlsx'
        await file.download_to_drive(TEMP_FILE_PATH)

         # Открываем Excel и меняем ячейки A1 -> A2
        wb = openpyxl.load_workbook(TEMP_FILE_PATH)
        ws = wb.active

        cell_a1_value = ws['A1'].value
        ws['A2'].value = cell_a1_value

        # Сохраняем изменения в тот же файл
        wb.save(TEMP_FILE_PATH)

        # Создаём InputFile для нового файла
        #new_file = InputFile(open(TEMP_FILE_PATH, 'rb'))
        
        await update.message.reply_text("Этап 2 обработки excel файла")
        await update.message.reply_text(TEMP_FILE_PATH)
        # Открываем файл для передачи в InputMediaDocument
        #with open(TEMP_FILE_PATH, 'rb') as f:
        #    new_file = InputFile(f)

            # Заменяем сообщение с файлом
        #   await context.bot.edit_message_media(
        #       chat_id=chat_id,
        #       message_id=message_id,
        #       media=InputMediaDocument(media=new_file)
        #   )
            
        with open(TEMP_FILE_PATH, "rb") as file:  
            media = InputMediaDocument(file)  
            message_id_2 = 351
            await context.bot.edit_message_media(chat_id=chat_id, message_id=message_id_2, media=media)  

        await update.message.reply_text("Файл успешно обновлён.")


        
        # Отправляем сообщение с содержимым A1
        await update.message.reply_text(f"Значение ячейки A1: {cell_a1_value}")

        # Отправляем обновлённый файл  
        #await context.bot.send_document(
        #    chat_id=chat_id,
        #    document=new_file,
        #    filename='обновленный_файл.xlsx'
        #)
        await update.message.reply_text("Этап 3 обработки excel файла")
        
        #await context.bot.edit_message_media(
        #        chat_id=chat_id,
        #        message_id=message_id,
        #        media=InputMediaDocument(media=new_file)
        #    )
        await update.message.reply_text("Конец обработки excel файла")
            
      

'''
    excel_file_bytes = None
'''
#-------------------------------------------------------------------

async def main():
    app = Application.builder().token(TOKEN).updater(None).write_timeout(30).read_timeout(30).build()
    
    #app.add_handler(MessageHandler(filters.ALL, echo)) # Обработчик всех текстовых сообщений, кроме команд
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & (~filters.REPLY), echo)) # Обработчик всех текстовых сообщений, кроме команд
    app.add_handler(MessageHandler(filters.REPLY & (~filters.COMMAND), def_reply)) # Обработчик всех текстовых сообщений, кроме команд
    
    #app.add_handler(MessageHandler(def_text, content_types=['text']))
    app.add_handler(CommandHandler('start', start)) 
    app.add_handler(CommandHandler('game', game)) 
    app.add_handler(CommandHandler('look', look))
    app.add_handler(CommandHandler('go', go))
    app.add_handler(CommandHandler('excel', excel)) 
    await app.bot.set_webhook(f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)
    print("await app.bot.set_webhook(f{URL}/telegram, allowed_updates=Update.ALL_TYPES)")
    print(f"{URL}/telegram")

    async def telegram(request: Request) -> Response:
        await app.update_queue.put(Update.de_json(await request.json(), app.bot))
        return Response()

    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    starlette = Starlette(routes=[
        Route("/telegram", telegram, methods=["POST"]),
        Route("/healthcheck", health, methods=["GET"]),
#        Route("/health", health, methods=["GET"]),
    ])

    server = uvicorn.Server(
        uvicorn.Config(app=starlette, host="0.0.0.0", port=PORT, use_colors=False)
    )
    async with app:
        await app.start()
        await server.serve()
        await app.stop()

#-------------------------------------------------------------------
        
def self_ping_loop():
    """
    Периодически пингует /health через внешний URL.
    Это создаёт входящий HTTP-трафик и предотвращает автоусыпление на Free плане.
    Примечание: у Render Free Web Services засыпают после ~15 минут без входящего трафика.
    """
    if not BASE_URL:
        print("BASE_URL не задан; самопинг отключён (не знаем, куда стучаться).")
        #app.logger.warning(
        #    "BASE_URL не задан; самопинг отключён (не знаем, куда стучаться)."
        #)
        return

#    ping_url = f"{BASE_URL}/health" #/healthcheck
    ping_url = f"{BASE_URL}/healthcheck" 
    print("Самопинг включён, URL: %s, интервал: %s сек", ping_url, PING_INTERVAL_SECONDS)
    #app.logger.info("Самопинг включён, URL: %s, интервал: %s сек", ping_url, PING_INTERVAL_SECONDS)
    while True:
        try:
            requests.get(ping_url, timeout=10)
        except Exception as e:
            print("Ошибка самопинга: %s", e)
            #app.logger.warning("Ошибка самопинга: %s", e)
        time.sleep(PING_INTERVAL_SECONDS)


# Старт фоновых потоков при импортировании модуля (когда процесс поднимается gunicorn-ом)
#threading.Thread(target=ensure_webhook, daemon=True).start()
#if SELF_PING_ENABLED:
threading.Thread(target=self_ping_loop, daemon=True).start()

if __name__ == "__main__":
    asyncio.run(main())
