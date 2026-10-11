"""Browser control.

Opens pages with the system's default browser and drives whichever browser window
is in front using standard keyboard shortcuts (so it works with Chrome, Edge,
Firefox, ... without any extension)."""
from __future__ import annotations

import re
import urllib.parse
import webbrowser

from core.actions import MOD
from voice.commands import normalize_site

SEARCH_URLS = {
    "google": "https://www.google.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
}
KNOWN_SITES = {
    "youtube": "youtube.com", "google": "google.com", "gmail": "mail.google.com",
    "github": "github.com", "wikipedia": "wikipedia.org", "facebook": "facebook.com",
    "twitter": "twitter.com", "reddit": "reddit.com", "amazon": "amazon.com",
    "netflix": "netflix.com", "linkedin": "linkedin.com", "maps": "maps.google.com",
    "google maps": "maps.google.com", "instagram": "instagram.com", "whatsapp": "web.whatsapp.com",
    "chatgpt": "chatgpt.com", "claude": "claude.ai", "spotify": "open.spotify.com", "outlook": "outlook.live.com",
    "stackoverflow": "stackoverflow.com", "stack overflow": "stackoverflow.com", "drive": "drive.google.com",
    "google drive": "drive.google.com", "translate": "translate.google.com", "news": "news.google.com",
    "x": "x.com", "flipkart": "flipkart.com", "hotstar": "hotstar.com", "prime video": "primevideo.com",
}
YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query={q}"
RISKY = {"close_tab", "close_window", "go_to"}      # ask before doing these (if enabled)


class BrowserController:
    def __init__(self, actions, status, log, get_cfg):
        self.actions = actions
        self.status = status
        self.log = log
        self.get_cfg = get_cfg
        self.active = False

    def start(self) -> None:
        try:
            browser = webbrowser.get()
            name = getattr(browser, "name", "default browser")
            self.active = True
            self.status.set("browser", "running", f"Ready - default browser ({name})")
        except webbrowser.Error:
            self.active = False
            self.status.set("browser", "error", "No default web browser found")
            self.log.error("No default web browser was found on this computer.")

    def stop(self) -> None:
        self.active = False
        self.status.set("browser", "stopped", "")

    # ---- helpers ----------------------------------------------------
    @staticmethod
    def _known(spoken: str) -> str:
        word = re.sub(r"^(?:the|my) ", "", spoken.strip())
        return KNOWN_SITES.get(word) or KNOWN_SITES.get(word.replace(" ", ""), "")

    def is_known_site(self, spoken: str) -> bool:
        """Well-known sites (YouTube, Gmail, ...) open without asking first."""
        return bool(self._known(spoken)) or normalize_site(spoken) in KNOWN_SITES.values()

    def resolve_target(self, spoken: str) -> str:
        """Spoken site name -> https URL. Unknown plain words become a web search (safer)."""
        site = normalize_site(spoken)
        if not site:
            word = spoken.strip()
            if self._known(word):
                site = self._known(word)
            elif " " not in word and word.replace("-", "").isalnum() and word in KNOWN_SITES.values():
                site = word
            else:
                return self.search_url(spoken)
        return "https://" + site

    def search_url(self, query: str) -> str:
        engine = self.get_cfg()["browser"]["search_engine"]
        return SEARCH_URLS.get(engine, SEARCH_URLS["google"]).format(q=urllib.parse.quote_plus(query))

    def _open_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Only http(s) links are allowed")
        webbrowser.open_new_tab(url)

    # ---- actions ------------------------------------------------------
    def perform(self, action: str, **kw) -> str:
        """Run a browser action; returns a short description for the log."""
        a = self.actions
        if action == "open":
            self._open_url(self.get_cfg()["browser"]["home_page"]); return "Opened browser"
        if action == "home":
            self._open_url(self.get_cfg()["browser"]["home_page"]); return "Opened home page"
        if action == "go_to":
            url = self.resolve_target(kw["target"]); self._open_url(url); return f"Opened {url}"
        if action == "search":
            self._open_url(self.search_url(kw["query"])); return f"Searched for '{kw['query']}'"
        if action == "youtube":
            self._open_url(YOUTUBE_SEARCH.format(q=urllib.parse.quote_plus(kw["query"])))
            return f"Searched YouTube for '{kw['query']}'"
        if action == "tab":
            n = int(kw["number"])
            a.hotkey(MOD, str(n if 1 <= n <= 8 else 9)); return f"Tab {n}"
        table = {
            "back": ("alt", "left") if MOD != "command" else ("command", "["),
            "forward": ("alt", "right") if MOD != "command" else ("command", "]"),
            "refresh": (MOD, "r"),
            "new_tab": (MOD, "t"),
            "close_tab": (MOD, "w"),
            "next_tab": (MOD, "tab"),
            "prev_tab": (MOD, "shift", "tab"),
            "close_window": ("alt", "f4") if MOD != "command" else ("command", "shift", "w"),
            "address_bar": (MOD, "l"),
            "zoom_in": (MOD, "="),
            "zoom_out": (MOD, "-"),
            "zoom_reset": (MOD, "0"),
            "reopen_tab": (MOD, "shift", "t"),
            "bookmark": (MOD, "d"),
        }
        if action not in table:
            raise ValueError(f"Unknown browser action '{action}'")
        a.hotkey(*table[action])
        return action.replace("_", " ").capitalize()
