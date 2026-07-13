"""OAuth sign-in routes (Google + GitHub).

Flow: ``/api/auth/{provider}/login`` → provider consent → ``/api/auth/{provider}/callback``
→ set a signed session cookie → redirect to the app. ``/api/auth/me`` reports the current
user; ``/api/auth/logout`` clears the session. When a provider isn't configured the login
route bounces back so the UI can fall back to demo login.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import get_settings
from app.core import oauth

router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_COOKIE = "peit_oauth_state"
SESSION_COOKIE = "peit_session"


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
