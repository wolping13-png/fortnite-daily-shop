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
SHOP_JSON_PATH = BASE_DIR / "shop.json"
SHOP_SECTIONS_DIR = BASE_DIR / "shop_sections"
SHOP_SECTIONS_MANIFEST = SHOP_SECTIONS_DIR / "manifest.json"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "gemini_bot_config.json not found. Copy gemini_bot_config.example.json first."
        )

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("gemini_bot_config.json must contain a JSON object.")

    provider = str(data.get("provider") or "gemini").lower()
    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY") or str(data.get("deepseek_api_key") or "")
        if not api_key or api_key == "PASTE_YOUR_DEEPSEEK_API_KEY_HERE":
            raise ValueError("DeepSeek API key is missing.")
        data["deepseek_api_key"] = api_key
    else:
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


def load_shop_pages(limit: int | None = None) -> list[tuple[Path, str]]:
    if not SHOP_SECTIONS_MANIFEST.exists():
        return []

    try:
        data = json.loads(SHOP_SECTIONS_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return []

    pages = data.get("pages")
    if not isinstance(pages, list):
        return []

    result: list[tuple[Path, str]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        path = BASE_DIR / str(page.get("path") or "")
        if not path.exists():
            continue
        caption = str(page.get("caption") or "Fortnite 每日商店")
        result.append((path, caption))
        if limit is not None and len(result) >= limit:
            break
    return result


def send_shop_image(config: dict[str, Any], group_id: int | str, send_all: bool = False) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    caption = str(config.get("shop_caption") or "Fortnite 每日商店")
    if not send_all:
        image_path = SHOP_IMAGE_PATH if SHOP_IMAGE_PATH.exists() else BASE_DIR / "shop.png"
        message = build_message(caption=f"{caption}\n官方分区总图", image_path=image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
            timeout=120,
        )
        return

    pages = load_shop_pages()

    if pages:
        for index, (image_path, page_caption) in enumerate(pages, 1):
            text = f"{caption}\n{page_caption}"
            message = build_message(caption=text, image_path=image_path)
            post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={"group_id": group_id, "message": message},
                access_token=access_token,
                timeout=90,
            )
        return

    image_path = SHOP_IMAGE_PATH if SHOP_IMAGE_PATH.exists() else BASE_DIR / "shop.png"
    message = build_message(caption=f"{caption}\n官方分区总图", image_path=image_path)
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


def is_shop_question(question: str) -> bool:
    value = question.lower()
    keywords = (
        "商店",
        "商城",
        "皮肤",
        "价格",
        "v-buck",
        "vbuck",
        "vbucks",
        "fortnite",
        "堡垒",
        "今天有什么",
        "推荐",
    )
    return any(keyword in value for keyword in keywords)


def load_shop_summary(max_items: int = 120) -> str:
    if not SHOP_JSON_PATH.exists():
        return "今天的 Fortnite 商店数据文件还没有生成。"

    try:
        data = json.loads(SHOP_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "今天的 Fortnite 商店数据文件读取失败。"

    items = data.get("items")
    if not isinstance(items, list) or not items:
        return "今天的 Fortnite 商店数据为空。"

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section") or "未分区")
        groups.setdefault(section, []).append(item)

    lines = [
        "今天 Fortnite 每日商店真实数据如下。回答时只基于这些数据，不要编造普通电商商品、优惠券或现实世界商店内容。",
        f"更新时间：{data.get('updatedAt') or data.get('date') or '未知'}",
    ]

    count = 0
    for section, section_items in groups.items():
        lines.append(f"\n分区：{section}")
        for item in section_items:
            if count >= max_items:
                lines.append("还有更多商品，已省略。")
                return "\n".join(lines)

            name = str(item.get("name") or "未知物品")
            rarity = str(item.get("rarity") or "未知稀有度")
            price = item.get("price")
            price_text = f"{price} V-Bucks" if price is not None else "未知价格"
            lines.append(f"- {name} | {rarity} | {price_text}")
            count += 1

    return "\n".join(lines)


def enrich_question(question: str) -> str:
    if not is_shop_question(question):
        return question

    return (
        f"{question}\n\n"
        "请注意：用户说的“商店”默认指 Fortnite 每日商店，不是普通电商平台。\n"
        "请根据下面的数据，用简体中文总结亮点、分区、值得注意的联动/稀有度/价格。不要编造数据里没有的商品。\n\n"
        f"{load_shop_summary()}"
    )


def ask_gemini(config: dict[str, Any], question: str) -> str:
    model = str(config.get("model") or "gemini-2.0-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    system_prompt = str(
        config.get("system_prompt")
        or "你是一个友好的 QQ 群助手。用简体中文回答，简洁一点。"
    )

    user_question = enrich_question(question)

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
                    "parts": [{"text": user_question}],
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


def ask_deepseek(config: dict[str, Any], question: str) -> str:
    base_url = str(config.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = str(config.get("model") or "deepseek-v4-flash")
    system_prompt = str(
        config.get("system_prompt")
        or "你是一个友好的 QQ 群助手。用简体中文回答，简洁一点。"
    )

    user_question = enrich_question(question)

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['deepseek_api_key']}",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            "temperature": float(config.get("temperature", 0.7)),
            "max_tokens": int(config.get("max_output_tokens", 700)),
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return "DeepSeek 没有返回内容。"

    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return "DeepSeek 没有返回文字内容。"
    answer = str(message.get("content") or "").strip()
    return answer or "DeepSeek 没有返回文字内容。"


def ask_model(config: dict[str, Any], question: str) -> str:
    provider = str(config.get("provider") or "gemini").lower()
    if provider == "deepseek":
        return ask_deepseek(config, question)
    return ask_gemini(config, question)


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

    ask_prefix = str(config.get("ask_prefix") or "温德尔")
    shop_command = str(config.get("shop_command") or "商店")
    shop_all_command = str(config.get("shop_all_command") or "商店全部")

    if text in {shop_command, shop_all_command}:
        send_shop_image(config, group_id, send_all=text == shop_all_command)
        return

    if not text.startswith(ask_prefix):
        return

    question = text[len(ask_prefix) :].strip()
    question = question.lstrip(" ：:，,")
    if not question:
        send_group_text(config, group_id, f"用法：{ask_prefix} 你想问的问题")
        return

    try:
        answer = ask_model(config, question)
    except Exception as exc:
        print(f"Model request failed: {exc}", file=sys.stderr)
        send_group_text(config, group_id, "AI 暂时没有回复成功，稍后再试一下。")
        return

    for chunk in split_reply(answer):
        send_group_text(config, group_id, chunk)


class OneBotHandler(BaseHTTPRequestHandler):
    config: dict[str, Any] = {}

    def read_body(self) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" not in transfer_encoding:
            length = int(self.headers.get("Content-Length") or "0")
            return self.rfile.read(length)

        body = bytearray()
        while True:
            size_line = self.rfile.readline().strip()
            if not size_line:
                continue

            chunk_size = int(size_line.split(b";", 1)[0], 16)
            if chunk_size == 0:
                self.rfile.readline()
                break

            body.extend(self.rfile.read(chunk_size))
            self.rfile.readline()

        return bytes(body)

    def do_POST(self) -> None:
        try:
            body = self.read_body()
            if not body.strip():
                self.send_response(204)
                self.end_headers()
                return

            event = json.loads(body.decode("utf-8"))
            if isinstance(event, dict):
                threading.Thread(target=handle_event, args=(self.config, event), daemon=True).start()

            self.send_response(204)
            self.end_headers()
        except json.JSONDecodeError:
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
