"""What the simulations are made of (docs/CONVERSATION_DESIGN.md, "Testing design").

- **Personas**: 3 attributes, 8 combinations. Codes are ``{NG|G}_{C|P}_{NV|V}``: generous or
  not, complete or partial, verbose or not.
- **Cases**: ground truths (route and vehicles) the fake APIs can quote: cities from
  ``tests/fake_geo.py``, vehicles from ``tests/fake_carhauler.py``.
- **Paths**: which fragments a call contains. A fragment fires once, the first time the call
  reaches its trigger, and tells the caller model what to do in that turn; the persona decides
  how it's said. So a path is reproducible while the words change on every run.

Triggers, from what's on file before the caller speaks:
``route`` (nothing on file yet), ``vehicle`` (route on file, no vehicle),
``read_back`` (everything on file, no quote), ``after_quote`` (a quote was given).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product


@dataclass(frozen=True)
class Persona:
    generous: bool
    complete: bool
    verbose: bool

    @property
    def code(self) -> str:
        return "_".join(
            [
                "G" if self.generous else "NG",
                "C" if self.complete else "P",
                "V" if self.verbose else "NV",
            ]
        )

    def describe(self) -> str:
        return " ".join(
            [
                (
                    "You volunteer details before you're asked and like to give several at "
                    "once (the route and the car in one go)."
                    if self.generous
                    else "You only answer exactly what Mia asks, one thing at a time."
                ),
                (
                    "When you give a detail you give all of it: city and state, and the car's "
                    "year, make and model."
                    if self.complete
                    else "You give about half of each detail at first (a city without its "
                    "state, 'a Honda' without the year or model, or the year without the "
                    "model) and the rest only when Mia asks for it."
                ),
                (
                    "You talk a lot: fillers, side comments and small stories around the "
                    "answer, two or three sentences per turn."
                    if self.verbose
                    else "You're brief: a few words per turn."
                ),
            ]
        )


PERSONAS = [Persona(g, c, v) for g, c, v in product([False, True], repeat=3)]


@dataclass(frozen=True)
class Place:
    city: str
    state: str

    @property
    def label(self) -> str:  # what QuoteSession.snapshot() shows
        return f"{self.city}, {self.state}"


@dataclass(frozen=True)
class Case:
    origin: Place
    destination: Place
    vehicles: tuple[str, ...]  # "2020 Toyota Camry", as QuoteSession labels them


def _case(o: str, os_: str, d: str, ds: str, *vehicles: str) -> Case:
    return Case(Place(o, os_), Place(d, ds), tuple(vehicles))


CASES = [
    _case("Miami", "Florida", "Boston", "Massachusetts", "2020 Toyota Camry"),
    _case("Chicago", "Illinois", "Seattle", "Washington", "2021 Ford F-150"),
    _case("Denver", "Colorado", "Austin", "Texas", "2018 Honda CR-V"),
    _case("Atlanta", "Georgia", "Portland", "Oregon", "2022 Toyota RAV4", "2017 Honda Civic"),
    _case("Dallas", "Texas", "Los Angeles", "California", "2019 Chevrolet Malibu"),
    _case("New York", "New York", "Orlando", "Florida", "2025 Honda Civic"),
    _case("Phoenix", "Arizona", "Chicago", "Illinois", "2023 Audi A4"),
    _case(
        "Boston",
        "Massachusetts",
        "San Francisco",
        "California",
        "2025 Honda Civic",
        "2020 Toyota 4Runner",
    ),
]

# Changes after the quote: the new value, picked so it differs from the case's.
NEW_VEHICLES = ["2020 Toyota 4Runner", "2019 Toyota Corolla"]
NEW_DESTINATIONS = [Place("Tampa", "Florida"), Place("Denver", "Colorado")]

# FAQs (CONVERSATION_DESIGN.md) and what a right answer must mention: every group needs one
# of its words. Code, not a judge: cheap and the same every run.
FAQS = [
    ("Do you do enclosed shipping?", [["open"]]),
    ("Can I pay with a credit card?", [["cash"], ["3", "three"]]),
    ("Can I leave some boxes in the trunk?", [["100", "hundred"]]),
    ("Is there a discount if I pay a deposit upfront?", [["4", "four"]]),
]
HOW_LONG = ("How long will the shipping take?", [["day"]])

OFF_TOPIC = [
    "What's the capital of France?",
    "Tell me a joke about cats.",
    "Who won the Super Bowl last year?",
    "What's your favorite pizza topping?",
]


@dataclass
class Fragment:
    kind: str  # faq | off_topic | correction | change_vehicle | change_route | person
    trigger: str  # route | vehicle | read_back | after_quote
    text: str = ""  # the question, or the new value for changes
    expect_words: list[list[str]] = field(default_factory=list)  # faq only


@dataclass
class PathSpec:
    code: str
    family: str  # SHP | QHP | NHP | AP (CONVERSATION_DESIGN.md, "Paths")
    about: str
    end: str = "decline"  # after the last quote: decline | accept (the representative)
    expect_quote: bool = True
    expect_transfer: bool = False
    expect_off_topic_end: bool = False


PATHS = [
    PathSpec("SHP", "SHP", "strict happy path, declines the representative"),
    PathSpec(
        "SHP_transfer",
        "SHP",
        "happy path, says yes to the representative",
        end="accept",
        expect_transfer=True,
    ),
    PathSpec("QHP", "QHP", "an FAQ at the vehicle question and one after the quote"),
    PathSpec("NHP_correction", "NHP", "self-corrects the car's year"),
    PathSpec("NHP_change_vehicle", "NHP", "changes the car after the quote"),
    PathSpec("NHP_change_route", "NHP", "changes the destination after the quote"),
    PathSpec(
        "NHP_person",
        "NHP",
        "asks for a person at the vehicle question",
        expect_quote=False,
        expect_transfer=True,
    ),
    PathSpec("AP_two", "AP", "two off-topic questions, then a normal call"),
    PathSpec(
        "AP_three",
        "AP",
        "three off-topic questions in a row from the start",
        expect_quote=False,
        expect_off_topic_end=True,
    ),
]
PATH_CODES = [p.code for p in PATHS]


def path(code: str) -> PathSpec:
    return next(p for p in PATHS if p.code == code)


def fragments(spec: PathSpec, case: Case, n: int) -> list[Fragment]:
    """The fragments of one call; ``n`` (the call's index) varies the question and the change."""
    if spec.code == "QHP":
        q, words = FAQS[n % len(FAQS)]
        return [
            Fragment("faq", "vehicle", q, words),
            Fragment("faq", "after_quote", HOW_LONG[0], HOW_LONG[1]),
        ]
    if spec.code == "NHP_correction":
        return [Fragment("correction", "vehicle")]
    if spec.code == "NHP_change_vehicle":
        new = next(v for v in NEW_VEHICLES if v not in case.vehicles)
        return [Fragment("change_vehicle", "after_quote", new)]
    if spec.code == "NHP_change_route":
        new = next(p for p in NEW_DESTINATIONS if p != case.destination)
        return [Fragment("change_route", "after_quote", new.label)]
    if spec.code == "NHP_person":
        return [Fragment("person", "vehicle")]
    if spec.code == "AP_two":
        return [
            Fragment("off_topic", "route", OFF_TOPIC[n % len(OFF_TOPIC)]),
            Fragment("off_topic", "vehicle", OFF_TOPIC[(n + 1) % len(OFF_TOPIC)]),
        ]
    if spec.code == "AP_three":
        return [
            Fragment("off_topic", "route", OFF_TOPIC[(n + i) % len(OFF_TOPIC)]) for i in range(3)
        ]
    return []


@dataclass
class Plan:
    """One simulated call."""

    id: str
    persona: Persona
    path: PathSpec
    case: Case
    fragments: list[Fragment]


def build_plan(
    personas: list[str] | None = None,
    paths: list[str] | None = None,
    repeat: int = 1,
) -> list[Plan]:
    """Every persona x path (x repeat). Cases rotate so each persona meets several routes and
    both one- and two-vehicle calls."""
    chosen_personas = [p for p in PERSONAS if not personas or p.code in personas]
    chosen_paths = [p for p in PATHS if not paths or p.code in paths]
    plans = []
    for r in range(repeat):
        for i, persona in enumerate(chosen_personas):
            for j, spec in enumerate(chosen_paths):
                n = (i * len(PATHS) + j + r * 3) % (len(CASES) * len(PATHS))
                case = CASES[(i + j + r) % len(CASES)]
                suffix = f"_r{r + 1}" if repeat > 1 else ""
                plans.append(
                    Plan(
                        f"{persona.code}__{spec.code}{suffix}",
                        persona,
                        spec,
                        case,
                        fragments(spec, case, n),
                    )
                )
    return plans
