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

# Класс Player — игрок
class Player:
    def __init__(self, name, description, health):
        self.name = name                  # название
        self.description = description    # описание
        self.inventory = []               # инвентарь
        self.health = health              # здоровье
        
# Класс Monster — монстр в локации
class Monster:
    def __init__(self, name, health, attack, defense):
        self.name = name  # имя монстра
        self.health = health  # здоровье монстра
        self.attack = attack              # 
        self.defense = defense            #

    def take_damage(self, damage):
        self.health -= damage

    def is_dead(self):
        return self.health <= 0

# Класс Item — вещи, оружие, броня, ключи
class Item:
    def __init__(self, name, description, type = 'thing', attack = 0, defense = 0, number = 1, picture = '❔'):
        self.name = name                  # название
        self.description = description    # описание
        self.type = type                  # тип: вещь-thing, оружие-weapon, экипировка-equipment, ключи-key, деньги-money 
        self.attack = attack              # 
        self.defense = defense            #
        self.number = number              #
        self.picture = picture   #
        
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
            '⬆️ Север': '⬇️ Юг',
            '⬇️ Юг': '⬆️ Север',
            '➡️ Восток': '⬅️ Запад',
            '⬅️ Запад': '➡️ Восток',
            'Дверь': 'Дверь'
        }
        other_location.connections[opposite_directions[direction]] = self
        
# Класс Game — управляет состоянием игры для каждого пользователя
class Game:
    def __init__(self):
        # Инициализация локаций
        self.locations = {}
        self.player = Player("Хранитель","Из ордена хранителей", 100)
        self.create_world()
         # Начальная локация игрока
        self.current_location = self.locations['Деревня']
        self.current_box = self.player.inventory
        
    def create_world(self):
        # Создаем локации
        village          = Location('Деревня', 'Маленькая уютная деревня.')
        fountain         = Location('Целебный Фонтан', 'Фонтан исцеляющий раны.')
        forest           = Location('Лес', 'Тёмный дремучий лес.')
        castle_entry     = Location('Вход в замок', 'Вы перед древним заброшенным таинственным замком')
        d_castle_hallway = Location('Дверь: замок-прихожая', 'Массивная дубовая дверь', 'door', 'open' )
        hallway          = Location('Прихожая замка', 'Вы вошли в прихожую замка')
        mountain_path    = Location('Горная тропа', 'Тропа в горы.')
        d_hallway_dungeon = Location('Дверь: прихожая-подземелье', 'Массивная дубовая дверь', 'door', 'lock', 'Старый ржавый ключ' )
               
        # Соединяем локации
        # Соединяем по сторонам света
        village.connect(forest, '⬆️ Север')          # на север лес
        village.connect(fountain, '➡️ Восток')       # на востоке фонтан
        forest.connect(mountain_path, '➡️ Восток')  # Горная тропа восточнее леса
        #⬇️ ⬅️
        forest.connect(castle_entry, '⬆️ Север')
        castle_entry.connect(d_castle_hallway, '⬆️ Север')  # Соединение с дверью
        d_castle_hallway.connect(hallway, '⬆️ Север') # Соединение с дверью
        hallway.connect(d_hallway_dungeon, '⬆️ Север') # Соединение с дверью
        
        # Заполняем словарь локаций для доступа по имени
        self.locations['Деревня'] = village
        self.locations['Целебный Фонтан'] = fountain
        self.locations['Лес'] = forest
        self.locations['Горная тропа'] = mountain_path
        self.locations['Вход в замок'] = castle_entry
        self.locations['Дверь: замок-прихожая'] = d_castle_hallway
        self.locations['Прихожая замка'] = hallway
        self.locations['Дверь: прихожая-подземелье'] = d_hallway_dungeon

        #Создаем вещи оружие экипировку ключи
        hunter_knife = Item('Охотничий нож', 'Хороший крепкий нож', 'weapon', 10, 0, 1, '🔪')
        leather_gloves = Item('Кожанные перчатки', 'Старые кожанные перчатки', 'equipment', 0, 5, 1, '🧤')


        #Заполняем инвентарь
        self.player.inventory.append(hunter_knife)
        self.player.inventory.append(leather_gloves)
   
        
    def move_to(self, direction, answer):
        # Перемещение по направлению (если есть)
        if direction in self.current_location.connections:
            if (self.current_location.connections[direction].type == 'door'
                and self.current_location.connections[direction].status == 'open'):                    
                    self.current_location=self.current_location.connections[direction].connections[direction]
                    return True
            elif (self.current_location.connections[direction].type == 'door'
                and self.current_location.connections[direction].status == 'lock'):
                    answer.append('Дверь заперта. Нужен: ' + self.current_location.connections[direction].key)                    
                    return False
            else:
                self.current_location=self.current_location.connections[direction]
                return True
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
        await update.message.reply_text("Пожалуйста, начните игру командой /game.")
        return
            
    if text == '⬆️ Север' or text == '⬇️ Юг' or text == '➡️ Восток' or text == '⬅️ Запад' :
        #direction = context.args[0].lower()
        direction = text
        answer = []
        moved = game.move_to(direction, answer)
        
        if moved:            
            #connections = list(game.current_location.connections.keys())     #Получаем список направлений
            direction = ', '.join(game.current_location.connections.keys())  #Получаем строку список направлений    

            location_desc = game.current_location.description                #Получаем описание текущей локации
            location_desc = location_desc + "\nДоступные направления:\n" 
            for key, value in game.current_location.connections.items():
                #print(f"{key}: {value}")
                location_desc = location_desc + key + " - " + value.name + "\n"

            # Создаем клавиатуру из доступных направлений (выходов)
            connections = list(game.current_location.connections.keys())    
            #keyboard = [[direction] for direction in connections]  # Каждая кнопка — в новой строке    
            keyboard = [[direction for direction in connections]]  # Все кнопки — в одной строке    
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
            await update.message.reply_text(location_desc, reply_markup=reply_markup)
        else:
            await update.message.reply_text("Нельзя пройти в этом направлении.")
            
            #key = game.current_location.connections[direction].key
            #await update.message.reply_text(key)
            await update.message.reply_text(', '.join(answer))

    elif text == '🧳':
        #inventory = list(game.player.inventory)
        #.current_box
        game.current_box = game.player.inventory

        #Разделяем список инвентаря на строки кратные 6
        result = []
        for i in range(0, len(game.current_box), 6):
            sublist_objects = game.current_box[i:i+6]
            sublist_picture = [obj.picture for obj in sublist_objects]
            result.append(sublist_picture)
            
        #keyboard = [[element.picture for element in game.current_box]] # Каждая кнопка — в новой строке   
        keyboard = result
        keyboard.append(['👀'])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
        await update.message.reply_text('🧳', reply_markup=reply_markup)
    
    elif text == '🔪' or text == '🧤':       
        
        if text == '🔪': 
            for item in game.current_box:
                if item.picture == '🔪':
                    found_item = item
                    break
            
            text_message = f"{found_item.picture}. {found_item.name}. {found_item.description}. Урон: {found_item.attack}."
            keyboard = []
            keyboard.append(['🖐','🗑️'])
            keyboard.append(['👀','🧳'])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
            await update.message.reply_text( text_message, reply_markup=reply_markup)
        
    elif text == '👀':
        location = game.current_location                                 #Получаем текущую локацию
        direction = ', '.join(game.current_location.connections.keys())  #Получаем строку список направлений    
    
        location_desc = game.current_location.description                #Получаем описание текущей локации
        location_desc = location_desc + "\nДоступные направления:\n" 
        for key, value in game.current_location.connections.items():
            #print(f"{key}: {value}")
            location_desc = location_desc + key + " - " + value.name + "\n"
                
            #await update.message.reply_text(key + " " + value.name)
    
        # Создаем клавиатуру из доступных направлений (выходов)
        connections = list(game.current_location.connections.keys())     #Получаем список направлений
        keyboard = [[direction for direction in connections]]  # Каждая кнопка — отдельная строка    
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
        await update.message.reply_text(location_desc, reply_markup=reply_markup)
           


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Здравствуйте. Я бот. ")

async def game(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    # Создаем новую игру для пользователя или сбрасываем текущую
    user_games[user_id] = Game()
    game = user_games.get(user_id)
    await update.message.reply_text("Добро пожаловать в текстовую бродилку!\n" +
                                    "Нажмите кнопку действия\n" +
                                    "👀 осмотреться\n" +
                                    "🧳 инвентарь\n" +
                                    "⬆️ идти на север\n" +
                                    "⬇️ идти на юг\n" +
                                    "➡️ идти на восток\n" +
                                    "⬅️ идти на запад" 
                                   )
    #👀 Eyes
    #👁️ Eye #👁#👀 Eyes
    location_desc = game.current_location.description                #Получаем описание текущей локации
    direction = ', '.join(game.current_location.connections.keys())  #Получаем строку список направлений 
    # Создаем клавиатуру из доступных направлений (выходов)
    connections = list(game.current_location.connections.keys())     #Получаем список направлений
    keyboard = [[direction for direction in connections],
               ['👀','🧳']]     
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
    await update.message.reply_text(location_desc, reply_markup=reply_markup)

# Обработчик команды /look — описание текущей комнаты
async def look(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = user_games.get(user_id)
    if not game:
        await update.message.reply_text("Пожалуйста, начните игру командой /game.")
        return
    
    location = game.current_location                                 #Получаем текущую локацию
    direction = ', '.join(game.current_location.connections.keys())  #Получаем строку список направлений    

    location_desc = game.current_location.description                #Получаем описание текущей локации
    location_desc = location_desc + "\nДоступные направления:\n" 
    for key, value in game.current_location.connections.items():
        #print(f"{key}: {value}")
        location_desc = location_desc + key + " - " + value.name + "\n"
            
        #await update.message.reply_text(key + " " + value.name)

    # Создаем клавиатуру из доступных направлений (выходов)
    connections = list(game.current_location.connections.keys())     #Получаем список направлений
    keyboard = [[direction for direction in connections]]  # Каждая кнопка — отдельная строка    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)  
    await update.message.reply_text(location_desc, reply_markup=reply_markup)
    
    # Создаем клавиатуру из доступных направлений (выходов)
    #room_exits = list(game.rooms[game.current_room]['exits'].keys())    
    #keyboard = [[direction] for direction in room_exits]  # Каждая кнопка — отдельная строка    
    #reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)    
    #await update.message.reply_text(description, reply_markup=reply_markup)
    #await update.message.reply_text("room_exits" + room_exits)

    #keyboard = ReplyKeyboardMarkup(keyboard=[
    #            ['Button 1', 'Button 2'],
    #            ['Button 3', 'Button 4']
    #        ])
    #await update.message.reply_text(room_exits, reply_markup=keyboard)
    

    

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
#⛔✅ 🤷🔎 🎒⚠️🤖🛑❓🧭📦⚔️🛡🗡🏆🏷📊👕🧤🧷🚶🔎🖐 👁⬆️⬇️➡️⬅️🔪#💀 ☠️ 💥 🗡️ 🛡️🗑️
#🗡️⚔️🗡⚔🏹🛡️🔪⚜️👑⚜🔰🔱⛏💎🏆☣⛩️✴🔥⚕☠✝🪽🪓🕷💀🌀☯🖌↗🚩💘☝🦅🏮🆕
#👋 Waving Hand
#🤚 Raised Back of Hand
#🖐️ Hand With Fingers Splayed
#✋ Raised Hand
#🖖 Vulcan Salute
#🫱 Rightwards Hand
#🫲 Leftwards Hand
#🫳 Palm Down Hand
#🫴 Palm Up Hand
#👌 OK Hand
#🤌 Pinched Fingers
#🤏 Pinching Hand
#✌️ Victory Hand
#🤞 Crossed Fingers
#🫰 Hand With Index Finger And Thumb Crossed
#🤟 Love-You Gesture
#🤘 Sign of the Horns
#🤙 Call Me Hand
#👈 Backhand Index Pointing Left
#👉 Backhand Index Pointing Right
#👆 Backhand Index Pointing Up
#🖕 Middle Finger
#👇 Backhand Index Pointing Down
#☝️ Index Pointing Up
#🫵 Index Pointing At The Viewer
#👍 Thumbs Up
#👎 Thumbs Down
#✊ Raised Fist
#👊 Oncoming Fist
#🤛 Left-Facing Fist
#🤜 Right-Facing Fist
#👏 Clapping Hands
#🙌 Raising Hands
#🫶 Heart Hands
#👐 Open Hands
#🤲 Palms Up Together
#🤝 Handshake
#🙏 Folded Hands
#✍️ Writing Hand
#💅 Nail Polish
#💪 Flexed Biceps
#🦾 Mechanical Arm
#🦿 Mechanical Leg
#🦵 Leg
#🦶 Foot
#👂 Ear
#🦻 Ear With Hearing Aid
#👃 Nose
#🦷 Tooth
#🦴 Bone
#👀 Eyes
#👁️ Eye
#👅 Tongue
#👄 Mouth
#🫦 Biting Lip
#👶 Baby
#👵 Old Woman
#🤦 Person Facepalming
#🤦‍♂️ Man Facepalming
#🤦‍♀️ Woman Facepalming
#🤷 Person Shrugging
#🤷‍♂️ Man Shrugging
#🤷‍♀️ Woman Shrugging
#👨‍⚕️ ️Man Health Worker
#👩‍⚕️ ️Woman Health Worker
#👨‍🏫 Man Teacher
#🧑‍💻 Technologist
#👨‍💻 Man Technologist
#👩‍💻 Woman Technologist
#👮‍♂️ Man Police Officer
#👮‍♀️ Woman Police Officer
#🤰 Pregnant Woman
#🎅 Santa Claus
#🤶 Mrs. Claus
#🧑‍🎄 Mx Claus
#🧟 Zombie
#🧟‍♂️ Man Zombie
#🧟‍♀️ Woman Zombie
#💃 Woman Dancing
#🕺 Man Dancing
#👨‍👩‍👧‍👦 Family: Man, Woman, Girl, Boy
#🗣️ Speaking Head
#👤 Bust in Silhouette
#👥 Busts in Silhouette
#🫂 People Hugging
#👣 Footprints
#🐼 Animals & Nature
#
#🐵 Monkey Face
#🦍 Gorilla
#🐶 Dog Face
#🦊 Fox
#🦝 Raccoon
#🐱 Cat Face
#🐯 Tiger Face
#🐅 Tiger
#🐆 Leopard
#🐴 Horse Face
#🐎 Horse
#🦄 Unicorn
#🦓 Zebra
#🦌 Deer
#🦬 Bison
#🐂 Ox
#🐄 Cow
#🐷 Pig Face
#🐽 Pig Nose
#🦙 Llama
#🐭 Mouse Face
#🐹 Hamster
#🐰 Rabbit Face
#🐇 Rabbit
#🦇 Bat
#🐻 Bear
#🐻‍❄️ Polar Bear
#🐨 Koala
#🐼 Panda
#🦘 Kangaroo
#🐾 Paw Prints
#🐔 Chicken
#🐣 Hatching Chick
#🐤 Baby Chick
#🐥 Front-Facing Baby Chick
#🐦 Bird
#🐧 Penguin
#🕊️ Dove
#🦆 Duck
#🦢 Swan
#🦉 Owl
#🦜 Parrot
#🐢 Turtle
#🐍 Snake
#🐳 Spouting Whale
#🦭 Seal
#🐟 Fish
#🐠 Tropical Fish
#🐙 Octopus
#🐌 Snail
#🦋 Butterfly
#🪲 Beetle
#🐞 Lady Beetle
#🪳 Cockroach
#🕷️ Spider
#🕸️ Spider Web
#🦟 Mosquito
#🦠 Microbe
#🌸 Cherry Blossom
#🌹 Rose
#🌺 Hibiscus
#🌼 Blossom
#🌷 Tulip
#🌱 Seedling
#🌲 Evergreen Tree
#🌳 Deciduous Tree
#🌴 Palm Tree
#🌵 Cactus
#🌿 Herb
#🍀 Four Leaf Clover
#
#🍕 Food & Drink
#
#🍌 Banana
#🍓 Strawberry
#🥨 Pretzel
#🥞 Pancakes
#🍖 Meat on Bone
#🍗 Poultry Leg
#🍔 Hamburger
#🍟 French Fries
#🍕 Pizza
#🌭 Hot Dog
#🥪 Sandwich
#🌮 Taco
#🥙 Stuffed Flatbread
#🍳 Cooking
#🍿 Popcorn
#🥫 Canned Food
#🍱 Bento Box
#🍘 Rice Cracker
#🍙 Rice Ball
#🍢 Oden
#🍣 Sushi
#🍥 Fish Cake With Swirl
#🍡 Dango
#🦞 Lobster
#🦐 Shrimp
#🍦 Soft Ice Cream
#🍩 Doughnut
#🍪 Cookie
#🎂 Birthday Cake
#🍰 Shortcake
#🧁 Cupcake
#🥧 Pie
#🍫 Chocolate Bar
#🍭 Lollipop
#🍮 Custard
#☕ Hot Beverage
#🍾 Bottle With Popping Cork
#🍷 Wine Glass
#🍸 Cocktail Glass
#🍹 Tropical Drink
#🥂 Clinking Glasses
#🥃 Tumbler Glass
#🫗 Pouring Liquid
#🥤 Cup With Straw
#🧋 Bubble Tea
#🧃 Beverage Box
#🧉 Mate
#🍽️ Fork and Knife With Plate
#
#🌇 Travel & Places
#
#🧭 Compass
#🏕️ Camping
#🏖️ Beach With Umbrella
#🏝️ Desert Island
#🏛️ Classical Building
#🏠 House
#♨️ Hot Springs
#🎢 Roller Coaster
#🚂 Locomotive
#🚑 Ambulance
#🚓 Police Car
#🚕 Taxi
#🚗 Automobile
#🛥️ Motor Boat
#✈️ Airplane
#🚀 Rocket
#🧳 Luggage 
#⌛ Hourglass Done
#⏳ Hourglass Not Done
#🌑 New Moon
#🌒 Waxing Crescent Moon
#🌓 First Quarter Moon
#🌔 Waxing Gibbous Moon
#🌕 Full Moon
#🌖 Waning Gibbous Moon
#🌗 Last Quarter Moon
#🌘 Waning Crescent Moon
#🌚 New Moon Face
#🌛 First Quarter Moon Face
#🌜 Last Quarter Moon Face
#🌡️ Thermometer
#☀️ Sun
#🌝 Full Moon Face
#🌞 Sun With Face
#⭐ Star
#🌟 Glowing Star
#☁️ Cloud
#⛅ Sun Behind Cloud
#⛈️ Cloud With Lightning and Rain
#🌤️ Sun Behind Small Cloud
#🌥️ Sun Behind Large Cloud
#🌦️ Sun Behind Rain Cloud
#🌧️ Cloud With Rain
#🌨️ Cloud With Snow
#🌩️ Cloud With Lightning
#⚡ High Voltage
#❄️ Snowflake
#☃️ Snowman
#⛄ Snowman Without Snow
#🔥 Fire
#
#🎈 Activities
#
#🎃 Jack-O-Lantern
#🎄 Christmas Tree
#🎆 Fireworks
#🎇 Sparkler
#🧨 Firecracker
#✨ Sparkles
#🎈 Balloon
#🎉 Party Popper
#🎊 Confetti Ball
#🎗️ Reminder Ribbon
#🎟️ Admission Tickets
#🎫 Ticket
#🎖️ Military Medal
#🏆 Trophy
#🏅 Sports Medal
#🥇 1st Place Medal
#🥈 2nd Place Medal
#🥉 3rd Place Medal
#⚽ Soccer Ball
#🏀 Basketball
#🛷 Sled
#🔮 Crystal Ball
#🪄 Magic Wand
#🎮 Video Game
#🪩 Mirror Ball
#🎭 Performing Arts
#🎨 Artist Palette
#
#📮 Objects
#
#💣 Bomb
#👛 Purse
#👜 Handbag
#🛍️ Shopping Bags
#👠 High-heeled Shoe
#👑 Crown
#🎩 Top Hat
#🎓 Graduation Cap
#🪖 Military Helmet
#💄 Lipstick
#💎 Gem Stone
#📣 Megaphone
#🎵 Musical Note
#🎶 Musical Notes
#🎙️ Studio Microphone
#🎤 Microphone
#📱 Mobile Phone
#☎️ Telephone
#📞 Telephone Receiver
#💻 Laptop
#🖨️ Printer
#⌨️ Keyboard
#🧮 Abacus
#🎬 Clapper Board
#📺 Television
#🔍 Magnifying Glass Tilted Left
#🔎 Magnifying Glass Tilted Right
#💡 Light Bulb
#📖 Open Book
#📚 Books
#📰 Newspaper
#💰 Money Bag
#🪙 Coin
#💸 Money With Wings
#✉️ Envelope
#📤 Outbox Tray
#📥 Inbox Tray
#📭 Open Mailbox With Lowered Flag
#🗳️ Ballot Box With Ballot
#📝 Memo
#💼 Briefcase
#📁 File Folder
#📂 Open File Folder
#🗂️ Card Index Dividers
#📆 Tear-Off Calendar
#📈 Chart Increasing
#📉 Chart Decreasing
#📊 Bar Chart
#🔐 Locked With Key
#🔑 Key
#🗝️ Old Key
#🧰 Toolbox
#🧪 Test Tube
#🔬 Microscope
#🔭 Telescope
#💉 Syringe
#💊 Pill
#🩺 Stethoscope
#🧻 Roll Of Paper
#🧼 Soap
#🧽 Sponge
#🛒 Shopping Cart
#🗑️ :wastebasket:
#⚰️ Coffin
#🗿 Moai
#
#💯 Symbols
#
#🚹 Men’s Room
#🚺 Women’s Room
#🚼 Baby Symbol
#🛃 Customs
#🔞 No One Under Eighteen
#🔝 TOP Arrow
#♐ Sagittarius
#♑ Capricorn
#♒ Aquarius
#♓ Pisces
#⛎ Ophiuchus
#‼️ Double Exclamation Mark
#⁉️ Exclamation Question Mark
#❓ Question Mark
#❔ White Question Mark
#❕ White Exclamation Mark
#❗ Exclamation Mark
#💱 Currency Exchange
#✅ Check Mark Button
#☑️ Check Box With Check
#✔️ Check Mark
#❌ Cross Mark
#🆒 COOL Button
#🆓 FREE Button
#🆕 NEW Button
#🆗 OK Button
#🆙 UP! Button
#😀 Grinning Face
#😃 Grinning Face With Big Eyes
#😄 Grinning Face With Smiling Eyes
#😁 Beaming Face With Smiling Eyes
#😆 Grinning Squinting Face
#😅 Grinning Face With Sweat
#🤣 Rolling on the Floor Laughing
#😂 Face With Tears of Joy
#🙂 Slightly Smiling Face
#🙃 Upside-Down Face
#🫠 Melting Face
#😉 Winking Face
#😊 Smiling Face With Smiling Eyes
#😇 Smiling Face With Halo
#🥰 Smiling Face With Hearts
#😍 Smiling Face With Heart-Eyes
#🤩 Star-Struck
#😘 Face Blowing a Kiss
#😗 Kissing Face
#☺️ Smiling Face
#😚 Kissing Face With Closed Eyes
#😙 Kissing Face With Smiling Eyes
#🥲 Smiling Face With Tear
#😋 Face Savoring Food
#😛 Face With Tongue
#😜 Winking Face With Tongue
#🤪 Zany Face
#😝 Squinting Face With Tongue
#🤑 Money-Mouth Face
#🤗 Hugging Face
#🤭 Face With Hand Over Mouth
#🫢 Face With Open Eyes And Hand Over Mouth
#🫣 Face With Peeking Eye
#🤫 Shushing Face
#🤔 Thinking Face
#🫡 Saluting Face
#🤐 Zipper-Mouth Face
#🤨 Face With Raised Eyebrow
#😐 Neutral Face
#😑 Expressionless Face
#😶 Face Without Mouth
#🫥 Dotted Line Face
#😶‍🌫️ Face in clouds
#😏 Smirking Face
#😒 Unamused Face
#🙄 Face With Rolling Eyes
#😬 Grimacing Face
#😮‍💨 Face exhaling
#🤥 Lying Face
#😌 Relieved Face
#😔 Pensive Face
#😪 Sleepy Face
#🤤 Drooling Face
#😴 Sleeping Face
#😷 Face With Medical Mask
#🤒 Face With Thermometer
#🤕 Face With Head-Bandage
#🤢 Nauseated Face
#🤮 Face Vomiting
#🤧 Sneezing Face
#🥵 Hot Face
#🥶 Cold Face
#🥴 Woozy Face
#😵 Dizzy Face
#😵‍💫 Face with spiral eyes
#🤯 Exploding Head
#🤠 Cowboy Hat Face
#🥳 Partying Face
#🥸 Disguised Face
#😎 Smiling Face With Sunglasses
#🤓 Nerd Face
#🧐 Face With Monocle
#😕 Confused Face
#🫤 Face With Diagonal Mouth
#😟 Worried Face
#🙁 Slightly Frowning Face
#☹️ Frowning Face
#😮 Face With Open Mouth
#😯 Hushed Face
#😲 Astonished Face
#😳 Flushed Face
#🥺 Pleading Face
#🥹 Face Holding Back Tears
#😦 Frowning Face With Open Mouth
#😧 Anguished Face
#😨 Fearful Face
#😰 Anxious Face With Sweat
#😥 Sad But Relieved Face
#😢 Crying Face
#😭 Loudly Crying Face
#😱 Face Screaming in Fear
#😖 Confounded Face
#😣 Persevering Face
#😞 Disappointed Face
#😓 Downcast Face With Sweat
#😩 Weary Face
#😫 Tired Face
#🥱 Yawning Face
#😤 Face With Steam From Nose
#😡 Pouting Face
#😠 Angry Face
#🤬 Face With Symbols On Mouth
#😈 Smiling Face With Horns
#👿 Angry Face With Horns
#💀 Skull
#☠️ Skull and Crossbones
#💩 Pile of Poo
#🤡 Clown Face
#👹 Ogre
#👺 Goblin
#👻 Ghost
#👽 Alien
#👾 Alien Monster
#🤖 Robot
#😺 Grinning Cat
#😸 Grinning Cat With Smiling Eyes
#😹 Cat With Tears Of Joy
#😻 Smiling Cat With Heart-Eyes
#😼 Cat With Wry Smile
#😽 Kissing Cat
#🙀 Weary Cat
#😿 Crying Cat
#😾 Pouting Cat
#🙈 See-No-Evil Monkey
#🙉 Hear-no-evil Monkey
#🙊 Speak-No-Evil Monkey
#💋 Kiss Mark
#💌 Love Letter
#💘 Heart With Arrow
#💝 Heart With Ribbon
#💖 Sparkling Heart
#💗 Growing Heart
#💓 Beating Heart
#💞 Revolving Hearts
#💕 Two Hearts
#💟 Heart Decoration
#❣️ Heart Exclamation
#💔 Broken Heart
#❤️‍🔥 Heart on fire
#❤️‍🩹 Mending heart
#❤️ Red Heart
#🧡 Orange Heart
#💛 Yellow Heart
#💚 Green Heart
#💙 Blue Heart
#💜 Purple Heart
#🤎 Brown Heart
#🖤 Black Heart
#🤍 White Heart
#💯 Hundred Points
#💢 Anger Symbol
#💥 Collision
#💫 Dizzy
#💬 Speech Balloon
#🗯️ Right Anger Bubble
#💭 Thought Balloon
#💤 Zzz
#🤷 People & Body
# 🧛🏽‍♂️ вампир
# 🧛🏼‍♀️
#🦖
