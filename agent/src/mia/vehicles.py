"""Turn a spoken year/make/model into a CarHauler trim ID.

The LLM extracts ``year``, ``make`` and ``model`` from what the caller said (any of them may be
missing); this module matches them against the CarHauler catalog, tolerating speech-to-text
typos and spoken numbers ("four runner" → 4Runner, "CRV" → CR-V), and either returns a
``ResolvedVehicle`` or raises a ``VehicleError`` whose ``code`` tells the agent exactly what to
ask next (the "depth ladder" in docs/CONVERSATION_DESIGN.md):

    year + make + model  → resolved (first trim; the API lists the base trim first)
    make + year          → MISSING_MODEL
    make + model         → MISSING_YEAR
    model only           → make inferred from the catalog ("4Runner from 2020" → Toyota)
    nothing usable       → MISSING_MAKE_AND_MODEL

When a name doesn't match, nothing is guessed: ``*_NOT_FOUND`` carries close suggestions and
``AMBIGUOUS_*`` the options to read back ("the Silverado 1500 or the 2500 HD?").
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher, get_close_matches
from enum import StrEnum
from typing import Any

from mia.carhauler import VEHICLE_TYPES, CarHaulerClient, CarHaulerError, ErrorCode

# Cutoffs for fuzzy matching on normalized names (lowercase, letters and digits only).
FUZZY_CUTOFF = 0.8
# Without a make we search ~2,000 models, so a typo match must be stricter.
FUZZY_CUTOFF_NO_MAKE = 0.86
# The best fuzzy match must beat the runner-up by this much, or it's ambiguous.
FUZZY_MARGIN = 0.05
MAX_OPTIONS = 5

MAKE_ALIASES = {
    "chevy": "Chevrolet",
    "vw": "Volkswagen",
    "volks": "Volkswagen",
    "mercedes": "Mercedes-Benz",
    "benz": "Mercedes-Benz",
    "merc": "Mercedes-Benz",
    "caddy": "Cadillac",
    "caddie": "Cadillac",
    "beemer": "BMW",
    "bimmer": "BMW",
    "rolls": "Rolls-Royce",
    "alfa": "Alfa Romeo",
    "aston": "Aston Martin",
    "landy": "Land Rover",
    "range rover": "Land Rover",
    "mini cooper": "MINI",
    "infinity": "INFINITI",
    "hummer": "HUMMER",
}

_NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    # Spoken model numbers: "F one fifty" (Sergio's call, 2026-11-11: grounding didn't match
    # "F-150" and Mia asked for the model three times), "two fifty", "fifteen hundred".
    "zero": "0",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "00",
}

VEHICLE_TYPE_ALIASES = {
    "car": "sedan",
    "regular car": "sedan",
    "normal car": "sedan",
    "sedan": "sedan",
    "saloon": "sedan",
    "suv": "suv",
    "crossover": "suv",
    "sport utility": "suv",
    "pickup": "pickup",
    "pick up": "pickup",
    "pickup truck": "pickup",
    "pick up truck": "pickup",
    "truck": "truck",
    "van": "van",
    "cargo van": "van",
    "minivan": "minivan",
    "mini van": "minivan",
    "hatchback": "hatchback",
    "hatch": "hatchback",
    "convertible": "convertible",
    "cabriolet": "convertible",
    "coupe": "coupe",
    "wagon": "wagon",
    "station wagon": "wagon",
    "estate": "wagon",
}


class VehicleErrorCode(StrEnum):
    MISSING_MAKE_AND_MODEL = "MISSING_MAKE_AND_MODEL"
    MISSING_MODEL = "MISSING_MODEL"
    MISSING_YEAR = "MISSING_YEAR"
    MAKE_NOT_FOUND = "MAKE_NOT_FOUND"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    AMBIGUOUS_MAKE = "AMBIGUOUS_MAKE"
    AMBIGUOUS_MODEL = "AMBIGUOUS_MODEL"
    YEAR_NOT_AVAILABLE = "YEAR_NOT_AVAILABLE"
    NO_TRIMS = "NO_TRIMS"


class VehicleError(Exception):
    def __init__(
        self,
        code: VehicleErrorCode,
        *,
        known: dict[str, Any] | None = None,
        options: list[str] | None = None,
        available_years: list[int] | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.known = known or {}  # what was resolved so far: year, make, model (catalog names)
        self.options = options or []  # suggestions or choices to read back to the caller
        self.available_years = available_years or []

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error_code": str(self.code), "known": self.known}
        if self.options:
            out["options"] = self.options
        if self.available_years:
            out["available_years"] = {
                "from": min(self.available_years),
                "to": max(self.available_years),
            }
        return out


@dataclass(frozen=True)
class ResolvedVehicle:
    year: int
    make: str
    model: str
    make_id: int
    model_id: int
    trim_id: int
    trim_name: str
    trims_available: int = 1
    corrections: dict[str, str] = field(default_factory=dict)  # spoken → catalog, if fuzzy

    @property
    def label(self) -> str:
        return f"{self.year} {self.make} {self.model}"


# --- matching ----------------------------------------------------------------------------


def normalize(text: str) -> str:
    """'4 Runner' / 'four runner' / '4-Runner' → '4runner'; 'CR-V' → 'crv'."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "".join(_NUMBER_WORDS.get(w, w) for w in words)


@dataclass(frozen=True)
class _Match:
    kind: str  # exact | extends | prefix | fuzzy | ambiguous | none
    items: list[Any]


def _best_match(query: str, items: list[Any], name_of, cutoff: float = FUZZY_CUTOFF) -> _Match:
    """Match a spoken name against catalog items, most to least certain."""
    q = normalize(query)
    if not q:
        return _Match("none", [])
    normed = [(normalize(name_of(it)), it) for it in items]

    exact = [it for n, it in normed if n == q]
    if exact:
        return _Match("exact", exact[:1])

    # The caller said less than the catalog name ("Silverado" → "Silverado 1500", ...).
    extends = [it for n, it in normed if n.startswith(q) and len(q) >= 2]
    if len(extends) == 1:
        return _Match("extends", extends)
    if len(extends) > 1:
        extends.sort(key=lambda it: (len(name_of(it)), name_of(it)))
        return _Match("ambiguous", extends[:MAX_OPTIONS])

    # The caller said more than the catalog name ("Civic sedan" → "Civic"): longest wins.
    prefixes = [(n, it) for n, it in normed if q.startswith(n) and len(n) >= 3]
    if prefixes:
        prefixes.sort(key=lambda p: len(p[0]), reverse=True)
        return _Match("prefix", [prefixes[0][1]])

    scored = sorted(
        ((SequenceMatcher(None, q, n).ratio(), it) for n, it in normed),
        key=lambda s: s[0],
        reverse=True,
    )
    good = [(s, it) for s, it in scored if s >= cutoff]
    if len(good) == 1 or (len(good) > 1 and good[0][0] - good[1][0] >= FUZZY_MARGIN):
        return _Match("fuzzy", [good[0][1]])
    if len(good) > 1:
        return _Match("ambiguous", [it for _, it in good[:MAX_OPTIONS]])
    return _Match("none", [])


def _suggestions(query: str, names: list[str], n: int = 3) -> list[str]:
    by_norm = {normalize(x): x for x in names}
    return [by_norm[m] for m in get_close_matches(normalize(query), list(by_norm), n, 0.6)]


def normalize_year(year: int | str | None, today: date | None = None) -> int | None:
    """2020 → 2020; '20 / 20 → 2020; 98 → 1998. None or garbage → None."""
    if year is None:
        return None
    try:
        y = int(str(year).strip().lstrip("'"))
    except ValueError:
        return None
    if y < 100:
        this_year = (today or date.today()).year
        y += 2000 if 2000 + y <= this_year + 1 else 1900
    return y if 1900 <= y <= 2100 else None


def normalize_vehicle_type(spoken: str | None) -> str | None:
    """'pick up truck' → 'pickup', 'crossover' → 'suv'. Unknown → None."""
    if not spoken:
        return None
    key = " ".join(re.findall(r"[a-z]+", spoken.lower()))
    if key in VEHICLE_TYPE_ALIASES:
        return VEHICLE_TYPE_ALIASES[key]
    squashed = key.replace(" ", "")
    return squashed if squashed in VEHICLE_TYPES else None


# --- resolution --------------------------------------------------------------------------


class VehicleResolver:
    """Resolves vehicles against the catalog. One per worker; the client caches lookups."""

    def __init__(
        self,
        client: CarHaulerClient,
        *,
        concurrency: int = 8,
        model_index: list[dict[str, Any]] | None = None,
    ):
        self._client = client
        self._concurrency = concurrency
        self._model_index = model_index  # pass a warm one to skip the first-call lookups
        self._index_lock = asyncio.Lock()

    async def _models(self, make_id: int) -> list[dict[str, Any]]:
        """Models of a make. A few makes with no models (Daihatsu, Freightliner, SRT on
        2026-11-08) get an HTML error page instead of ``[]``; treat that as no models."""
        try:
            return await self._client.models(make_id)
        except CarHaulerError as exc:
            if exc.code == ErrorCode.BAD_RESPONSE:
                return []
            raise

    async def model_index(self) -> list[dict[str, Any]]:
        """Every (make, model) in the catalog, for callers who name only the model.

        ~70 cheap lookups the first time (run concurrently), then cached. Call it at worker
        startup so the first caller doesn't wait for it.
        """
        async with self._index_lock:
            if self._model_index is None:
                makes = await self._client.makes()
                sem = asyncio.Semaphore(self._concurrency)

                async def models_of(make: dict[str, Any]) -> list[dict[str, Any]]:
                    async with sem:
                        models = await self._models(make["id"])
                    return [
                        {
                            "make_id": make["id"],
                            "make": make["name"],
                            "model_id": m["id"],
                            "model": m["name"],
                        }
                        for m in models
                    ]

                groups = await asyncio.gather(*(models_of(m) for m in makes))
                self._model_index = [row for group in groups for row in group]
        return self._model_index

    async def _match_make(self, spoken: str) -> tuple[dict[str, Any], str | None]:
        makes = await self._client.makes()
        alias = MAKE_ALIASES.get(" ".join(re.findall(r"[a-z]+", spoken.lower())))
        query = alias or spoken
        m = _best_match(query, makes, lambda x: x["name"])
        if m.kind == "ambiguous":
            raise VehicleError(
                VehicleErrorCode.AMBIGUOUS_MAKE, options=[x["name"] for x in m.items]
            )
        if m.kind == "none":
            raise VehicleError(
                VehicleErrorCode.MAKE_NOT_FOUND,
                options=_suggestions(spoken, [x["name"] for x in makes]),
            )
        make = m.items[0]
        corrected = make["name"] if m.kind == "fuzzy" and not alias else None
        return make, corrected

    async def resolve(
        self,
        *,
        year: int | str | None = None,
        make: str | None = None,
        model: str | None = None,
    ) -> ResolvedVehicle:
        year_n = normalize_year(year)
        make = (make or "").strip() or None
        model = (model or "").strip() or None
        known: dict[str, Any] = {"year": year_n} if year_n else {}
        corrections: dict[str, str] = {}

        if not make and not model:
            raise VehicleError(VehicleErrorCode.MISSING_MAKE_AND_MODEL, known=known)

        # 1. Make (inferred from the model when the caller didn't say it).
        if make:
            make_row, corrected = await self._match_make(make)
            if corrected:
                corrections[make] = corrected
            known["make"] = make_row["name"]
            if not model:
                raise VehicleError(VehicleErrorCode.MISSING_MODEL, known=known)
            models = await self._models(make_row["id"])
            m = _best_match(model, models, lambda x: x["name"])
            if m.kind == "ambiguous":
                raise VehicleError(
                    VehicleErrorCode.AMBIGUOUS_MODEL,
                    known=known,
                    options=[x["name"] for x in m.items],
                )
            if m.kind == "none":
                raise VehicleError(
                    VehicleErrorCode.MODEL_NOT_FOUND,
                    known=known,
                    options=_suggestions(model, [x["name"] for x in models]),
                )
            model_row = m.items[0]
            if m.kind == "fuzzy":
                corrections[model] = model_row["name"]
            make_id, make_name = make_row["id"], make_row["name"]
            model_id, model_name = model_row["id"], model_row["name"]
        else:
            assert model is not None
            index = await self.model_index()
            m = _best_match(model, index, lambda x: x["model"], cutoff=FUZZY_CUTOFF_NO_MAKE)
            if m.kind == "ambiguous" or (
                m.kind != "none" and len({(x["make"], x["model"]) for x in m.items}) > 1
            ):
                raise VehicleError(
                    VehicleErrorCode.AMBIGUOUS_MAKE,
                    known=known,
                    options=[f"{x['make']} {x['model']}" for x in m.items],
                )
            if m.kind == "none":
                raise VehicleError(
                    VehicleErrorCode.MODEL_NOT_FOUND,
                    known=known,
                    options=_suggestions(model, sorted({x["model"] for x in index})),
                )
            row = m.items[0]
            # Same model name under two makes (rare) → ask which make.
            same_name = [x for x in index if normalize(x["model"]) == normalize(row["model"])]
            if len({x["make_id"] for x in same_name}) > 1:
                raise VehicleError(
                    VehicleErrorCode.AMBIGUOUS_MAKE,
                    known=known,
                    options=[f"{x['make']} {x['model']}" for x in same_name][:MAX_OPTIONS],
                )
            if m.kind == "fuzzy":
                corrections[model] = row["model"]
            make_id, make_name = row["make_id"], row["make"]
            model_id, model_name = row["model_id"], row["model"]

        known.update(make=make_name, model=model_name)

        # 2. Year.
        years = await self._client.years(model_id)
        if not year_n:
            raise VehicleError(VehicleErrorCode.MISSING_YEAR, known=known, available_years=years)
        if year_n not in years:
            raise VehicleError(
                VehicleErrorCode.YEAR_NOT_AVAILABLE, known=known, available_years=years
            )

        # 3. Trim: the API lists the base trim first; that's our default.
        trims = await self._client.trims(model_id, year_n)
        if not trims:
            raise VehicleError(VehicleErrorCode.NO_TRIMS, known=known, available_years=years)
        trim = trims[0]
        return ResolvedVehicle(
            year=year_n,
            make=make_name,
            model=model_name,
            make_id=make_id,
            model_id=model_id,
            trim_id=int(trim["id"]),
            trim_name=str(trim["name"]),
            trims_available=len(trims),
            corrections=corrections,
        )
