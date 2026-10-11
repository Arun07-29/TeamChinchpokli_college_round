"""Live 'is it running?' list for every feature (compact: one line per feature)."""
import customtkinter as ctk

from core.status import FEATURES
from ui import theme


class StatusPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER)
        self.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(self, text="System status", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=theme.TEXT).grid(row=0, column=0, columnspan=4, sticky="w", padx=18, pady=(12, 4))
        self._rows = {}
        self._cache = {}
        for i, (key, label) in enumerate(FEATURES, start=1):
            dot = ctk.CTkLabel(self, text="●", font=ctk.CTkFont(size=14), text_color=theme.NEUTRAL, width=18)
            dot.grid(row=i, column=0, padx=(16, 4), pady=1, sticky="w")
            name = ctk.CTkLabel(self, text=label, anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
                                text_color=theme.TEXT)
            name.grid(row=i, column=1, sticky="w", pady=1)
            detail = ctk.CTkLabel(self, text="", anchor="w", justify="left", font=ctk.CTkFont(size=11),
                                  text_color=theme.MUTED, wraplength=210)
            detail.grid(row=i, column=2, sticky="w", padx=(10, 4), pady=1)
            state = ctk.CTkLabel(self, text="Stopped", font=ctk.CTkFont(size=12, weight="bold"),
                                 text_color=theme.NEUTRAL, anchor="e", width=64)
            state.grid(row=i, column=3, padx=(4, 16), pady=1, sticky="e")
            self._rows[key] = (dot, name, detail, state)
        ctk.CTkLabel(self, text="", height=4).grid(row=len(FEATURES) + 1, column=0)

    def update_status(self, features: dict) -> None:
        for key, (state, detail) in features.items():
            if self._cache.get(key) == (state, detail):
                continue
            self._cache[key] = (state, detail)
            color, label = theme.STATE_STYLE.get(state, (theme.NEUTRAL, state))
            dot, _, det, st = self._rows[key]
            dot.configure(text_color=color)
            st.configure(text=label, text_color=color)
            det.configure(text=detail, text_color=theme.BAD if state == "error" else theme.MUTED)
