"""Buddy's own browser: see a page, click, type, scroll, log in once and stay logged in.

Separate from web_search (which only returns snippets). Uses Playwright with a
persistent profile at ~/Library/Application Support/Buddy/browser-profile so
logins survive restarts. Prefers the user's installed Google Chrome (no
download needed); falls back to Playwright's Chromium.

Every public function here is exposed to the agent as a tool, so helpers and
imports are underscore-prefixed on purpose (core.agent.execute_tool discovers
tools with dir(module)).

How the model "sees" a page: web_read returns visible text plus a numbered list
of interactive elements, e.g. `[7] button "Sign in"`. It then calls
web_click(7) / web_type(12, "hello"). Refs are re-numbered on every read, so
always act on the most recent read.
"""
import os as _os
import queue as _queue
import threading as _threading
import time as _time

from tools.paths import data_dir as _data_dir

_JOBS = _queue.Queue()
_THREAD = None
_LOCK = _threading.Lock()
_TIMEOUT = 45
_TEXT_LIMIT = 3500

_SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],' +
    '[role=checkbox],[role=tab],[role=menuitem],[role=switch],[role=option],[contenteditable=true],[onclick]';
  document.querySelectorAll('[data-buddy-ref]').forEach(e => e.removeAttribute('data-buddy-ref'));
  const out = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (r.bottom < -2000 || r.top > 6000) continue;
    n += 1; el.setAttribute('data-buddy-ref', n);
    const tag = el.tagName.toLowerCase();
    let label = (el.getAttribute('aria-label') || el.innerText || el.value ||
                 el.getAttribute('placeholder') || el.getAttribute('title') ||
                 el.getAttribute('alt') || el.getAttribute('name') || '').trim().replace(/\s+/g, ' ');
    if (label.length > 70) label = label.slice(0, 70) + '…';
    let kind = tag;
    if (tag === 'input') kind = 'input:' + (el.type || 'text');
    else if (el.getAttribute('role')) kind = el.getAttribute('role');
    let extra = '';
    if (tag === 'a' && el.href) extra = ' -> ' + el.href.slice(0, 80);
    if ((tag === 'input' || tag === 'textarea') && el.value && el.type !== 'password') extra = ' value="' + el.value.slice(0, 40) + '"';
    if (el.type === 'checkbox' || el.type === 'radio') extra = el.checked ? ' [checked]' : ' [unchecked]';
    if (el.disabled) extra += ' [disabled]';
    out.push('[' + n + '] ' + kind + ' "' + label + '"' + extra);
    if (n >= 80) break;
  }
  return { title: document.title, url: location.href, text: document.body ? document.body.innerText : '', elements: out };
}
"""


def _worker():
    """All Playwright calls must happen on one thread; Buddy calls tools from many."""
    state = {"pw": None, "ctx": None, "page": None}
    while True:
        fn, box = _JOBS.get()
        try:
            box["result"] = fn(state)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as text
            box["error"] = exc
        finally:
            box["done"].set()


def _run(fn, timeout=_TIMEOUT):
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD = _threading.Thread(target=_worker, daemon=True, name="buddy-browser")
            _THREAD.start()
    box = {"done": _threading.Event()}
    _JOBS.put((fn, box))
    if not box["done"].wait(timeout):
        raise TimeoutError("The browser took too long to respond.")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _page(state):
    page = state.get("page")
    if page is not None and not page.is_closed():
        return page
    if state["ctx"] is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright isn't installed. Run: pip install playwright")
        state["pw"] = sync_playwright().start()
        profile = str(_data_dir("browser-profile"))
        headless = _os.environ.get("BUDDY_BROWSER_HEADLESS") == "1"
        last = None
        for channel in ("chrome", None):
            try:
                kwargs = {"headless": headless, "viewport": {"width": 1280, "height": 860}}
                if channel:
                    kwargs["channel"] = channel
                state["ctx"] = state["pw"].chromium.launch_persistent_context(profile, **kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if state["ctx"] is None:
            raise RuntimeError(
                "Couldn't start a browser. Install Google Chrome, or run `playwright install chromium`. (%s)" % last
            )
    ctx = state["ctx"]
    state["page"] = ctx.pages[0] if ctx.pages else ctx.new_page()
    return state["page"]


def _settle(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:  # noqa: BLE001 - busy pages never go idle; that's fine
        pass


def _snapshot(page, full=False):
    data = page.evaluate(_SNAPSHOT_JS)
    text = " ".join((data.get("text") or "").split())
    limit = 12000 if full else _TEXT_LIMIT
    if len(text) > limit:
        text = text[:limit] + " …[truncated; web_read(full=True) for more]"
    parts = ["Page: %s\nURL: %s" % (data.get("title") or "(untitled)", data.get("url")), "Text: " + text]
    els = data.get("elements") or []
    parts.append("Interactive elements:\n" + ("\n".join(els) if els else "(none visible)"))
    return "\n\n".join(parts)


def _ref(page, ref):
    loc = page.locator('[data-buddy-ref="%s"]' % int(ref))
    if loc.count() == 0:
        raise RuntimeError("Element [%s] isn't on the page anymore. Call web_read again for fresh numbers." % ref)
    return loc.first


def web_open(url: str) -> str:
    """Opens a URL in Buddy's own browser and returns what is on the page."""
    if "://" not in url:
        url = "https://" + url

    def job(state):
        page = _page(state)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _settle(page)
        return _snapshot(page)

    return _run(job, 60)


def web_read(full: bool = False) -> str:
    """Re-reads the current page: visible text plus numbered clickable elements."""
    def job(state):
        page = _page(state)
        _settle(page)
        return _snapshot(page, full)

    return _run(job)


def web_click(ref: int) -> str:
    """Clicks element [ref] from the latest web_read and returns the updated page."""
    def job(state):
        page = _page(state)
        _ref(page, ref).click(timeout=8000)
        _time.sleep(0.6)
        _settle(page)
        return _snapshot(page)

    return _run(job)


def web_type(ref: int, text: str, submit: bool = False) -> str:
    """Types into input [ref] (replacing its content). submit=True presses Enter afterwards."""
    def job(state):
        page = _page(state)
        el = _ref(page, ref)
        el.fill(text, timeout=8000)
        if submit:
            el.press("Enter")
            _time.sleep(0.8)
            _settle(page)
        return _snapshot(page)

    return _run(job)


def web_select(ref: int, option: str) -> str:
    """Chooses an option (by visible label) in dropdown [ref]."""
    def job(state):
        page = _page(state)
        _ref(page, ref).select_option(label=option, timeout=8000)
        return _snapshot(page)

    return _run(job)


def web_press(key: str) -> str:
    """Presses a key on the page, e.g. Enter, Escape, Tab, ArrowDown, Meta+f."""
    def job(state):
        page = _page(state)
        page.keyboard.press(key)
        _time.sleep(0.4)
        _settle(page)
        return _snapshot(page)

    return _run(job)


def web_scroll(direction: str = "down") -> str:
    """Scrolls the page one screen (down, up, top, bottom) and returns what is now visible."""
    def job(state):
        page = _page(state)
        js = {
            "down": "window.scrollBy(0, window.innerHeight * 0.85)",
            "up": "window.scrollBy(0, -window.innerHeight * 0.85)",
            "top": "window.scrollTo(0, 0)",
            "bottom": "window.scrollTo(0, document.body.scrollHeight)",
        }.get(direction, "window.scrollBy(0, window.innerHeight * 0.85)")
        page.evaluate(js)
        _time.sleep(0.4)
        return _snapshot(page)

    return _run(job)


def web_back() -> str:
    """Goes back one page in Buddy's browser."""
    def job(state):
        page = _page(state)
        page.go_back(timeout=15000)
        _settle(page)
        return _snapshot(page)

    return _run(job)


def web_screenshot(save_path: str = "~/Desktop/buddy_page.png") -> str:
    """Saves a screenshot of the current page in Buddy's browser."""
    path = _os.path.expanduser(save_path)

    def job(state):
        _page(state).screenshot(path=path, full_page=False)
        return "Saved screenshot to %s" % path

    return _run(job)


def web_close() -> str:
    """Closes Buddy's browser (logins stay saved in its profile)."""
    def job(state):
        if state.get("ctx"):
            state["ctx"].close()
        if state.get("pw"):
            state["pw"].stop()
        state.update({"pw": None, "ctx": None, "page": None})
        return "Browser closed. Saved logins are kept."

    return _run(job)
