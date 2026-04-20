"""
token_cache.py — Shared reCAPTCHA token cache with background refresh.

The token is fetched once via headless Playwright and reused for up to TOKEN_TTL
seconds. A background daemon thread refreshes it automatically.

Usage (in app.py):
    import token_cache
    token_cache.start(settlement_id=5000)   # call once at startup
    token = token_cache.get()               # None if not yet ready
"""

import asyncio
import threading
import time
import os
from typing import Optional

# Token is valid for ~2 hours on nadlan.gov.il; refresh at 75% of that.
TOKEN_TTL = 75 * 60  # 75 minutes

_token: Optional[str] = None
_token_ts: float = 0.0
_lock = threading.Lock()
_refresh_event = threading.Event()   # set to trigger an immediate refresh


def get() -> Optional[str]:
    """Return cached token if still fresh, else None."""
    with _lock:
        if _token and (time.time() - _token_ts) < TOKEN_TTL:
            return _token
    return None


def _set(token: str) -> None:
    global _token, _token_ts
    with _lock:
        _token = token
        _token_ts = time.time()
    print(f"[token_cache] Token refreshed. Valid for ~{TOKEN_TTL//60} min.")


def force_refresh() -> None:
    """Signal the background thread to refresh immediately."""
    _refresh_event.set()


async def _fetch_headless(settlement_id: int) -> Optional[str]:
    """Fetch reCAPTCHA token using headless Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[token_cache] playwright not installed — run: pip install playwright && playwright install chromium")
        return None

    stealth_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1280,800",
    ]

    token_holder: list = []
    try:
        async with async_playwright() as p:
            # Try real Chrome first (better reCAPTCHA score), fall back to bundled Chromium
            try:
                browser = await p.chromium.launch(channel="chrome", headless=True, args=stealth_args)
            except Exception:
                browser = await p.chromium.launch(headless=True, args=stealth_args)

            context = await browser.new_context(
                locale="he-IL",
                timezone_id="Asia/Jerusalem",
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            # Apply stealth patches to hide automation fingerprint
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except ImportError:
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )

            url = f"https://www.nadlan.gov.il/?view=settlement&id={settlement_id}&page=deals"
            print(f"[token_cache] Loading {url} ...")
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)

            for i in range(60):
                await page.wait_for_timeout(1_000)
                token = await page.evaluate("sessionStorage.getItem('recaptchaServerToken')")
                if token:
                    token = token.strip().strip('"')
                    # Skip JSON error responses (e.g. {"ok":false,"error":"..."})
                    if token.startswith("{") or token.startswith("["):
                        if i % 15 == 14:
                            print(f"[token_cache] Still waiting (got error JSON)... ({i+1}s)")
                        continue
                    if token and token not in ("null", "None", "undefined"):
                        print(f"[token_cache] Token obtained after {i+1}s")
                        token_holder.append(token)
                        break
                if i % 15 == 14:
                    print(f"[token_cache] Still waiting... ({i+1}s)")

            await browser.close()
    except Exception as e:
        print(f"[token_cache] Headless fetch error: {e}")

    return token_holder[0] if token_holder else None


def _refresh_loop(settlement_id: int) -> None:
    """Background daemon: refresh token every TOKEN_TTL seconds."""
    while True:
        _refresh_event.clear()
        token = asyncio.run(_fetch_headless(settlement_id))
        if token:
            _set(token)
        else:
            print("[token_cache] Failed to obtain token — will retry in 5 min.")
            time.sleep(300)
            continue
        # Wait until TTL expires or force_refresh() is called
        _refresh_event.wait(timeout=TOKEN_TTL)


def start(settlement_id: int = 5000) -> None:
    """Start the background refresh thread. Call once at app startup."""
    t = threading.Thread(target=_refresh_loop, args=(settlement_id,), daemon=True, name="token-refresh")
    t.start()
    print(f"[token_cache] Background refresh started (settlement_id={settlement_id})")
