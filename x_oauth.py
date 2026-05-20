from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
X_AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_ME_URL = "https://api.x.com/2/users/me"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"
DEFAULT_SCOPES = "tweet.read users.read follows.read offline.access"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def save_config(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def parse_callback(value: str) -> tuple[str, str]:
    text = value.strip()
    if not text:
        raise ValueError("Callback URL or code is empty.")
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        query = parse_qs(parsed.query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        error = (query.get("error") or [""])[0]
        if error:
            raise RuntimeError(f"X authorization returned error: {error}")
        if not code:
            raise ValueError("The pasted callback URL does not contain code=...")
        return code, state
    return text, ""


def exchange_code(
    client_id: str,
    code: str,
    verifier: str,
    redirect_uri: str,
    client_secret: str = "",
) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    auth = None
    if client_secret:
        auth = (client_id, client_secret)
    else:
        data["client_id"] = client_id

    response = requests.post(
        X_TOKEN_URL,
        data=data,
        auth=auth,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code in {400, 401, 403}:
        raise RuntimeError(f"X token exchange failed: {response.text[:800]}")
    response.raise_for_status()
    token_data = response.json()
    if not token_data.get("access_token"):
        raise RuntimeError(f"X token exchange returned no access token: {token_data!r}")
    return token_data


def read_me(access_token: str) -> dict:
    response = requests.get(
        X_ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"user.fields": "username,name,profile_image_url"},
        timeout=30,
    )
    if response.status_code in {400, 401, 403}:
        raise RuntimeError(f"Could not read X account info: {response.text[:800]}")
    response.raise_for_status()
    data = response.json()
    user = data.get("data") if isinstance(data.get("data"), dict) else {}
    if not user.get("id"):
        raise RuntimeError(f"Could not read X account id: {data!r}")
    return user


def authorize(config_path: Path) -> int:
    config = load_config(config_path)
    client_id = str(config.get("x_client_id") or "").strip()
    if not client_id:
        client_id = input("Paste X OAuth 2.0 Client ID: ").strip()
    if not client_id:
        raise ValueError("Client ID is required.")

    client_secret = str(config.get("x_client_secret") or "").strip()
    redirect_uri = str(config.get("x_oauth_redirect_uri") or DEFAULT_REDIRECT_URI).strip()
    scopes = str(config.get("x_oauth_scopes") or DEFAULT_SCOPES).strip()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)

    auth_url = X_AUTHORIZE_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )

    print("\nOpen this URL in your browser and authorize the app:\n")
    print(auth_url)
    print(
        "\nAfter authorization, the browser may fail to open 127.0.0.1. "
        "That is OK. Copy the full address from the browser address bar and paste it here."
    )
    callback = input("\nPaste redirected URL: ").strip()
    code, returned_state = parse_callback(callback)
    if returned_state and returned_state != state:
        raise RuntimeError("State mismatch. Please run the authorization again.")

    token_data = exchange_code(
        client_id=client_id,
        code=code,
        verifier=verifier,
        redirect_uri=redirect_uri,
        client_secret=client_secret,
    )
    access_token = str(token_data["access_token"])
    user = read_me(access_token)

    config["x_client_id"] = client_id
    config["x_oauth_redirect_uri"] = redirect_uri
    config["x_oauth_scopes"] = scopes
    config["x_user_access_token"] = access_token
    if token_data.get("refresh_token"):
        config["x_user_refresh_token"] = str(token_data["refresh_token"])
    if token_data.get("expires_in"):
        config["x_user_token_expires_at"] = int(time.time()) + int(token_data["expires_in"]) - 90
    config["x_user_id"] = str(user.get("id") or "")
    config["x_username"] = str(user.get("username") or "")
    config["x_display_name"] = str(user.get("name") or "")
    config.setdefault("x_timeline_command", "X日常")
    config.setdefault("x_timeline_limit", 3)
    config.setdefault("x_timeline_fetch_limit", 10)

    save_config(config_path, config)
    print(f"\nSaved X account authorization for @{config['x_username']} to {config_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize an X account for Following timeline reads.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args()
    return authorize(Path(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
