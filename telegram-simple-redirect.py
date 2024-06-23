from argparse import ArgumentParser, Namespace
import json
from typing import Any, Dict, Tuple, TypeAlias
from dataclasses import dataclass, asdict
from flask import Flask, request
import asyncio
from multiprocessing import Process
from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, MessageHandler, filters
import requests

DEFAULT_PORT = 6060

Url: TypeAlias = str


@dataclass(frozen=True, init=True, kw_only=True)
class ParsedMessage:
    id: int
    fullname: str
    username: str
    is_bot: bool
    message: str
    formatted_message: str
    # images: Tuple[Url]
    # videos: Tuple[Url]


def parse_argv() -> Dict[str, str]:
    """Set command line arguments and parses them."""
    parser = ArgumentParser()
    default_options = {
        # "nargs": 1,
        "required": True,
        "type": str,
        "default": None,
    }

    # parser.add_argument(
    #     "--send-to",
    #     **default_options,
    #     help="HTTP endpoint to which send the redirected messages",
    # )

    parser.add_argument(
        "--chat",
        **default_options,
        help="Phone number or group to watch for messages",
    )

    parser.add_argument(
        "--token",
        **default_options,
        help="Telegram app API token",
    )

    parser.add_argument(
        "--host",
        **default_options,
        help="HTTP URL of recipient server",
    )

    parser.add_argument(
        "--port", **default_options, help="HTTP server port related to specified HOST"
    )

    args: Namespace = parser.parse_args()

    return vars(args)


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

    args = parse_argv()
    host: str = args["host"] or "localhost"
    port: int

    try:
        port = int(args["port"])
    except ValueError:
        port = DEFAULT_PORT

    asyncio.run(app.run(host=host, port=port))


def bot() -> None:
    """Sends message to local http server."""
    args = parse_argv()
    # endpoint: str = args["--send-to"]
    token: str = args["token"]
    chat: str = args["chat"]
    host: str = args["host"] or "localhost"
    port: int

    try:
        port = int(args["port"])
    except ValueError:
        port = DEFAULT_PORT

    # if not endpoint:
    #     print("Invalid endpoint string")
    #     return

    if not token:
        print("Invalid token string")
        return

    if not chat:
        print("Invalid chat identifier string")
        return

    async def redirect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = ParsedMessage(
            message=update.message.text or "",
            formatted_message=update.message.text_markdown_v2_urled or "",
            id=update.message.from_user.id,
            fullname=update.message.from_user.full_name,
            username=update.message.from_user.username or "",
            is_bot=update.message.from_user.is_bot,
        )

        response = requests.post(f"http://localhost:{port}", json=asdict(data))

        if response.status_code == 200:
            prittified = json.dumps(asdict(data), indent=2)
            await update.message.reply_markdown(f"```json\n{prittified}\n```")

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
