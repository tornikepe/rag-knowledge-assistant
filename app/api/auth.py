"""OAuth sign-in routes (Google + GitHub).

Flow: ``/api/auth/{provider}/login`` → provider consent → ``/api/auth/{provider}/callback``
→ set a signed session cookie → redirect to the app. ``/api/auth/me`` reports the current
user; ``/api/auth/logout`` clears the session. When a provider isn't configured the login
route bounces back so the UI can fall back to demo login.
"""

from __future__ import annotations

import logging
import re
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core import oauth
from app.core.email import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_COOKIE = "peit_oauth_state"
SESSION_COOKIE = "peit_session"
SIGNUP_CODE_TTL = 600  # seconds a verification code stays valid
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupStartRequest(BaseModel):
    email: str = Field(..., max_length=254)
    name: str = Field(default="", max_length=120)


class SignupVerifyRequest(BaseModel):
    token: str = Field(..., max_length=4000)
    code: str = Field(..., min_length=4, max_length=12)


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _base_url(request: Request, settings) -> str:
    if settings.oauth_redirect_base:
        return settings.oauth_redirect_base.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


def _redirect_uri(request: Request, settings, provider: str) -> str:
    return f"{_base_url(request, settings)}/api/auth/{provider}/callback"


@router.get("/providers")
def providers():
    """Which providers are configured — the frontend uses this to decide real vs demo."""
    s = get_settings()
    return {
        "google": oauth.provider_enabled(s, "google"),
        "github": oauth.provider_enabled(s, "github"),
    }


@router.get("/me")
def me(request: Request):
    s = get_settings()
    data = oauth.verify_session(request.cookies.get(SESSION_COOKIE), s.session_secret)
    if not data:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"email": data.get("email"), "name": data.get("name"), "provider": data.get("provider")}


@router.post("/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


def _set_session_cookie(resp, request: Request, user: dict) -> None:
    s = get_settings()
    token = oauth.sign_session(user, s.session_secret)
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 3600, httponly=True,
        secure=_is_https(request), samesite="lax", path="/",
    )


@router.post("/signup/start")
def signup_start(body: SignupStartRequest):
    """Begin email sign-up: issue a signed token carrying a one-time code, and email it.

    Stateless — the code lives inside the HMAC-signed token, so no server storage is
    needed. When SMTP isn't configured the code is returned for the demo flow.
    """
    s = get_settings()
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "Enter a valid email address."}, status_code=400)

    code = f"{secrets.randbelow(1_000_000):06d}"
    name = body.name.strip() or "Test"
    token = oauth.sign_session(
        {"email": email, "name": name, "code": code, "kind": "signup"},
        s.session_secret,
        ttl=SIGNUP_CODE_TTL,
    )

    delivered = False
    try:
        delivered = send_verification_email(s, email, name, code)
    except Exception as exc:  # noqa: BLE001 — surface the real reason (auth/timeout/etc.)
        logging.getLogger("peit").warning("verification email failed: %r", exc)
        delivered = False

    resp: dict = {"ok": True, "token": token, "delivered": delivered, "email": email}
    if not delivered:
        # Demo fallback: no SMTP configured (or send failed) — surface the code so the
        # user can still complete verification.
        resp["demo_code"] = code
    return resp


@router.post("/signup/verify")
def signup_verify(body: SignupVerifyRequest, request: Request):
    """Check the code against the signed token and, on success, start a session."""
    s = get_settings()
    data = oauth.verify_session(body.token, s.session_secret)
    if not data or data.get("kind") != "signup":
        return JSONResponse(
            {"ok": False, "error": "Your code expired. Please start again."}, status_code=400
        )
    if not secrets.compare_digest(str(data.get("code", "")), body.code.strip()):
        return JSONResponse({"ok": False, "error": "Incorrect code. Try again."}, status_code=400)

    user = {"email": data["email"], "name": data.get("name", "Test"), "provider": "email"}
    resp = JSONResponse({"ok": True, **user})
    _set_session_cookie(resp, request, user)
    return resp


@router.get("/{provider}/login")
def login(provider: str, request: Request):
    s = get_settings()
    if provider not in oauth.PROVIDERS or not oauth.provider_enabled(s, provider):
        return RedirectResponse("/?auth=unconfigured")
    state = secrets.token_urlsafe(24)
    url = oauth.authorize_url(provider, s, _redirect_uri(request, s, provider), state)
    resp = RedirectResponse(url)
    resp.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True,
        secure=_is_https(request), samesite="lax", path="/",
    )
    return resp


@router.get("/{provider}/callback")
async def callback(provider: str, request: Request, code: str | None = None, state: str | None = None):
    s = get_settings()
    if provider not in oauth.PROVIDERS or not oauth.provider_enabled(s, provider):
        return RedirectResponse("/?auth=unconfigured")
    if not code or not state or state != request.cookies.get(STATE_COOKIE):
        return RedirectResponse("/?auth=error")
    try:
        user = await oauth.exchange_and_fetch_user(provider, code, _redirect_uri(request, s, provider), s)
    except Exception:
        return RedirectResponse("/?auth=error")

    token = oauth.sign_session(
        {"email": user["email"], "name": user["name"], "provider": provider}, s.session_secret
    )
    resp = RedirectResponse("/?auth=ok")
    resp.delete_cookie(STATE_COOKIE, path="/")
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=7 * 24 * 3600, httponly=True,
        secure=_is_https(request), samesite="lax", path="/",
    )
    return resp
