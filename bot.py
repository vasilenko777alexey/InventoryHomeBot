import os, asyncio, logging, uvicorn, telebot, openpyxl, io
from starlette.applications import Starlette
from starlette.responses import Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from telegram import Update, InputFile, InputMediaDocument
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, CommandHandler, CallbackContext, filters, ContextTypes, ApplicationBuilder

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
    await update.message.reply_text(update.message.text + " , id message: "+ str(update.message.id) + " " + str(update.message.reply_to_message.id))
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Здравствуйте. Я бот. ")

async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Начало обработки excel файла")
    
    chat_id = update.effective_chat.id

    # Ищем в старых сообщениях файла Excel
    # Получим последние 50 сообщений (можно больше или меньше)
    #app
    #messages = await context.bot.get_updates(limit=100)

    message_id = 9
    #msg_copy = context.bot.forward_message(chat_id, chat_id, message_id)
    
    message_to_copy = await context.bot.forward_message(chat_id, chat_id, message_id)
    if message_to_copy.text:
        await update.message.reply_text(text=message_to_copy.text)
    
    await update.message.reply_text("Этап 1 обработки excel файла")

    if message_to_copy.document:
        await context.bot.send_document(chat_id=chat_id, document=message_to_copy.document.file_id)
        text="Документ id: " + str(message_to_copy.document.file_id)
        await context.bot.send_message(chat_id=chat_id, text=text)
        file = await message_to_copy.document.get_file()
        excel_file_bytes = await file.download_as_bytearray()

        # Открываем файл из байтов
        with io.BytesIO(excel_file_bytes) as bio:
            wb = openpyxl.load_workbook(bio)
            sheet = wb.active  # или wb['Имя листа']
    
            # Читаем A1
            a1_value = sheet['A1'].value
    
            # Копируем в A2
            sheet['A2'].value = a1_value
    
            # Сохраняем обратно в байты
            with io.BytesIO() as output:
                wb.save(output)
                output.seek(0)
                new_excel_bytes = output.read()

        new_file = InputFile(open(new_excel_bytes, 'rb'))
    
        await update.message.reply_text("Этап 2 обработки excel файла")
        # Отправляем сообщение с содержимым A1
        await update.message.reply_text(f"Значение ячейки A1: {a1_value}")

        # Отправляем обновлённый файл  
        await context.bot.send_document(
            chat_id=chat_id,
            document=new_file,
            filename='обновленный_файл.xlsx'
        )
        await update.message.reply_text("Конец обработки excel файла")

        await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=InputMediaDocument(media=document)
            )
            
      

'''
    excel_file_bytes = None

    for msg in messages:
        if msg.document:
            filename = msg.document.file_name.lower()
            if filename.endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
                file = await msg.document.get_file()
                excel_file_bytes = await file.download_as_bytearray()
                break
    await update.message.reply_text("Этап 2 обработки excel файла")

    if not excel_file_bytes:
        await update.message.reply_text("В недавних сообщениях не найден файл Excel.")
        return

    await update.message.reply_text("Этап 3 обработки excel файла")

    # Открываем файл из байтов
    with io.BytesIO(excel_file_bytes) as bio:
        wb = openpyxl.load_workbook(bio)
        sheet = wb.active  # или wb['Имя листа']

        # Читаем A1
        a1_value = sheet['A1'].value

        # Копируем в A2
        sheet['A2'].value = a1_value

        # Сохраняем обратно в байты
        with io.BytesIO() as output:
            wb.save(output)
            output.seek(0)
            new_excel_bytes = output.read()

    await update.message.reply_text("Этап 4 обработки excel файла")

    # Отправляем сообщение с содержимым A1
    await update.message.reply_text(f"Значение ячейки A1: {a1_value}")

    # Отправляем обновлённый файл
    await context.bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(new_excel_bytes),
        filename='обновленный_файл.xlsx'
    )
    await update.message.reply_text("Конец обработки excel файла")
'''
#-------------------------------------------------------------------

async def main():
    app = Application.builder().token(TOKEN).updater(None).write_timeout(30).read_timeout(30).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
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
    ])

    server = uvicorn.Server(
        uvicorn.Config(app=starlette, host="0.0.0.0", port=PORT, use_colors=False)
    )
    async with app:
        await app.start()
        await server.serve()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
