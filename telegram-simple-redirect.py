from argparse import ArgumentParser, Namespace
import json
from typing import Any, Dict, List, Tuple, TypeAlias
from dataclasses import dataclass, asdict
from flask import Flask, request
import asyncio
from multiprocessing import Process
from telegram import Update, File
from telegram.ext import (
    ContextTypes,
    ApplicationBuilder,
    MessageHandler,
    filters,
)
import requests

DEFAULT_PORT = 6060


@dataclass(frozen=True, init=True, kw_only=True)
class ParsedMessage:
    user_id: int
    message_id: int
    chat_id: int
    fullname: str
    username: str
    is_bot: bool
    message: str
    caption: str
    formatted_message: str
    images: Tuple[Dict[str, Any]]
    video: Dict[str, Any]
    iso_datetime: str
    posix_secs_timestamp: float


def parse_argv() -> Dict[str, str]:
    """Set command line arguments and parses them."""
    parser = ArgumentParser()
    default_options = {
        "type": str,
        "default": None,
    }

    parser.add_argument(
        "--send-to",
        **default_options,
        required=True,
        help="HTTP endpoint to which send the redirected messages",
    )

    parser.add_argument(
        "--token",
        **default_options,
        required=True,
        help="Telegram app API token",
    )

    parser.add_argument(
        "--host",
        **default_options,
        required=False,
        help="HTTP URL of recipient server",
    )

    parser.add_argument(
        "--port",
        **default_options,
        required=False,
        help="HTTP server port related to specified HOST"
    )

    args: Namespace = parser.parse_args()

    return vars(args)

args = parse_argv()

def listen() -> None:
    """Create HTTP server and listen on localhost."""

    app = Flask(__name__)

    @app.route("/", methods=["POST"])
    async def pong() -> Tuple[str, int]:
        """Prints body of received request to stdout."""
        if request.method != "POST":
            return "", 406  # unauthorized

        try:
            print(json.dumps(request.get_data(as_text=True)))
        except json.JSONDecodeError:
            print(request.get_data(as_text=True))
        finally:
            return "", 200  # ok

    global args
    host: str = args["host"] or "localhost"
    port: int

    try:
        port = int(args["port"])
    except ValueError:
        port = DEFAULT_PORT

    asyncio.run(app.run(host=host, port=port))


def remove_file_duplicates(files: Tuple[File]) -> List[File]:
    if not len(files):
        return []
    ordered = sorted(files, key=lambda file: file.file_size)
    offset = int(len(ordered) / 5)
    correct = list(ordered)
    correct.reverse()

    return correct[:offset]


def bot() -> None:
    """Sends message to local http server."""
    global args
    sendto: str = args["send_to"]
    token: str = args["token"]

    if not sendto:
        raise ValueError("Invalid endpoint string")

    if not token:
        raise ValueError("Invalid token string")

    async def redirect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        photo = remove_file_duplicates(update.message.photo)
        video = update.message.video

        data = ParsedMessage(
            message=update.message.text or "",
            caption=update.message.caption or "",
            formatted_message=update.message.text_markdown_v2_urled or "",
            user_id=update.message.from_user.id,
            message_id=update.message.id,
            chat_id=update.message.chat_id,
            fullname=update.message.from_user.full_name,
            username=update.message.from_user.username or "",
            is_bot=update.message.from_user.is_bot,
            images=[p.to_dict() for p in photo],
            video=video.to_dict() if video else {},
            iso_datetime=update.message.date.isoformat(),
            posix_secs_timestamp=update.message.date.timestamp(),
        )

        response = requests.post(sendto, json=asdict(data))

        if response.status_code != 200:
            return

        prittified = json.dumps(asdict(data), indent=2)
        await update.message.reply_markdown(f"```json\n{prittified}\n```")

        if len(photo):
            for p in photo:
                await update.message.chat.send_photo(p)

        if video:
            await update.message.chat.send_video(video)

    application = ApplicationBuilder().token(token).build()

    handlers = [
        MessageHandler(
            filters.ALL,
            redirect,
        )
    ]

    for h in handlers:
        application.add_handler(h)

    application.run_polling()


if __name__ == "__main__":
    server_proc = Process(target=listen, name="Server")
    bot_proc = Process(target=bot, name="Bot")

    server_proc.start()
    bot_proc.start()

    bot_proc.join()
    server_proc.join()
