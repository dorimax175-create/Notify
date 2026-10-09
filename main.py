
import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_IDS = {
    int(item.strip())
    for item in os.environ.get("OWNER_IDS", "").split(",")
    if item.strip()
}
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_MESSAGE = (
    "Hello! We received your request to join our private channel. "
    "Your request may be reviewed by the channel administrators. "
    "Thank you for your interest."
)


def load_message() -> str:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        message = data.get("join_message")
        if isinstance(message, str) and message.strip():
            return message
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read saved configuration: %s", exc)
    return DEFAULT_MESSAGE


def save_message(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CONFIG_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps({"join_message": message}, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_file.replace(CONFIG_FILE)


async def start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_message or not update.effective_user:
        return

    if update.effective_user.id in OWNER_IDS:
        await update.effective_message.reply_text(
            "Bot is running.\n\n"
            "/message - View the current join message\n"
            "/setmessage YOUR MESSAGE - Update the message"
        )
    else:
        await update.effective_message.reply_text(
            "This bot sends information related to channel join requests."
        )


async def show_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or update.effective_user.id not in OWNER_IDS:
        if update.effective_message:
            await update.effective_message.reply_text("Not authorized.")
        return

    await update.effective_message.reply_text(
        f"Current join message:\n\n{load_message()}"
    )


async def set_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or update.effective_user.id not in OWNER_IDS:
        if update.effective_message:
            await update.effective_message.reply_text("Not authorized.")
        return

    message = update.effective_message.text.partition(" ")[2].strip()

    if not message:
        await update.effective_message.reply_text(
            "Usage:\n/setmessage Your new message goes here"
        )
        return

    if len(message) > 4000:
        await update.effective_message.reply_text(
            "The message is too long. Please keep it under 4,000 characters."
        )
        return

    try:
        save_message(message)
    except OSError:
        logger.exception("Unable to save the join message")
        await update.effective_message.reply_text(
            "Could not save the message. Check the Railway volume and logs."
        )
        return

    await update.effective_message.reply_text(
        "Join message updated and saved."
    )


async def handle_join_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    request = update.chat_join_request
    if request is None:
        return

    try:
        await context.bot.send_message(
            chat_id=request.user_chat_id,
            text=load_message(),
        )
        logger.info(
            "Sent join-request message for channel ID %s",
            request.chat.id,
        )
    except TelegramError as exc:
        # Do not expose the requester's private information in logs.
        logger.warning(
            "Could not deliver a join-request message: %s",
            type(exc).__name__,
        )


async def on_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    error = context.error
    logger.error(
        "Unhandled bot error: %s",
        type(error).__name__ if error else "UnknownError",
    )


def main() -> None:
    if not OWNER_IDS:
        raise RuntimeError(
            "Set OWNER_IDS to your Telegram numeric user ID."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("message", show_message))
    app.add_handler(CommandHandler("setmessage", set_message))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_error_handler(on_error)

    logger.info("Bot starting with long polling")
    app.run_polling(
        allowed_updates=["message", "chat_join_request"],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
