from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import random
import re
import shutil
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
VALORANT_MEMORY_PATH = BASE_DIR / "bot_memory" / "valorant_users.json"
VALORANT_OUTPUT_DIR = BASE_DIR / "bot_memory" / "valorant_shop"
VALORANT_TEMP_DIR = BASE_DIR / "temp" / "valorant"
VALORANT_LOCK = threading.RLock()
LOGGER = logging.getLogger("valorant_shop")


class ValorantShopError(RuntimeError):
    pass


class ValorantNotBound(ValorantShopError):
    pass


class ValorantAuthExpired(ValorantShopError):
    pass


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(38, True)
FONT_SUBTITLE = load_font(18)
FONT_NAME = load_font(22, True)
FONT_PRICE = load_font(20, True)
FONT_SMALL = load_font(15)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    value = str(text or "").strip()
    if text_size(draw, value, font)[0] <= max_width:
        return value
    while value and text_size(draw, f"{value}...", font)[0] > max_width:
        value = value[:-1]
    return f"{value}..." if value else ""


def safe_user_segment(user_id: str) -> str:
    raw = str(user_id or "").strip()
    normalized = re.sub(r"[^0-9A-Za-z_-]", "_", raw).strip("_") or "user"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:32]}_{digest}"


def load_valorant_data() -> dict[str, Any]:
    if not VALORANT_MEMORY_PATH.exists():
        return {"users": {}, "watchlists": {}}
    try:
        data = json.loads(VALORANT_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "watchlists": {}}
    if not isinstance(data, dict):
        return {"users": {}, "watchlists": {}}
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    if not isinstance(data.get("watchlists"), dict):
        data["watchlists"] = {}
    return data


def save_valorant_data(data: dict[str, Any]) -> None:
    VALORANT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = VALORANT_MEMORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(VALORANT_MEMORY_PATH)


def get_valorant_user_config(user_id: str) -> dict[str, Any] | None:
    with VALORANT_LOCK:
        users = load_valorant_data().get("users", {})
        config = users.get(str(user_id))
        return dict(config) if isinstance(config, dict) else None


def save_valorant_user_config(user_id: str, user_config: dict[str, Any]) -> None:
    with VALORANT_LOCK:
        data = load_valorant_data()
        users = data.setdefault("users", {})
        users[str(user_id)] = {
            "userId": str(user_config.get("userId") or ""),
            "tid": str(user_config.get("tid") or ""),
            "nickname": str(user_config.get("nickname") or ""),
            "openid": str(user_config.get("openid") or ""),
            "uin": str(user_config.get("uin") or ""),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_valorant_data(data)


def clear_valorant_user_config(user_id: str) -> bool:
    with VALORANT_LOCK:
        data = load_valorant_data()
        users = data.setdefault("users", {})
        existed = str(user_id) in users
        users.pop(str(user_id), None)
        data.setdefault("watchlists", {}).pop(str(user_id), None)
        save_valorant_data(data)
        return existed


def get_valorant_watchlist(user_id: str) -> list[str]:
    with VALORANT_LOCK:
        watchlists = load_valorant_data().get("watchlists", {})
        items = watchlists.get(str(user_id), [])
        return [str(item).strip() for item in items if str(item).strip()] if isinstance(items, list) else []


def add_valorant_watch_item(user_id: str, item_name: str) -> bool:
    item = str(item_name or "").strip().strip('"')
    if not item:
        raise ValueError("item_name is empty")
    with VALORANT_LOCK:
        data = load_valorant_data()
        watchlists = data.setdefault("watchlists", {})
        items = [str(value).strip() for value in watchlists.get(str(user_id), []) if str(value).strip()]
        if any(value.lower() == item.lower() for value in items):
            return False
        items.append(item)
        watchlists[str(user_id)] = items
        save_valorant_data(data)
        return True


def remove_valorant_watch_item(user_id: str, item_name: str) -> bool:
    item = str(item_name or "").strip().strip('"')
    with VALORANT_LOCK:
        data = load_valorant_data()
        watchlists = data.setdefault("watchlists", {})
        items = [str(value).strip() for value in watchlists.get(str(user_id), []) if str(value).strip()]
        kept = [value for value in items if value.lower() != item.lower()]
        changed = len(kept) != len(items)
        watchlists[str(user_id)] = kept
        save_valorant_data(data)
        return changed


class ValorantShopClient:
    LOGIN_URL_TEMPLATE = (
        "https://xui.ptlogin2.qq.com/cgi-bin/xlogin?"
        "pt_enable_pwd=1&appid=716027609&pt_3rd_aid=102061775&daid=381&"
        "pt_skey_valid=0&style=35&force_qr=1&autorefresh=1&"
        "s_url=http%3A%2F%2Fconnect.qq.com&refer_cgi=m_authorize&ucheck=1&"
        "fall_to_wv=1&status_os=12&redirect_uri=auth%3A%2F%2Ftauth.qq.com%2F&"
        "client_id=102061775&pf=openmobile_android&response_type=token&scope=all&"
        "sdkp=a&sdkv=3.5.17.lite&sign=a6479455d3e49b597350f13f776a6288&"
        "status_machine=MjMxMTdSSzY2Qw%3D%3D&switch=1&time=1763280194&"
        "show_download_ui=true&h5sig=trobryxo8IPM0GaSQH12mowKG-CY65brFzkK7_-9EW4&loginty=6"
    )
    PTQR_SHOW_URL = "https://xui.ptlogin2.qq.com/ssl/ptqrshow"
    PTQR_LOGIN_URL = "https://xui.ptlogin2.qq.com/ssl/ptqrlogin"
    OPENMOBILE_REDIRECT_URL = "https://openmobile.qq.com/oauth2.0/m_get_redirect_url"
    PTQR_AID = "716027609"
    PTQR_DAID = "381"
    PTQR_THIRD_AID = "102061775"
    DEFAULT_LOGIN_CALLBACK_URL = "http://connect.qq.com"
    DEFAULT_LOGIN_U1_URL = "http://connect.qq.com"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def _get_config_value(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def _normalize_url(self, value: str, default: str = "") -> str:
        url = (value or default or "").strip()
        if not url:
            return ""
        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = f"https://{url.lstrip('/')}"
        return url

    def _get_login_callback_url(self) -> str:
        value = str(self._get_config_value("valorant_login_callback_url", self.DEFAULT_LOGIN_CALLBACK_URL))
        return self._normalize_url(value, self.DEFAULT_LOGIN_CALLBACK_URL)

    def _get_login_u1_url(self, callback_url: str) -> str:
        value = str(self._get_config_value("valorant_login_u1_url", self.DEFAULT_LOGIN_U1_URL))
        return self._normalize_url(value, self.DEFAULT_LOGIN_U1_URL)

    def _build_login_url(self, callback_url: str) -> str:
        encoded_callback = urllib.parse.quote(callback_url, safe="")
        return re.sub(
            r"([?&])s_url=[^&]*",
            lambda match: f"{match.group(1)}s_url={encoded_callback}",
            self.LOGIN_URL_TEMPLATE,
            count=1,
        )

    def _get_cookie_value(self, session: aiohttp.ClientSession, url: str, name: str) -> str:
        try:
            cookie = session.cookie_jar.filter_cookies(url).get(name)
            return cookie.value if cookie else ""
        except Exception:
            return ""

    def _calc_ptqrtoken(self, qrsig: str) -> int:
        token = 0
        for ch in qrsig:
            token += (token << 5) + ord(ch)
        return token & 2147483647

    def _parse_ptui_callback(self, text: str) -> dict[str, str] | None:
        match = re.search(r"ptuiCB\('([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'", text)
        if not match:
            return None
        return {
            "code": match.group(1),
            "redirect_url": match.group(3).replace("\\/", "/").replace("\\x26", "&"),
            "message": match.group(5),
        }

    def _extract_login_data_from_success_url(self, success_url: str) -> dict[str, Any]:
        def normalize_url(url: str) -> str:
            return (url or "").replace("\\/", "/").replace("\\x26", "&").strip()

        def parse_param_str(raw: str) -> dict[str, str]:
            parsed: dict[str, str] = {}
            if not raw:
                return parsed
            for key, value in urllib.parse.parse_qs(raw.replace("#&", "&").lstrip("&"), keep_blank_values=True).items():
                if value:
                    parsed[key] = value[0]
            return parsed

        nested_keys = {
            "u1",
            "url",
            "jump_url",
            "redirect_uri",
            "redirect_url",
            "target_url",
            "s_url",
            "f_url",
            "qtarget",
            "jump",
            "ru",
        }
        merged_params: dict[str, str] = {}
        queue = [normalize_url(success_url)]
        visited: set[str] = set()
        while queue:
            candidate = queue.pop(0)
            if not candidate or candidate in visited:
                continue
            visited.add(candidate)
            decoded = candidate
            for _ in range(3):
                next_decoded = urllib.parse.unquote(decoded)
                if next_decoded == decoded:
                    break
                decoded = next_decoded
            parsed_url = urllib.parse.urlparse(decoded)
            candidate_params: dict[str, str] = {}
            for raw_part in (parsed_url.query, parsed_url.fragment):
                candidate_params.update(parse_param_str(raw_part))
            if not candidate_params and ("openid=" in decoded or "access_token=" in decoded):
                candidate_params.update(parse_param_str(decoded))
            for key, value in candidate_params.items():
                merged_params.setdefault(key, value)
            for nested_key in nested_keys:
                nested_value = candidate_params.get(nested_key, "")
                if nested_value and nested_value not in visited:
                    queue.append(normalize_url(nested_value))
        return {
            "openid": merged_params.get("openid", ""),
            "appid": merged_params.get("appid", ""),
            "access_token": merged_params.get("access_token", ""),
            "pay_token": merged_params.get("pay_token", ""),
            "key": merged_params.get("key", ""),
            "redirect_uri_key": merged_params.get("redirect_uri_key", ""),
            "expires_in": merged_params.get("expires_in", "7776000"),
            "pf": merged_params.get("pf", "openmobile_android"),
            "status_os": merged_params.get("status_os", "12"),
            "status_machine": merged_params.get("status_machine", ""),
            "full_params": merged_params,
        }

    def _build_pt_openlogin_data(self, login_url: str, session: aiohttp.ClientSession) -> str:
        parsed = urllib.parse.urlparse(login_url)
        query_map = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        def q(name: str, default: str = "") -> str:
            values = query_map.get(name, [])
            return values[0] if values else default

        tid = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "idt") or str(int(time.time()))
        auth_time = str(int(time.time() * 1000))
        return urllib.parse.urlencode(
            [
                ("which", ""),
                ("refer_cgi", q("refer_cgi", "m_authorize")),
                ("response_type", q("response_type", "token")),
                ("client_id", q("client_id", self.PTQR_THIRD_AID)),
                ("state", ""),
                ("display", ""),
                ("openapi", "1011"),
                ("switch", q("switch", "1")),
                ("src", "1"),
                ("sdkv", q("sdkv", "3.5.17.lite")),
                ("sdkp", q("sdkp", "a")),
                ("tid", tid),
                ("pf", q("pf", "openmobile_android")),
                ("need_pay", "0"),
                ("browser", "0"),
                ("browser_error", ""),
                ("serial", ""),
                ("token_key", ""),
                ("redirect_uri", q("redirect_uri", "auth://tauth.qq.com/")),
                ("sign", q("sign", "")),
                ("time", q("time", "")),
                ("status_version", ""),
                ("status_os", q("status_os", "12")),
                ("status_machine", q("status_machine", "")),
                ("page_type", "1"),
                ("has_auth", "1"),
                ("update_auth", "1"),
                ("auth_time", auth_time),
                ("loginfrom", ""),
                ("h5sig", q("h5sig", "")),
                ("loginty", q("loginty", "6")),
            ]
        )

    def _extract_jsver_from_login_page(self, login_page: str) -> str:
        patterns = [
            r"/monorepo/([0-9A-Za-z]+)/ptlogin/js/login_10\.js",
            r"/monorepo/([0-9A-Za-z]+)/ptlogin/js/",
            r"https://qq-web\.cdn-go\.cn/monorepo/([0-9A-Za-z]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, login_page or "")
            if match:
                return match.group(1)
        return "28d22679"

    def _build_aegis_uid(self, session: aiohttp.ClientSession) -> str:
        aegis_uid = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "__aegis_uid")
        if aegis_uid:
            return aegis_uid
        server_ip = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "pt_serverip")
        client_ip = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "pt_clientip")
        if server_ip and client_ip:
            return f"{server_ip}-{client_ip}-4458"
        return ""

    def _extract_auth_url_from_callback_body(self, text: str) -> str:
        callback_match = re.search(r"_Callback\s*\(\s*(\{.*?\})\s*\)\s*;?\s*$", text or "", re.DOTALL)
        if callback_match:
            try:
                payload = json.loads(callback_match.group(1))
                callback_url = str(payload.get("url", "") or "").strip()
                if callback_url.startswith("auth://"):
                    return callback_url
            except Exception:
                pass
        auth_match = re.search(r"(auth://tauth\.qq\.com/[^\s\"'<>]+)", text or "")
        return auth_match.group(1) if auth_match else ""

    def _merge_login_data(self, base_data: dict[str, Any], extra_data: dict[str, Any]) -> dict[str, Any]:
        base = dict(base_data or {})
        extra = dict(extra_data or {})
        merged_params: dict[str, str] = dict(base.get("full_params", {}) or {})
        merged_params.update(extra.get("full_params", {}) or {})
        for key in (
            "openid",
            "appid",
            "access_token",
            "pay_token",
            "key",
            "redirect_uri_key",
            "expires_in",
            "pf",
            "status_os",
            "status_machine",
        ):
            if not base.get(key) and extra.get(key):
                base[key] = extra[key]
        base["full_params"] = merged_params
        return base

    def _collect_redirect_key_candidates(
        self,
        session: aiohttp.ClientSession,
        login_data: dict[str, Any],
        success_url: str,
    ) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add_key(value: str, source: str) -> None:
            keystr = (value or "").strip()
            if not keystr or keystr in seen:
                return
            seen.add(keystr)
            result.append((keystr, source))

        full_params = (login_data or {}).get("full_params", {}) or {}
        for key_name in ("redirect_uri_key", "keystr", "key", "uikey", "superkey", "supertoken"):
            add_key(str(full_params.get(key_name, "")), f"param:{key_name}")

        normalized_url = (success_url or "").replace("\\/", "/").replace("\\x26", "&")
        parsed = urllib.parse.urlparse(normalized_url)
        raw_parts = [parsed.query, parsed.fragment]
        if not parsed.query and not parsed.fragment:
            raw_parts.append(normalized_url)
        for raw in raw_parts:
            if not raw:
                continue
            raw_params = urllib.parse.parse_qs(raw.replace("#&", "&"), keep_blank_values=True)
            for key_name in ("redirect_uri_key", "keystr", "key", "uikey", "superkey", "supertoken"):
                values = raw_params.get(key_name, [])
                if values:
                    add_key(values[0], f"url:{key_name}")

        for domain in (
            "https://xui.ptlogin2.qq.com",
            "https://ssl.ptlogin2.qq.com",
            "https://ptlogin4.openmobile.qq.com",
            "https://openmobile.qq.com",
            "https://connect.qq.com",
        ):
            host = urllib.parse.urlparse(domain).netloc
            for key_name in ("redirect_uri_key", "keystr", "uikey", "superkey", "supertoken", "key"):
                add_key(self._get_cookie_value(session, domain, key_name), f"cookie:{host}:{key_name}")
        return result

    async def _fetch_auth_url_by_redirect_key(self, session: aiohttp.ClientSession, redirect_uri_key: str) -> str:
        keystr = (redirect_uri_key or "").strip()
        if not keystr:
            return ""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/101.0.4951.61 Mobile Safari/537.36 tencent_game_emulator"
            ),
            "Accept": "*/*",
            "Referer": "https://imgcache.qq.com/",
        }
        try:
            async with session.get(
                self.OPENMOBILE_REDIRECT_URL,
                params={"keystr": keystr},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20, connect=10, sock_connect=10, sock_read=15),
            ) as response:
                body = await response.text(errors="ignore")
                if response.status != 200:
                    return ""
                return self._extract_auth_url_from_callback_body(body)
        except Exception:
            return ""

    def _extract_url_from_body(self, body: str) -> str:
        text = (body or "").replace("\\/", "/").replace("\\x26", "&")
        patterns = [
            r"ptuiCB\('[^']*','[^']*','([^']+)'",
            r"ptui_auth_CB\('[^']*','[^']*','([^']+)'",
            r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",
            r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",
            r"(auth://tauth\.qq\.com/[^\s\"'<>]+)",
            r"(https?://imgcache\.qq\.com/[^\s\"'<>]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    async def _resolve_login_success_url(
        self,
        session: aiohttp.ClientSession,
        success_url: str,
        referer_url: str = "",
    ) -> str:
        current_url = (success_url or "").replace("\\/", "/").replace("\\x26", "&").strip()
        if not current_url or "check_sig" not in current_url:
            return current_url
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/101.0.4951.61 Mobile Safari/537.36 tencent_game_emulator"
            ),
            "Accept": "*/*",
            "Referer": referer_url or "https://openmobile.qq.com/",
        }
        try:
            async with session.get(
                current_url,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15, connect=8, sock_connect=8, sock_read=10),
            ) as response:
                body = await response.text(errors="ignore")
                location = (response.headers.get("Location", "") or "").strip()
                if location:
                    return urllib.parse.urljoin(str(response.url), location)
                body_url = self._extract_url_from_body(body)
                if body_url:
                    return body_url
        except Exception:
            pass
        return current_url

    async def generate_qr_code_http(self) -> dict[str, Any] | None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        callback_url = self._get_login_callback_url()
        u1_url = self._get_login_u1_url(callback_url)
        login_url = self._build_login_url(callback_url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/101.0.4951.61 Mobile Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://openmobile.qq.com/",
            "X-Requested-With": "com.tencent.apps.valorant",
            "Cookie": "accountType=5; clientType=9",
        }
        try:
            async with session.get(login_url, headers=headers) as response:
                response.raise_for_status()
                login_page = await response.text(errors="ignore")

            login_sig = ""
            login_sig_match = re.search(r"g_login_sig=encodeURIComponent\(\"([^\"]+)\"\)", login_page)
            if login_sig_match:
                login_sig = login_sig_match.group(1)
            if not login_sig:
                login_sig = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "pt_login_sig")
            if not login_sig:
                login_sig = self._get_cookie_value(session, "https://ssl.ptlogin2.qq.com", "pt_login_sig")

            parsed_login_url = urllib.parse.urlparse(login_url)
            login_query_map = urllib.parse.parse_qs(parsed_login_url.query, keep_blank_values=True)
            login_u1 = u1_url
            pt_uistyle = login_query_map.get("style", ["35"])[0] or "35"
            ptlang = login_query_map.get("ptlang", ["2052"])[0] or "2052"
            jsver = self._extract_jsver_from_login_page(login_page)
            pt_openlogin_data = self._build_pt_openlogin_data(login_url, session)
            aegis_uid = self._build_aegis_uid(session)

            qr_params = {
                "s": "8",
                "e": "0",
                "appid": self.PTQR_AID,
                "type": "0",
                "t": str(random.random()),
                "u1": login_u1,
                "daid": self.PTQR_DAID,
                "pt_3rd_aid": self.PTQR_THIRD_AID,
            }
            qr_headers = {
                "User-Agent": headers["User-Agent"],
                "Referer": login_url,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "X-Requested-With": "com.tencent.apps.valorant",
            }
            async with session.get(self.PTQR_SHOW_URL, params=qr_params, headers=qr_headers) as response:
                response.raise_for_status()
                qr_image_bytes = await response.read()

            qrsig = self._get_cookie_value(session, "https://xui.ptlogin2.qq.com", "qrsig")
            if not qrsig:
                qrsig = self._get_cookie_value(session, "https://ssl.ptlogin2.qq.com", "qrsig")
            if not qrsig:
                raise RuntimeError("未获取到 qrsig")

            qr_dir = VALORANT_OUTPUT_DIR / "qr"
            qr_dir.mkdir(parents=True, exist_ok=True)
            filename = qr_dir / f"valorant_qr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filename.write_bytes(qr_image_bytes)
            return {
                "session": session,
                "filename": filename,
                "ptqrtoken": self._calc_ptqrtoken(qrsig),
                "login_sig": login_sig,
                "login_url": login_url,
                "u1_url": login_u1,
                "callback_url": callback_url,
                "pt_openlogin_data": pt_openlogin_data,
                "aegis_uid": aegis_uid,
                "jsver": jsver,
                "pt_uistyle": pt_uistyle,
                "ptlang": ptlang,
            }
        except Exception:
            LOGGER.exception("Valorant QQ QR generation failed")
            await session.close()
            return None

    async def wait_for_http_login_result(
        self,
        session: aiohttp.ClientSession,
        ptqrtoken: int,
        login_sig: str,
        login_u1: str,
        referer_url: str,
        pt_openlogin_data: str = "",
        aegis_uid: str = "",
        jsver: str = "28d22679",
        pt_uistyle: str = "35",
        ptlang: str = "2052",
        timeout: int = 30,
    ) -> dict[str, Any] | None:
        poll_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/101.0.4951.61 Mobile Safari/537.36 tencent_game_emulator"
            ),
            "Referer": referer_url,
            "Accept": "*/*",
            "X-Requested-With": "com.tencent.apps.valorant",
        }
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                params = {
                    "u1": login_u1,
                    "from_ui": "1",
                    "type": "1",
                    "ptlang": str(ptlang or "2052"),
                    "ptqrtoken": str(ptqrtoken),
                    "daid": self.PTQR_DAID,
                    "aid": self.PTQR_AID,
                    "pt_3rd_aid": self.PTQR_THIRD_AID,
                    "pt_openlogin_data": pt_openlogin_data,
                    "device": "2",
                    "ptopt": "1",
                    "pt_uistyle": str(pt_uistyle or "35"),
                    "jsver": str(jsver or "28d22679"),
                    "r": str(random.random()),
                }
                if login_sig:
                    params["login_sig"] = login_sig
                if aegis_uid:
                    params["aegis_uid"] = aegis_uid

                async with session.get(self.PTQR_LOGIN_URL, params=params, headers=poll_headers) as response:
                    response.raise_for_status()
                    text = await response.text(errors="ignore")

                callback = self._parse_ptui_callback(text)
                if not callback:
                    await asyncio.sleep(2)
                    continue
                code = callback["code"]
                if code == "0":
                    success_url = callback.get("redirect_url", "")
                    login_data = self._extract_login_data_from_success_url(success_url)
                    if not (login_data.get("openid") and login_data.get("access_token")):
                        resolved_url = await self._resolve_login_success_url(session, success_url, referer_url)
                        if resolved_url and resolved_url != success_url:
                            login_data = self._merge_login_data(
                                login_data,
                                self._extract_login_data_from_success_url(resolved_url),
                            )
                        for keystr, _source in self._collect_redirect_key_candidates(
                            session,
                            login_data,
                            resolved_url or success_url,
                        ):
                            auth_url = await self._fetch_auth_url_by_redirect_key(session, keystr)
                            if not auth_url:
                                continue
                            login_data = self._merge_login_data(
                                login_data,
                                self._extract_login_data_from_success_url(auth_url),
                            )
                            if login_data.get("openid") and login_data.get("access_token"):
                                break
                    if login_data.get("openid") and login_data.get("access_token"):
                        return login_data
                    return None
                if code == "65":
                    return None
                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(2)
        return None

    async def get_final_cookies(self, login_data: dict[str, Any]) -> dict[str, Any] | None:
        openid = login_data.get("openid", "")
        access_token = login_data.get("access_token", "")
        if not openid or not access_token:
            return None
        login_url = "https://app.mval.qq.com/go/auth/login_by_qq?source_game_zone=agame&game_zone=agame"
        headers = {
            "Cookie": "clientType=9; openid=null; access_token=null;",
            "User-Agent": (
                "mval/2.4.0.10053 Channel/10068 Manufacturer/Redmi  "
                "Mozilla/5.0 (Linux; Android 12; 23117RK66C Build/V417IR; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/101.0.4951.61 Mobile Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Host": "app.mval.qq.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        payload = {
            "clienttype": 9,
            "config_params": {"client_dev_name": "23117RK66C", "lang_type": 0},
            "login_info": {
                "appid": 102061775,
                "openid": openid,
                "qq_info_type": 5,
                "sig": access_token,
                "uin": 0,
            },
            "mappid": 10200,
            "mcode": "132f0a77d34402abc8463d60100011d19b0e",
            "source_game_zone": "agame",
            "game_zone": "agame",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(login_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                result = await response.json(content_type=None)
        if result.get("result") != 0:
            LOGGER.warning("Valorant final cookie request failed: %s", result)
            return None
        login_info = result.get("data", {}).get("login_info", {})
        uin = login_info.get("uin", 0)
        return {
            "userId": login_info.get("user_id", ""),
            "tid": login_info.get("wt", ""),
            "openid": openid,
            "uin": uin,
        }

    def _build_store_api_headers(self, user_config: dict[str, Any]) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Upload-Draft-Interop-Version": "5",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "User-Agent": (
                "mval/2.3.0.10050 Channel/5 Manufacturer/Xiaomi  "
                "Mozilla/5.0 (Linux; Android 14; 23078RKD5C Build/UP1A.230905.011; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/140.0.7339.207 Mobile Safari/537.36"
            ),
            "Connection": "keep-alive",
            "Upload-Complete": "?1",
            "GH-HEADER": "1-2-105-160-0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Cookie": (
                "clientType=9; "
                "uin=o105940478; "
                "appid=102061775; "
                "acctype=qc; "
                "openid=03A18A61C761D3C44890E2992BB868CE; "
                "access_token=551176E5981C1F5422A08C227D193827; "
                f"userId={user_config['userId']}; "
                "accountType=5; "
                f"tid={user_config['tid']}"
            ),
        }

    def _get_store_api_error_message(self, response_data: dict[str, Any]) -> str:
        return response_data.get("errMsg") or response_data.get("msg") or "未知错误"

    def _is_store_auth_invalid(self, result_code: Any, err_msg: str) -> bool:
        err_msg_lower = (err_msg or "").lower()
        return (
            result_code in {1001, 1003, 999999}
            or "ticket expire" in err_msg_lower
            or "auth web ticket fail" in err_msg_lower
        )

    def _extract_shop_goods_list(self, response_data: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        if "data" not in response_data:
            return [], "商店接口返回格式异常"
        data = response_data["data"]
        if not data:
            return [], None
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return [], "商店接口返回格式异常"
        goods_list = data.get("list", [])
        if not isinstance(goods_list, list):
            return [], "商店接口返回格式异常"
        return [item for item in goods_list if isinstance(item, dict)], None

    async def request_store_api(
        self,
        user_id: str,
        user_config: dict[str, Any],
        max_retries: int = 3,
        timeout: int = 15,
    ) -> tuple[dict[str, Any] | None, str | None, bool]:
        if not all(user_config.get(key) for key in ("userId", "tid")):
            return None, "登录配置不完整", False
        headers = self._build_store_api_headers(user_config)
        url = "https://app.mval.qq.com/go/mlol_store/agame/user_store"
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json={"_t": int(time.time())},
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as response:
                        response.raise_for_status()
                        data = await response.json(content_type=None)
                result_code = data.get("result")
                if result_code != 0:
                    err_msg = self._get_store_api_error_message(data)
                    return None, err_msg, self._is_store_auth_invalid(result_code, err_msg)
                return data, None, False
            except aiohttp.ClientError:
                if attempt < max_retries - 1:
                    continue
                return None, "请求商店接口失败", False
            except Exception:
                LOGGER.exception("Valorant store API request failed")
                if attempt < max_retries - 1:
                    continue
                return None, "处理商店数据时出错", False
        return None, "请求商店接口失败", False

    async def test_config_validity(self, user_id: str, user_config: dict[str, Any]) -> bool:
        response_data, _err_msg, _auth_invalid = await self.request_store_api(
            user_id,
            user_config,
            max_retries=1,
            timeout=10,
        )
        return bool(response_data)

    async def get_shop_items_raw(self, user_id: str, user_config: dict[str, Any]) -> list[dict[str, Any]]:
        response_data, err_msg, auth_invalid = await self.request_store_api(user_id, user_config)
        if not response_data:
            if auth_invalid:
                raise ValorantAuthExpired(err_msg or "登录凭证已过期")
            raise ValorantShopError(err_msg or "获取商店失败")
        goods_list, parse_err_msg = self._extract_shop_goods_list(response_data)
        if parse_err_msg:
            raise ValorantShopError(parse_err_msg)
        return goods_list

    async def download_image_bytes(self, session: aiohttp.ClientSession, url: str) -> bytes | None:
        if not url:
            return None
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=14)) as response:
                response.raise_for_status()
                return await response.read()
        except Exception:
            return None

    async def build_shop_image(self, user_id: str, goods_list: list[dict[str, Any]]) -> Path:
        if not goods_list:
            raise ValorantShopError("今日商店暂无可用数据")

        temp_dir = VALORANT_TEMP_DIR / safe_user_segment(user_id)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        cards: list[Image.Image] = []
        async with aiohttp.ClientSession() as session:
            for goods in goods_list:
                card = await self._build_goods_card(session, goods)
                cards.append(card)

        if not cards:
            raise ValorantShopError("商城图片生成失败")

        width = 900
        padding = 30
        gap = 20
        card_width = (width - padding * 2 - gap) // 2
        card_height = 260
        rows = (len(cards) + 1) // 2
        height = 128 + rows * card_height + max(0, rows - 1) * gap + 56

        canvas = Image.new("RGB", (width, height), (9, 15, 24))
        draw = ImageDraw.Draw(canvas)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = (
                int(9 + 8 * ratio),
                int(15 + 11 * ratio),
                int(24 + 25 * ratio),
            )
            draw.line((0, y, width, y), fill=color)

        title = "无畏契约每日商店"
        subtitle = datetime.now().strftime("%Y-%m-%d %H:%M 生成")
        draw.text((padding, 28), title, fill=(255, 248, 236), font=FONT_TITLE)
        draw.text((padding, 82), f"{subtitle} · 共 {len(cards)} 件", fill=(163, 198, 213), font=FONT_SUBTITLE)

        for index, card in enumerate(cards):
            row = index // 2
            col = index % 2
            x = padding + col * (card_width + gap)
            y = 128 + row * (card_height + gap)
            resized = card.resize((card_width, card_height), Image.Resampling.LANCZOS)
            canvas.paste(resized, (x, y))

        footer = "数据来自掌上无畏契约接口，价格和上架请以游戏内为准"
        footer_width, _ = text_size(draw, footer, FONT_SMALL)
        draw.text(((width - footer_width) // 2, height - 34), footer, fill=(130, 154, 170), font=FONT_SMALL)

        VALORANT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = VALORANT_OUTPUT_DIR / f"valorant_shop_{safe_user_segment(user_id)}.jpg"
        canvas.save(output, quality=88, optimize=True)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return output

    async def _build_goods_card(self, session: aiohttp.ClientSession, goods: dict[str, Any]) -> Image.Image:
        card_width = 420
        card_height = 260
        name = str(goods.get("goods_name") or "未知商品")
        price = str(goods.get("rmb_price") or goods.get("price") or "0")
        bg_bytes = await self.download_image_bytes(session, str(goods.get("bg_image") or ""))
        goods_bytes = await self.download_image_bytes(session, str(goods.get("goods_pic") or ""))

        card = Image.new("RGB", (card_width, card_height), (20, 44, 57))
        if bg_bytes:
            try:
                bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
                bg = ImageOps.fit(bg, (card_width, card_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                card.paste(bg, (0, 0))
            except Exception:
                pass

        overlay = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle((0, card_height - 90, card_width, card_height), fill=(0, 0, 0, 150))
        overlay_draw.rectangle((0, 0, card_width, card_height), outline=(94, 218, 215, 150), width=2)
        card_rgba = card.convert("RGBA")
        card_rgba.alpha_composite(overlay)

        if goods_bytes:
            try:
                item = Image.open(io.BytesIO(goods_bytes)).convert("RGBA")
                max_item_width = int(card_width * 0.84)
                max_item_height = int(card_height * 0.66)
                ratio = min(max_item_width / item.width, max_item_height / item.height)
                item = item.resize((max(1, int(item.width * ratio)), max(1, int(item.height * ratio))), Image.Resampling.LANCZOS)
                x = (card_width - item.width) // 2
                y = 18 + (max_item_height - item.height) // 2
                card_rgba.alpha_composite(item, (x, y))
            except Exception:
                pass

        draw = ImageDraw.Draw(card_rgba)
        name_text = fit_text(draw, name, FONT_NAME, card_width - 34)
        price_text = fit_text(draw, price, FONT_PRICE, card_width - 34)
        draw.text((18, card_height - 72), name_text, fill=(255, 255, 255), font=FONT_NAME)
        draw.text((18, card_height - 38), price_text, fill=(255, 224, 124), font=FONT_PRICE)
        return card_rgba.convert("RGB")


async def bind_qq_account_flow(
    user_id: str,
    config: dict[str, Any],
    send_qr_callback: Callable[[Path], None],
) -> str:
    client = ValorantShopClient(config)
    existing = get_valorant_user_config(user_id)
    if existing:
        if await client.test_config_validity(user_id, existing):
            return f"嗷，你已经绑定过无畏契约账号啦。\n用户ID：{existing.get('userId')}\n现在可以发送：无畏商店"

    http_ctx = await client.generate_qr_code_http()
    if not http_ctx:
        raise ValorantShopError("生成无畏契约 QQ 登录二维码失败")

    session: aiohttp.ClientSession = http_ctx["session"]
    qr_path = Path(http_ctx["filename"])
    try:
        send_qr_callback(qr_path)
        login_data = await client.wait_for_http_login_result(
            session=session,
            ptqrtoken=http_ctx["ptqrtoken"],
            login_sig=http_ctx.get("login_sig", ""),
            login_u1=http_ctx.get("u1_url", client._get_login_u1_url(client._get_login_callback_url())),
            referer_url=http_ctx.get("login_url", client._build_login_url(client._get_login_callback_url())),
            pt_openlogin_data=http_ctx.get("pt_openlogin_data", ""),
            aegis_uid=http_ctx.get("aegis_uid", ""),
            jsver=http_ctx.get("jsver", "28d22679"),
            pt_uistyle=http_ctx.get("pt_uistyle", "35"),
            ptlang=http_ctx.get("ptlang", "2052"),
            timeout=int(config.get("valorant_login_timeout_seconds") or 45),
        )
        if not login_data:
            raise ValorantShopError("登录失败或二维码超时，请重新发送“瓦”再扫一次")

        final_data = await client.get_final_cookies(login_data)
        if not final_data or not final_data.get("userId") or not final_data.get("tid"):
            raise ValorantShopError("获取无畏契约登录信息失败，请稍后重试")

        save_valorant_user_config(user_id, final_data)
        return f"登录成功！用户ID：{final_data['userId']}\n现在可以发送：无畏商店"
    finally:
        await session.close()
        try:
            qr_path.unlink(missing_ok=True)
        except Exception:
            pass


async def build_valorant_shop_image(user_id: str, config: dict[str, Any]) -> tuple[str, Path]:
    user_config = get_valorant_user_config(user_id)
    if not user_config:
        raise ValorantNotBound("还没有绑定无畏契约账号")
    client = ValorantShopClient(config)
    goods_list = await client.get_shop_items_raw(user_id, user_config)
    image_path = await client.build_shop_image(user_id, goods_list)
    caption = f"无畏契约每日商店 · {len(goods_list)} 件"
    return caption, image_path


async def query_valorant_watchlist(user_id: str, config: dict[str, Any]) -> str:
    user_config = get_valorant_user_config(user_id)
    if not user_config:
        raise ValorantNotBound("还没有绑定无畏契约账号")
    watchlist = get_valorant_watchlist(user_id)
    if not watchlist:
        return "你的无畏商店监控列表是空的。可以发：瓦监控 添加 皮肤名"
    client = ValorantShopClient(config)
    goods_list = await client.get_shop_items_raw(user_id, user_config)
    goods_names = [str(goods.get("goods_name") or "") for goods in goods_list]
    matched = []
    for watch_name in watchlist:
        for goods_name in goods_names:
            if watch_name in goods_name or goods_name in watch_name:
                matched.append(goods_name)
    if matched:
        return "嗷，监控命中了：\n" + "\n".join(f"- {name}" for name in matched)
    return "本狼看过啦，今天暂时没有命中你的监控项。"
