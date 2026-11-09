"""Grounding guardrail: a tool may only save details the caller actually said.

Smaller models sometimes call tools with invented details: on 2026-11-08, gpt-oss-20b answered
"Yeah, sure" with save_origin_destination(origin_city="Los Angeles") 6 times out of 6. So every
city, make, model and year a tool receives is checked against everything the caller has said
(the user messages so far), tolerating speech-to-text typos ("Bostin"), spoken forms
("four runner", "twenty twenty") and common nicknames ("SF", "Chevy").

The check is deliberately lenient (a false "not said" annoys the caller more than a rare miss):
it catches values that appear nowhere in what the caller said.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from mia.geo import canonicalize_state
from mia.vehicles import MAKE_ALIASES, VEHICLE_TYPE_ALIASES, normalize, normalize_vehicle_type

MATCH_CUTOFF = 0.75

CITY_ALIASES = {
    "sf": "san francisco",
    "san fran": "san francisco",
    "frisco": "san francisco",
    "la": "los angeles",
    "nyc": "new york",
    "new york city": "new york",
    "philly": "philadelphia",
    "vegas": "las vegas",
    "dc": "washington",
    "nola": "new orleans",
    "chi town": "chicago",
    "atl": "atlanta",
    "slc": "salt lake city",
    "okc": "oklahoma city",
    "kc": "kansas city",
}

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_TEENS = [
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _two_digits(n: int) -> list[str]:
    """Ways to say 0-99 as the second half of a year: 5 -> ["oh five"], 20 -> ["twenty"]."""
    if n == 0:
        return ["hundred"]
    if n < 10:
        return [f"oh {_ONES[n]}"]
    if n < 20:
        return [_TEENS[n - 10]]
    tens, ones = divmod(n, 10)
    return [f"{_TENS[tens]} {_ONES[ones]}".strip()]


def spoken_years(year: int) -> list[str]:
    """2020 -> ['2020', '20', 'twenty twenty', 'two thousand twenty', ...]."""
    out = [str(year), f"{year % 100:02d}"]
    hi, lo = divmod(year, 100)
    hi_words = {19: "nineteen", 20: "twenty"}.get(hi)
    if hi_words:
        out += [f"{hi_words} {w}" for w in _two_digits(lo)]
    if year >= 2000:
        rest = year - 2000
        small = (
            _ONES[rest]
            if rest < 10
            else _TEENS[rest - 10]
            if rest < 20
            else f"{_TENS[rest // 10]} {_ONES[rest % 10]}".strip()
        )
        out += [f"two thousand {small}".strip(), f"two thousand and {small}".strip()]
    out += _two_digits(lo)  # "ninety eight"
    return out


def _windows(words: list[str], max_len: int = 4) -> list[str]:
    return [" ".join(words[i : i + n]) for n in range(1, max_len + 1) for i in range(len(words))]


def _fuzzy_in(value: str, said: str, cutoff: float = MATCH_CUTOFF) -> bool:
    """Does ``value`` appear in ``said`` (both normalized), allowing typos?"""
    v = normalize(value)
    if not v:
        return True
    # Short names need a closer match ("car" is 0.75 similar to "camry"), and a typo never
    # changes the length by much.
    min_ratio = max(cutoff, 0.8) if len(v) <= 6 else cutoff
    max_len_diff = max(1, len(v) // 4)
    words = _words(said)
    for window in _windows(words):
        w = normalize(window)
        if w == v:
            return True
        if (
            len(v) >= 4
            and abs(len(w) - len(v)) <= max_len_diff
            and SequenceMatcher(None, v, w).ratio() >= min_ratio
        ):
            return True
    return False


def city_said(city: str, said: str) -> bool:
    if _fuzzy_in(city, said):
        return True
    target = " ".join(_words(city))
    said_windows = set(_windows(_words(said), 3))
    return any(alias in said_windows and full == target for alias, full in CITY_ALIASES.items())


def state_said(state: str, said: str) -> bool:
    code = canonicalize_state(state)
    if not code:
        return _fuzzy_in(state, said)
    return any(canonicalize_state(w) == code for w in _windows(_words(said), 3))


def make_said(make: str, said: str) -> bool:
    if _fuzzy_in(make, said):
        return True
    said_windows = set(_windows(_words(said), 2))
    return any(
        alias in said_windows and normalize(full) == normalize(make)
        for alias, full in MAKE_ALIASES.items()
    )


def model_said(model: str, said: str) -> bool:
    return _fuzzy_in(model, said)


def year_said(year: int | str, said: str) -> bool:
    try:
        y = int(str(year).strip().lstrip("'"))
    except ValueError:
        return False
    if y < 100:
        return _fuzzy_in(str(y), said)
    text = " ".join(_words(said))
    padded = f" {text} "
    return any(f" {form} " in padded for form in spoken_years(y))


def vehicle_type_said(vehicle_type: str, said: str) -> bool:
    kind = normalize_vehicle_type(vehicle_type)
    if kind is None:
        return _fuzzy_in(vehicle_type, said)
    return any(
        normalize_vehicle_type(w) == kind
        for w in _windows(_words(said), 3)
        if w in VEHICLE_TYPE_ALIASES or w.replace(" ", "") == kind
    )


_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_COUNT_RE = re.compile(
    r"\b(both|two|three|four|five|six|seven|eight|[2-8])\s+(?:of\s+(?:my|our|the)\s+)?"
    r"(?:\w+\s+)?(cars|vehicles|autos|trucks|suvs|vans)\b"
)


def vehicle_count_said(said: str) -> int | None:
    """'I need to send 2 cars' / 'three vehicles' / 'both cars' -> the number, else None.

    Counting is too important to leave to the model (gpt-oss-20b often doesn't pass it), and a
    caller saying it is unambiguous. The latest mention wins ("two cars... actually three cars").
    """
    found = None
    for m in _COUNT_RE.finditer(said.lower()):
        word = m.group(1)
        found = 2 if word == "both" else _COUNTS.get(word) or int(word)
    return found


_YES = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "ya",
    "aha",
    "uh huh",
    "mhm",
    "sure",
    "correct",
    "right",
    "exactly",
    "ok",
    "okay",
    "perfect",
    "absolutely",
    "definitely",
    "of course",
    "sounds good",
    "go ahead",
    "that s it",
    "that s right",
    "that is right",
    "that s correct",
    "all good",
)
_NO = ("no", "nope", "not", "wrong", "actually", "wait", "change", "incorrect")


def is_confirmation(text: str) -> bool:
    """Is this caller message a yes ("Yep", "Correct", "aha, go ahead")? A "no" or a
    correction ("yes but actually it's 2021") is not."""
    words = _words(text.replace("'", " "))
    joined = f" {' '.join(words)} "
    if any(f" {w} " in joined for w in _NO):
        return False
    return any(f" {phrase} " in joined for phrase in _YES)
