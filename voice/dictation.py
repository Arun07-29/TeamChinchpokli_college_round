"""Turns recognised dictation into typed text (spoken punctuation, capitalisation, spacing)."""
from __future__ import annotations

PUNCT = {
    "comma": ",", "period": ".", "full stop": ".", "question mark": "?", "exclamation mark": "!",
    "exclamation point": "!", "colon": ":", "semicolon": ";", "dash": " - ", "hyphen": "-",
    "open bracket": "(", "close bracket": ")", "new line": "\n", "new paragraph": "\n\n",
}
GLUE_LEFT = {",", ".", "?", "!", ":", ";", ")"}          # no space before these
NEWLINES = {"\n", "\n\n"}
_PHRASES = sorted(PUNCT, key=lambda p: -len(p.split()))


class DictationFormatter:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.capitalize_next = True
        self.first = True
        self.last_typed = ""

    def format(self, text: str, punctuation: bool = True, capitalize: bool = True) -> str:
        words = text.strip().split()
        tokens: list[tuple[str, str]] = []              # ("w", word) | ("p", symbol)
        i = 0
        while i < len(words):
            hit = None
            if punctuation:
                for phrase in _PHRASES:
                    n = len(phrase.split())
                    if " ".join(words[i:i + n]).lower() == phrase:
                        hit = (phrase, n)
                        break
            if hit:
                tokens.append(("p", PUNCT[hit[0]]))
                i += hit[1]
            else:
                tokens.append(("w", words[i]))
                i += 1

        out, glue_next = "", False
        for kind, tok in tokens:
            if kind == "w":
                if out and not out.endswith(("\n", " ")) and not glue_next:
                    out += " "
                out += tok
                glue_next = False
            elif tok in GLUE_LEFT or tok in NEWLINES or tok == " - ":
                out += tok
                glue_next = False
            elif tok == "(":
                out += (" " if out and not out.endswith(("\n", " ")) else "") + tok
                glue_next = True
            else:                                       # hyphen
                out += tok
                glue_next = True
        if not out:
            return ""
        if capitalize:
            out = self._capitalize(out)
        starts_glued = out[0] in GLUE_LEFT or out[0] == "\n"
        if not self.first and not starts_glued and not self.last_typed.endswith(("\n", " ")):
            out = " " + out
        self.first = False
        self.last_typed = out
        tail = out.rstrip(" ")
        self.capitalize_next = bool(tail) and tail[-1] in ".?!\n"
        return out

    def _capitalize(self, s: str) -> str:
        chars, cap = list(s), self.capitalize_next
        for idx, ch in enumerate(chars):
            if cap and ch.isalpha():
                chars[idx] = ch.upper()
                cap = False
            elif ch in ".?!\n":
                cap = True
            elif ch.isalnum():
                cap = False
        return "".join(chars)

    def undo_length(self) -> int:
        n = len(self.last_typed)
        self.last_typed = ""
        return n
