"""Strava OAuth client — fully generic, multi-user, session-based."""
import time

import requests
import streamlit as st

STRAVA_BASE = "https://www.strava.com"
API_BASE    = f"{STRAVA_BASE}/api/v3"
SCOPE       = "read,activity:read_all"


# ── Credential resolution: secrets.toml → session_state → empty ──────────────

def _get(key: str) -> str:
    """Read config from st.secrets first, then session_state (manual setup)."""
    try:
        v = st.secrets.get(key, "")
        if v:
            return v
    except Exception:
        pass
    return st.session_state.get(f"cfg_{key}", "")


def client_id()     -> str: return _get("STRAVA_CLIENT_ID")
def client_secret() -> str: return _get("STRAVA_CLIENT_SECRET")
def redirect_uri()  -> str: return _get("STRAVA_REDIRECT_URI")


def is_configured() -> bool:
    """True if client_id and client_secret are available."""
    return bool(client_id() and client_secret() and redirect_uri())


def save_config(cid: str, csecret: str, ruri: str) -> None:
    """Persist credentials in session state (no secrets.toml needed)."""
    st.session_state["cfg_STRAVA_CLIENT_ID"]     = cid.strip()
    st.session_state["cfg_STRAVA_CLIENT_SECRET"]  = csecret.strip()
    st.session_state["cfg_STRAVA_REDIRECT_URI"]   = ruri.strip()


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def auth_url() -> str:
    return (
        f"{STRAVA_BASE}/oauth/authorize"
        f"?client_id={client_id()}"
        f"&redirect_uri={redirect_uri()}"
        f"&response_type=code"
        f"&scope={SCOPE}"
        f"&approval_prompt=auto"
    )


def exchange_code(code: str) -> dict:
    resp = requests.post(f"{STRAVA_BASE}/oauth/token", data={
        "client_id":     client_id(),
        "client_secret": client_secret(),
        "code":          code,
        "grant_type":    "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def _refresh_if_needed() -> str | None:
    tokens = st.session_state.get("strava_tokens")
    if not tokens:
        return None
    if tokens["expires_at"] < time.time() + 300:
        resp = requests.post(f"{STRAVA_BASE}/oauth/token", data={
            "client_id":     client_id(),
            "client_secret": client_secret(),
            "grant_type":    "refresh_token",
            "refresh_token": tokens["refresh_token"],
        })
        resp.raise_for_status()
        data = resp.json()
        tokens.update({
            "access_token":  data["access_token"],
            "refresh_token": data.get("refresh_token", tokens["refresh_token"]),
            "expires_at":    data["expires_at"],
        })
        st.session_state["strava_tokens"] = tokens
    return tokens["access_token"]


# ── Session helpers ───────────────────────────────────────────────────────────

def is_authenticated() -> bool:
    return "strava_tokens" in st.session_state


def save_tokens(token_data: dict) -> None:
    st.session_state["strava_tokens"] = {
        "access_token":  token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at":    token_data["expires_at"],
    }
    if "athlete" in token_data:
        st.session_state["strava_athlete"] = token_data["athlete"]


def logout() -> None:
    for key in ("strava_tokens", "strava_athlete"):
        st.session_state.pop(key, None)
    st.cache_data.clear()


def current_token_key() -> str:
    return st.session_state.get("strava_tokens", {}).get("access_token", "")[:16]


# ── API calls ─────────────────────────────────────────────────────────────────

def _api_get(path: str, params: dict | None = None) -> dict | list:
    token = _refresh_if_needed()
    if not token:
        raise RuntimeError("Non authentifié")
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete(_tok: str) -> dict:
    if "strava_athlete" in st.session_state:
        return st.session_state["strava_athlete"]
    return _api_get("/athlete")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_activities(_tok: str, n: int = 60) -> list[dict]:
    activities, page = [], 1
    while len(activities) < n:
        batch = _api_get("/athlete/activities", {
            "per_page": min(n - len(activities), 30),
            "page": page,
        })
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities[:n]
