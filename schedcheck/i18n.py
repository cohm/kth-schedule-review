"""Languages: Swedish (default) and English.

Every user-facing text exists in both languages. Checks build each finding's
text in both at once (`T(sv=..., en=...)`) from the same data, so the two
cannot drift apart; `model.Issue` refuses a text that lacks a language.
Reports carry both and let the reader switch (HTML), or use the chosen one
(comment drafts, CLI).

Terminology follows docs/GLOSSARY.md. TimeEdit's own Swedish names
(Föreläsning, Övning, F/Ö, ...) are used in both languages.
"""
from __future__ import annotations

import datetime as dt
import os

LANGS = ("sv", "en")
DEFAULT = "sv"


def T(sv: str, en: str) -> dict[str, str]:
    """A text in both languages."""
    return {"sv": sv, "en": en}


def pick(text, lang: str) -> str:
    """The text in `lang` (plain strings are returned as they are)."""
    if isinstance(text, dict):
        return text.get(lang) or text.get(DEFAULT) or next(iter(text.values()), "")
    return text


def env_lang() -> str:
    lang = os.environ.get("SCHEDCHECK_LANG", DEFAULT)
    return lang if lang in LANGS else DEFAULT


def join(items, lang: str) -> str:
    """'a, b och c' / 'a, b and c'."""
    items = [str(x) for x in items]
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + (" och " if lang == "sv" else " and ") + items[-1]


def n_(n: int, sv1: str, svn: str, en1: str, enn: str) -> dict[str, str]:
    """'1 tentamen' / '3 tentamina' etc. in both languages."""
    return T(f"{n} {sv1 if n == 1 else svn}", f"{n} {en1 if n == 1 else enn}")


WEEKDAYS = {"sv": ["mån", "tis", "ons", "tor", "fre", "lör", "sön"],
            "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}


def weekday(d: dt.date, lang: str) -> str:
    return WEEKDAYS[lang][d.weekday()]


def when(start: dt.datetime, end: dt.datetime | None, lang: str) -> str:
    """'mån 2027-02-01 10:00-12:00' / 'Mon 2027-02-01 10:00-12:00'."""
    s = f"{weekday(start.date(), lang)} {start:%Y-%m-%d %H:%M}"
    return s + (f"-{end:%H:%M}" if end else "")


def both(fn) -> dict[str, str]:
    """T built by calling fn(lang) for each language."""
    return {lang: fn(lang) for lang in LANGS}


SEVERITY = {"error": T("Fel", "Error"), "warning": T("Varning", "Warning"),
            "review": T("Granska", "Review"), "info": T("Info", "Info"), "ok": T("OK", "OK")}

KIND = {"ordinary": T("ordinarie tentamen", "exam"), "reexam": T("omtentamen", "re-exam"),
        "partial": T("kontrollskrivning/delexamination", "partial exam")}
