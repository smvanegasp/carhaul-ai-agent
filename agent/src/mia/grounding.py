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
from typing import Any

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


def _windows(words: list[str], max_len: int = 5) -> list[str]:
    return [" ".join(words[i : i + n]) for n in range(1, max_len + 1) for i in range(len(words))]


def _fuzzy_in(value: str, said: str, cutoff: float = MATCH_CUTOFF) -> bool:
    """Does ``value`` appear in ``said`` (both normalized), allowing typos?"""
    v = normalize(value)
    if not v:
        # Nothing to match: "?" or "" was never said (real-API run, 2026-11-11: "Yeah, sure"
        # -> save_origin_destination(origin_city="?") passed, then "Which state is that in?").
        return False
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


# Makes callers name most; enough to notice two cars in one sentence (makes_named).
COMMON_MAKES = (
    "acura",
    "audi",
    "bmw",
    "buick",
    "cadillac",
    "chevrolet",
    "chrysler",
    "dodge",
    "ford",
    "gmc",
    "honda",
    "hyundai",
    "infiniti",
    "jeep",
    "kia",
    "lexus",
    "lincoln",
    "mazda",
    "mercedes-benz",
    "mitsubishi",
    "nissan",
    "porsche",
    "ram",
    "subaru",
    "tesla",
    "toyota",
    "volkswagen",
    "volvo",
)
_CORRECTION = re.compile(r"\b(?:no|not|actually|instead|sorry|i mean|rather)\b", re.IGNORECASE)


def makes_named(text: str) -> int:
    """How many cars one message names by make ("a 2022 Toyota RAV4 and a 2017 Honda Civic"
    -> 2). A correction is one car ("a Honda, not a Toyota", "I mean the Toyota, the Honda's
    sold" -> 1), but a corrected year isn't ("a twenty ten... no sorry, twenty twenty-two RAV4
    and a 2017 Civic" -> 2). Stage 7 simulation: two cars in one sentence, the model saved one,
    and nothing in code knew about the second."""
    names = {name for _, _, name in _make_hits(text)}
    if len(names) < 2:
        return len(names)
    words = " ".join(_words(text.replace("-", " ")))
    about_makes = _YEAR_FIX.sub(" ", words)  # "no sorry twenty twenty two": about the year
    # A correction word only counts right before a make ("not a Toyota", "I mean the
    # Toyota"): "I've actually got two vehicles" is two cars (stage 7 simulation).
    makes = "|".join(re.escape(m.replace("-", " ")) for m in (*COMMON_MAKES, *MAKE_ALIASES))
    fixes_make = re.search(
        rf"\b(?:no|not|actually|instead|sorry|i mean|rather)\b(?:\s+\w+){{0,2}}?\s+(?:{makes})\b",
        about_makes,
    )
    return 1 if fixes_make else len(names)


_YEAR_FIX = re.compile(
    r"\b(?:no|not|actually|sorry|i mean|rather)(?:\s+(?:no|sorry|wait|i mean|actually))*\s+"
    r"(?:it s\s+|a\s+)?(?:nineteen|twenty|two thousand|19\d\d|20\d\d)\b"
)


def _make_hits(text: str) -> list[tuple[int, int, str]]:
    """(start, end, display name) of each make named, in order, in the normalized words."""
    words = " ".join(_words(text.replace("-", " ")))
    hits: list[tuple[int, int, str]] = []
    for m in COMMON_MAKES:
        for found in re.finditer(rf"\b{m.replace('-', ' ')}\b", words):
            hits.append((found.start(), found.end(), _MAKE_NAMES.get(m, m.title())))
    for alias, full in MAKE_ALIASES.items():
        for found in re.finditer(rf"\b{alias}\b", words):
            hits.append((found.start(), found.end(), full))
    return sorted(hits)


_MAKE_NAMES = {"bmw": "BMW", "gmc": "GMC", "ram": "Ram", "mercedes-benz": "Mercedes-Benz"}


def makes_in(text: str) -> list[str]:
    """The makes one message names, as display names ("Honda", "Chevrolet"), in order."""
    out: list[str] = []
    for _, _, name in _make_hits(text):
        if name not in out:
            out.append(name)
    return out


def vehicle_details_in(text: str) -> dict[str, Any]:
    """The year and make in one message ("It's from Miami to Chicago. It's a twenty twenty
    Honda" -> {"year": 2020, "make": "Honda"}), so Mia never asks for them again. A make only
    when exactly one is named (two makes are two cars); the year a caller corrected to wins."""
    out: dict[str, Any] = {}
    if makes_named(text) >= 2:
        return out  # two cars: the count is set instead (agent._note_partial_vehicle)
    years = _years_in(text)
    if len({corrected_year(y, text) for _, _, y in years}) >= 2:
        return out  # "a 2025 Civic and a 2020 4Runner": two cars, not one partial
    if years:
        out["year"] = corrected_year(years[0][2], text)
    makes = makes_in(text)
    if len(makes) == 1:
        out["make"] = makes[0]
    return out


def model_named(model: str, make: str, said: str) -> bool:
    """This exact model name right after the make in the caller's words ("Honda Civic",
    "Honda, the Civic"): used when code fills in a model the LLM left out. Next to the make
    and exact, so "it doesn't fit" is never a Honda Fit."""
    v, m = normalize(model), normalize(make)
    words = _words(said)
    for i in range(len(words)):
        if normalize(words[i]) != m and normalize(" ".join(words[i : i + 2])) != m:
            continue
        start = i + (1 if normalize(words[i]) == m else 2)
        after = [w for w in words[start : start + 6] if w not in ("the", "a", "an", "it", "s")]
        if any(normalize(" ".join(after[:n])) == v for n in range(1, 5)):
            return True
    return False


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
    # A bare "car" is how everyone says it ("I'm shipping my car"), not a body type: in the
    # stage 7 simulations it grounded "sedan" for a caller who never said one.
    return any(
        normalize_vehicle_type(w) == kind
        for w in _windows(_words(said), 3)
        if w not in _GENERIC and (w in VEHICLE_TYPE_ALIASES or w.replace(" ", "") == kind)
    )


_GENERIC = {"car", "vehicle", "auto"}
_UNSURE = re.compile(
    r"\b(?:not (?:exactly |really |totally |quite )?sure|unsure|don'?t know|do not know|"
    r"no idea|can'?t remember|cannot remember|"
    r"don'?t remember|forgot|not certain|no clue)\b",
    re.IGNORECASE,
)
_OFFERED_TYPES = re.compile(r"\bsedan\b.*\b(?:suv|pickup|pick-up)\b", re.IGNORECASE)


def unsure(text: str) -> bool:
    """ "I'm not sure", "I don't know the model"."""
    return bool(_UNSURE.search(text))


def offered_types(mia_said: str) -> bool:
    """Did Mia just ask whether it's a sedan, SUV or pickup?"""
    return bool(_OFFERED_TYPES.search(mia_said))


_COUNTS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_COUNT_RE = re.compile(
    r"\b(both|couple|two|three|four|five|six|seven|eight|[2-8])\s+(?:of\s+)?"
    r"(?:(?:my|our|the)\s+)?"
    r"(?:\w+\s+)?(cars|vehicles|autos|trucks|suvs|vans|rides)\b"
)


def vehicle_count_said(said: str) -> int | None:
    """'I need to send 2 cars' / 'three vehicles' / 'both cars' -> the number, else None.

    Counting is too important to leave to the model (gpt-oss-20b often doesn't pass it), and a
    caller saying it is unambiguous. The latest mention wins ("two cars... actually three cars").
    """
    found = None
    for m in _COUNT_RE.finditer(said.lower()):
        word = m.group(1)
        found = 2 if word in ("both", "couple") else _COUNTS.get(word) or int(word)
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


def is_short_yes(text: str) -> bool:
    """A yes that's only a yes ("Sure", "Yes, that's correct"). "Sure, Mia, can you tell me a
    joke about cats?" starts with a yes but isn't one (stage 7 simulation: it kept the third
    off-topic question from ending the call)."""
    return is_confirmation(text) and len(_words(text)) <= 6 and not text.strip().endswith("?")


# Asking for a person. Since stage 9 request_human rings a real phone, so it only runs when the
# caller asked for one, or said yes right after Mia offered (guardrails.check_call).
_PERSON = re.compile(
    r"\b(?:human|person|people|someone|somebody|agent|representative|rep|operator|manager|"
    r"sergio|real (?:person|human)|live (?:person|agent)|transfer me|connect me)\b",
    re.IGNORECASE,
)
_OFFER = re.compile(r"\b(?:connect|transfer|representative|put you through)\b", re.IGNORECASE)
_DECLINE = re.compile(r"\b(?:no|nope|don't|dont|do not|not now)\b", re.IGNORECASE)
_ACCEPT = re.compile(r"\b(?:yes|yeah|sure|please)\b", re.IGNORECASE)


def wants_person(text: str) -> bool:
    """Is the caller asking to talk to a person ("can I talk to a human?", "agent please")?
    "No, I don't want an agent" is not."""
    if _DECLINE.search(text) and not _ACCEPT.search(text):
        return False
    return bool(_PERSON.search(text))


# A plain request for a person, stricter than ``wants_person`` ("someone will drop it off"
# mentions someone): used when code itself runs request_human (Mia.llm_node), which rings a
# real phone.
_ASKS_PERSON = re.compile(
    r"\b(?:talk|speak|connect|transfer|put me through|get me)\b[^.?!]{0,40}"
    r"\b(?:person|human|representative|rep|agent|operator|someone|somebody)\b"
    r"|\b(?:real|live|actual) (?:person|human|representative|agent)\b",
    re.IGNORECASE,
)


def asks_for_person(text: str) -> bool:
    """ "Could you connect me to a live representative?", "I want to talk to a human". Not a
    "no" ("no, I don't need a person")."""
    if _DECLINE.search(text) and not _ACCEPT.search(text):
        return False
    return bool(_ASKS_PERSON.search(text))


def offered_person(mia_said: str) -> bool:
    """Did Mia's last line offer to connect the caller with someone?"""
    return bool(_OFFER.search(mia_said))


# Self-corrections ("it's a twenty ten... twenty twenty Toyota", Sergio's call, 2026-11-09: saved
# as 2010). A year is corrected when the next year follows it with nothing but these words in
# between, so "a 2019 and a 2020" (two cars) is not a correction.
_CORRECTION_WORDS = {
    "no",
    "nope",
    "sorry",
    "i",
    "mean",
    "meant",
    "actually",
    "wait",
    "uh",
    "um",
    "uhm",
    "er",
    "oh",
    "it",
    "s",
    "its",
    "is",
    "a",
    "an",
    "make",
    "that",
    "scratch",
    "correction",
    "rather",
    "not",
    "my",
    "bad",
}


def _years_in(text: str) -> list[tuple[int, int, int]]:
    """(start, end, year) for each year said in ``text``, as digits or words ("twenty ten").
    Bare two-digit forms ("ten", "20") are left out: too ambiguous to place."""
    words = _words(text)
    found: list[tuple[int, int, int]] = []
    for year in range(1950, 2031):
        for form in spoken_years(year):
            parts = form.split()
            if len(parts) < 2 and not (form.isdigit() and len(form) == 4):
                continue
            n = len(parts)
            for i in range(len(words) - n + 1):
                if words[i : i + n] == parts:
                    found.append((i, i + n, year))
    # Where forms overlap ("twenty twenty" inside "two thousand twenty"), keep the longest.
    found.sort(key=lambda f: (f[0], -(f[1] - f[0])))
    out: list[tuple[int, int, int]] = []
    for f in found:
        if out and f[0] < out[-1][1]:
            continue
        out.append(f)
    return out


def corrected_year(year: int | None, last_said: str) -> int | None:
    """The year the caller settled on: if they said ``year`` and then corrected it ("twenty
    ten... no, twenty twenty"), the later one; otherwise ``year`` unchanged."""
    if year is None:
        return None
    words = _words(last_said)
    mentions = _years_in(last_said)
    current = year
    for (_, end, first), (start, _, second) in zip(mentions, mentions[1:], strict=False):
        between = words[end:start]
        if first == current and first != second and all(w in _CORRECTION_WORDS for w in between):
            current = second
    return current


# Removing a vehicle and undoing a change only run on the caller's own words (gpt-oss invents
# tool calls; these change what's quoted).
_REMOVE = re.compile(
    # "eliminate": Sergio's call, 2026-11-11 ("Can you actually eliminate the Toyota?" was
    # dropped, then Mia read the same three cars back three times).
    r"\b(?:remove|eliminate|get rid of|exclude|erase|take (?:off|out|away)|drop|delete|"
    r"cancel|forget|scratch|without|leave out|"
    r"don'?t need|do not need|not (?:shipping|sending|bringing)|no longer|only (?:the|one)|"
    r"just (?:the|one))",
    re.IGNORECASE,
)
_UNDO = re.compile(
    r"\b(?:undo|go back|change (?:it|that) back|put (?:it|that) back|keep the|the (?:original|"
    r"previous|old|first) one|was right|as (?:it was|before)|never ?mind|changed my mind)",
    re.IGNORECASE,
)


def wants_removal(text: str) -> bool:
    """ "Remove the Toyota", "I don't need the second car", "just the Honda"."""
    return bool(_REMOVE.search(text))


_OFFERED_REMOVAL = re.compile(r"\bremove the\b[^.!?]*\?", re.IGNORECASE)


def offered_removal(mia_said: str) -> bool:
    """Did Mia just ask "Do you want me to remove the 2024 Toyota 4Runner?"."""
    return bool(_OFFERED_REMOVAL.search(mia_said))


def wants_undo(text: str) -> bool:
    """ "Actually, keep the Honda", "go back to the original", "never mind"."""
    return bool(_UNDO.search(text))


# note_off_topic ends the call on the third one, so a turn about shipping never counts, even
# if the model calls it (gpt-oss invents tool calls).
_ON_TOPIC = re.compile(
    r"\b(?:ship|shipping|send|sending|move|moving|transport|car|cars|vehicle|vehicles|truck|"
    r"suv|sedan|quote|price|cost|how much|enclosed|open|deliver|delivery|pick ?up|pay|payment|"
    r"cash|card|deposit|discount|drivable|run|runs|trailer|carrier|insurance|days|long|when|"
    r"representative|agent|person|human)",
    re.IGNORECASE,
)


def is_on_topic(text: str) -> bool:
    """Does the caller's message mention shipping, the car, the price or the call itself? A
    make or a year counts (real-API run, 2026-11-11: "It's a 2025 Honda Civic" was counted as
    an off-topic question)."""
    return bool(_ON_TOPIC.search(text)) or bool(makes_in(text)) or bool(_years_in(text))


# Questions. STT usually adds the "?", but not always, so a question word at the start counts
# too. Used when the guardrail drops the model's whole step: a question still gets an answer
# (live check, 2026-11-10: "do you do a closed shipping?" got only the vehicle question).
_QUESTION_START = re.compile(
    r"^\W*(?:(?:and|so|ok|okay|oh|um|uh|well|also|but|before that|wait)\W+)*"
    r"(?:do|does|did|can|could|is|are|was|will|would|should|how|what|whats|what's|when|"
    r"where|why|which|who|any|have you|is there|are there)\b",
    re.IGNORECASE,
)


def is_question(text: str) -> bool:
    """Is the caller asking something ("do you do enclosed shipping?", "how long does it
    take")? "Yeah, sure" and "a 2020 Honda" are not."""
    text = text.strip()
    return bool(text) and (text.endswith("?") or bool(_QUESTION_START.search(text)))
