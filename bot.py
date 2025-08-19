import os, asyncio, logging, uvicorn, telebot, openpyxl, io
from starlette.applications import Starlette
from starlette.responses import Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from telegram import Update, InputFile, InputMediaDocument
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, CommandHandler, CallbackContext, filters, ContextTypes, ApplicationBuilder

import threading
import requests

print('Запуск бота...') 

TOKEN = os.environ["TELEGRAM_TOKEN"]
URL   = os.environ["RENDER_EXTERNAL_URL"]     # Render выдаёт значение сам
print("URL   = os.environ[RENDER_EXTERNAL_URL]")
print(os.environ["RENDER_EXTERNAL_URL"])
PORT  = int(os.getenv("PORT", 10000))          # Render слушает этот PORT

log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=log_fmt, level=logging.INFO)

# --- хендлеры --------------------------------------------------------------

async def echo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    #await update.message.reply_text(update.message.text + " , id message: "+ str(update.message.id) + " " + str(update.message.reply_to_message.message_id) + " " + str(update.message.reply_to_message))
    await update.message.reply_text(update.message.text )
async def def_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text + " , id message: "+ str(update.message.id) + " " + str(update.message.reply_to_message.message_id) + " " + str(update.message.reply_to_message))
    
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Здравствуйте. Я бот. ")

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

#    ping_url = f"{BASE_URL}/health" #/healthcheck
    ping_url = f"{BASE_URL}/healthcheck" 
    app.logger.info("Самопинг включён, URL: %s, интервал: %s сек", ping_url, PING_INTERVAL_SECONDS)
    while True:
        try:
            requests.get(ping_url, timeout=10)
        except Exception as e:
            app.logger.warning("Ошибка самопинга: %s", e)
        time.sleep(PING_INTERVAL_SECONDS)


# Старт фоновых потоков при импортировании модуля (когда процесс поднимается gunicorn-ом)
#threading.Thread(target=ensure_webhook, daemon=True).start()
#if SELF_PING_ENABLED:
threading.Thread(target=self_ping_loop, daemon=True).start()

if __name__ == "__main__":
    asyncio.run(main())
