import os, asyncio, logging, uvicorn, telebot
from starlette.applications import Starlette
from starlette.responses import Response, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, Updater, CommandHandler, CallbackContext, filters

TOKEN = os.environ["TELEGRAM_TOKEN"]
URL   = os.environ["RENDER_EXTERNAL_URL"]     # Render выдаёт значение сам
PORT  = int(os.getenv("PORT", 10000))          # Render слушает этот PORT

log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=log_fmt, level=logging.INFO)

async def echo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)
#---------------------
my_queue = asyncio.Queue()
#queue = asyncio.Queue()

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Здорова, брат! Я бот. Как сам?")

updater = Updater(os.environ["TELEGRAM_TOKEN"], update_queue=my_queue)
dp = updater.dispatcher
dp.add_handler(CommandHandler('start', start))

updater.start_polling()
updater.idle()
#---------------------

# Обработчик команды /start
#def start(update: Update, context):
#    update.message.reply_text('Привет!')


# Регистрируем обработчик команды /start
#dispatcher.add_handler(CommandHandler('start', start))

async def main():
    app = Application.builder().token(TOKEN).updater(None).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    await app.bot.set_webhook(f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)

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
