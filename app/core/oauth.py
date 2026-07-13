"""Real OAuth 2.0 (Authorization Code flow) for Google and GitHub.

Deliberately dependency-light: a small HMAC-signed token is the session cookie, and
``httpx`` performs the token exchange + userinfo calls. A provider is only "enabled"
when its client id + secret are configured — otherwise the frontend falls back to a
demo login, so the app never breaks while credentials aren't set up yet.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx

from app.config import Settings

PROVIDERS: dict[str, dict] = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "emails": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
    },
}


def _creds(settings: Settings, provider: str) -> tuple[str | None, str | None]:
    if provider == "google":
        return settings.google_client_id, settings.google_client_secret
    if provider == "github":
        return settings.github_client_id, settings.github_client_secret
    return None, None


def provider_enabled(settings: Settings, provider: str) -> bool:
    cid, secret = _creds(settings, provider)
    return bool(cid and secret)


def authorize_url(provider: str, settings: Settings, redirect_uri: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    cid, _ = _creds(settings, provider)
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "response_type": "code",
    }
    if provider == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    return f"{cfg['authorize']}?{urlencode(params)}"


async def exchange_and_fetch_user(
    provider: str, code: str, redirect_uri: str, settings: Settings
) -> dict:
    """Exchange the auth code for a token and return ``{email, name, provider}``."""
    cfg = PROVIDERS[provider]
    cid, secret = _creds(settings, provider)
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            cfg["token"],
            data={
                "client_id": cid,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("No access token returned by provider")

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        info = (await client.get(cfg["userinfo"], headers=headers)).json()

        if provider == "google":
            email = info.get("email")
            name = info.get("name") or (email.split("@")[0] if email else "User")
        else:  # github
            name = info.get("name") or info.get("login") or "User"
            email = info.get("email")
            if not email:  # email may be private — fetch the verified primary
                emails = (await client.get(cfg["emails"], headers=headers)).json()
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")),
                    emails[0] if emails else None,
                )
                email = primary["email"] if primary else f"{info.get('login', 'user')}@users.noreply.github.com"

    if not email:
        raise ValueError("Could not determine the account email")
    return {"email": email, "name": name, "provider": provider}


# --- session token (compact HMAC-signed, dependency-free) -------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_session(payload: dict, secret: str, ttl: int = 7 * 24 * 3600) -> str:
    body = {**payload, "exp": int(time.time()) + ttl}
    raw = _b64e(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify_session(token: str | None, secret: str) -> dict | None:
    if not token or "." not in token:
        return None
    try:
        raw, sig = token.split(".", 1)
        expected = _b64e(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64d(raw))
        if int(data.get("exp", 0)) < time.time():
            return None
        return data
    except Exception:
        return None
