from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from send_qq_shop import build_message, post_onebot


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
SHOP_IMAGE_PATH = BASE_DIR / "shop_qq.jpg"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "gemini_bot_config.json not found. Copy gemini_bot_config.example.json first."
        )

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("gemini_bot_config.json must contain a JSON object.")

    api_key = os.environ.get("GEMINI_API_KEY") or str(data.get("gemini_api_key") or "")
    if not api_key or api_key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("Gemini API key is missing.")

    data["gemini_api_key"] = api_key
    return data


def normalize_base_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value.rstrip("/") + "/"


def allowed_groups(config: dict[str, Any]) -> set[str]:
    return {str(group_id).strip() for group_id in config.get("allowed_group_ids", []) if str(group_id).strip()}


def extract_text(event: dict[str, Any]) -> str:
    raw = event.get("raw_message")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    message = event.get("message")
    if isinstance(message, str):
        return message.strip()

    if not isinstance(message, list):
        return ""

    parts: list[str] = []
    for segment in message:
        if not isinstance(segment, dict):
            continue
        if segment.get("type") != "text":
            continue
        data = segment.get("data")
        if isinstance(data, dict):
            parts.append(str(data.get("text") or ""))

    return "".join(parts).strip()


def send_group_text(config: dict[str, Any], group_id: int | str, text: str) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={
            "group_id": group_id,
            "message": [{"type": "text", "data": {"text": text}}],
        },
        access_token=access_token,
        timeout=60,
    )


def send_shop_image(config: dict[str, Any], group_id: int | str) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    caption = str(config.get("shop_caption") or "Fortnite 每日商店")
    image_path = SHOP_IMAGE_PATH if SHOP_IMAGE_PATH.exists() else BASE_DIR / "shop.png"
    message = build_message(caption=caption, image_path=image_path)
    post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": message},
        access_token=access_token,
        timeout=90,
    )


def split_reply(text: str, limit: int = 900) -> list[str]:
    value = text.strip()
    if len(value) <= limit:
        return [value]

    chunks: list[str] = []
    while value:
        chunk = value[:limit]
        cut = max(chunk.rfind("\n"), chunk.rfind("。"), chunk.rfind("！"), chunk.rfind("？"))
        if cut > 200:
            chunk = value[: cut + 1]
        chunks.append(chunk.strip())
        value = value[len(chunk) :].strip()
    return chunks


def ask_gemini(config: dict[str, Any], question: str) -> str:
    model = str(config.get("model") or "gemini-2.5-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    system_prompt = str(
        config.get("system_prompt")
        or "你是一个友好的 QQ 群助手。用简体中文回答，简洁一点。"
    )

    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": str(config["gemini_api_key"]),
        },
        json={
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": question}],
                }
            ],
            "generationConfig": {
                "temperature": float(config.get("temperature", 0.7)),
                "maxOutputTokens": int(config.get("max_output_tokens", 700)),
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "Gemini 没有返回内容。"

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
    answer = "\n".join(text for text in texts if text.strip()).strip()
    return answer or "Gemini 没有返回文字内容。"


def handle_event(config: dict[str, Any], event: dict[str, Any]) -> None:
    if event.get("post_type") != "message":
        return
    if event.get("message_type") != "group":
        return

    group_id = event.get("group_id")
    if group_id is None:
        return

    groups = allowed_groups(config)
    if groups and str(group_id) not in groups:
        return

    text = extract_text(event)
    if not text:
        return

    ask_prefix = str(config.get("ask_prefix") or "/问")
    shop_command = str(config.get("shop_command") or "/商店")

    if text == shop_command:
        send_shop_image(config, group_id)
        return

    if not text.startswith(ask_prefix):
        return

    question = text[len(ask_prefix) :].strip()
    if not question:
        send_group_text(config, group_id, f"用法：{ask_prefix} 你想问的问题")
        return

    try:
        answer = ask_gemini(config, question)
    except Exception as exc:
        print(f"Gemini request failed: {exc}", file=sys.stderr)
        send_group_text(config, group_id, "Gemini 暂时没有回复成功，稍后再试一下。")
        return

    for chunk in split_reply(answer):
        send_group_text(config, group_id, chunk)


class OneBotHandler(BaseHTTPRequestHandler):
    config: dict[str, Any] = {}

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length)
            event = json.loads(body.decode("utf-8"))
            if isinstance(event, dict):
                threading.Thread(target=handle_event, args=(self.config, event), daemon=True).start()

            self.send_response(204)
            self.end_headers()
        except Exception as exc:
            print(f"Failed to handle OneBot event: {exc}", file=sys.stderr)
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    config = load_config()
    host = str(config.get("listen_host") or "127.0.0.1")
    port = int(config.get("listen_port") or 8080)
    OneBotHandler.config = config

    server = ThreadingHTTPServer((host, port), OneBotHandler)
    print(f"Gemini QQ bot listening on http://{host}:{port}/onebot")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
