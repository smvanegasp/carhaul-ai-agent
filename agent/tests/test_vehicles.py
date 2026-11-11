from __future__ import annotations

from datetime import date

import pytest

from mia.vehicles import (
    VehicleError,
    VehicleErrorCode,
    normalize,
    normalize_vehicle_type,
    normalize_year,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4Runner", "4runner"),
        ("four runner", "4runner"),
        ("4-Runner", "4runner"),
        ("CR-V", "crv"),
        ("RAV four", "rav4"),
        ("Mercedes-Benz", "mercedesbenz"),
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (2020, 2020),
        ("2020", 2020),
        ("'18", 2018),
        (20, 2020),
        (98, 1998),
        (None, None),
        ("x", None),
    ],
)
def test_normalize_year(raw, expected):
    assert normalize_year(raw, today=date(2026, 11, 8)) == expected


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("SUV", "suv"),
        ("crossover", "suv"),
        ("pick up truck", "pickup"),
        ("Car", "sedan"),
        ("minivan", "minivan"),
        ("mini van", "minivan"),
        ("spaceship", None),
        (None, None),
    ],
)
def test_normalize_vehicle_type(spoken, expected):
    assert normalize_vehicle_type(spoken) == expected


# --- resolution: the ways people say year/make/model (docs/CONVERSATION_DESIGN.md) -------


@pytest.mark.parametrize(
    "year, make, model, label",
    [
        (2025, "Honda", "Civic", "2025 Honda Civic"),  # "2025 Honda Civic"
        (2020, "Toyota", "4Runner", "2020 Toyota 4Runner"),  # "Toyota 4Runner from 2020"
        (2020, None, "4Runner", "2020 Toyota 4Runner"),  # "4Runner from 2020" / "2020 4Runner"
        (2020, "toyota", "four runner", "2020 Toyota 4Runner"),  # spoken number
        (2022, "Honda", "CRV", "2022 Honda CR-V"),
        (2022, "Honda", "Civic sedan", "2022 Honda Civic"),  # said more than the model
        (2021, "Chevy", "Malibu", "2021 Chevrolet Malibu"),  # alias
        (2021, "Mercedes", "C Class", "2021 Mercedes-Benz C-Class"),
        ("'19", "Toyota", "Corolla", "2019 Toyota Corolla"),
        (2023, "Ford", "F150", "2023 Ford F-150"),
    ],
)
async def test_resolves(resolver, year, make, model, label):
    v = await resolver.resolve(year=year, make=make, model=model)
    assert v.label == label
    assert v.trim_id > 0


async def test_resolves_to_base_trim(resolver):
    v = await resolver.resolve(year=2025, make="Honda", model="Civic")
    assert v.trim_id == 34547
    assert v.trim_name.startswith("LX")
    assert v.trims_available == 2


@pytest.mark.parametrize(
    "make, model, fixed",
    [
        ("Hondda", "Civic", {"Hondda": "Honda"}),
        ("Toyota", "Corola", {"Corola": "Corolla"}),
        ("Toyta", "Camri", {"Toyta": "Toyota", "Camri": "Camry"}),
    ],
)
async def test_typos_are_corrected_and_reported(resolver, make, model, fixed):
    v = await resolver.resolve(year=2020, make=make, model=model)
    assert v.corrections == fixed


@pytest.mark.parametrize(
    "year, make, model, code, known",
    [
        # "Toyota from 2020" / "2020 Toyota"
        (2020, "Toyota", None, VehicleErrorCode.MISSING_MODEL, {"year": 2020, "make": "Toyota"}),
        # "Toyota 4Runner"
        (
            None,
            "Toyota",
            "4Runner",
            VehicleErrorCode.MISSING_YEAR,
            {"make": "Toyota", "model": "4Runner"},
        ),
        # "Toyota"
        (None, "Toyota", None, VehicleErrorCode.MISSING_MODEL, {"make": "Toyota"}),
        # "it's a 2020"
        (2020, None, None, VehicleErrorCode.MISSING_MAKE_AND_MODEL, {"year": 2020}),
        (None, "", "  ", VehicleErrorCode.MISSING_MAKE_AND_MODEL, {}),
    ],
)
async def test_missing_parts_drive_the_next_question(resolver, year, make, model, code, known):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=year, make=make, model=model)
    assert exc.value.code == code
    assert exc.value.known == known


async def test_ambiguous_model_lists_options(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, make="Chevrolet", model="Silverado")
    assert exc.value.code == VehicleErrorCode.AMBIGUOUS_MODEL
    assert exc.value.options == ["Silverado 1500", "Silverado 2500HD"]


async def test_exact_model_beats_longer_names(resolver):
    v = await resolver.resolve(year=2020, make="Toyota", model="Corolla")
    assert v.model == "Corolla"  # not "Corolla Cross"


async def test_model_shared_by_two_makes_asks_for_make(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, model="Ranger")
    assert exc.value.code == VehicleErrorCode.AMBIGUOUS_MAKE
    assert set(exc.value.options) == {"Ford Ranger", "GMC Ranger"}


async def test_unknown_make_suggests(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, make="Hondo Motors", model="Civic")
    assert exc.value.code == VehicleErrorCode.MAKE_NOT_FOUND


async def test_unknown_model_suggests_close_names(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, make="Audi", model="A9")
    assert exc.value.code == VehicleErrorCode.MODEL_NOT_FOUND
    assert exc.value.known == {"year": 2020, "make": "Audi"}
    assert set(exc.value.options) <= {"A4", "A5"}


async def test_does_not_guess_a_different_model(resolver):
    # A4 vs A5 differ by one character; never silently swap them.
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, make="Audi", model="A6")
    assert exc.value.code == VehicleErrorCode.MODEL_NOT_FOUND


async def test_year_not_available(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=1990, make="Toyota", model="RAV4")
    assert exc.value.code == VehicleErrorCode.YEAR_NOT_AVAILABLE
    assert exc.value.to_dict()["available_years"] == {"from": 2015, "to": 2025}


async def test_year_without_trims(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2015, make="Honda", model="Civic")
    assert exc.value.code == VehicleErrorCode.NO_TRIMS


async def test_model_index_is_built_once(resolver, fake_api):
    await resolver.resolve(year=2020, model="4Runner")
    await resolver.resolve(year=2020, model="Camry")
    assert fake_api.calls["/car/makes"] == 1
    assert fake_api.calls["/car/models"] == 8  # one per make, cached after


async def test_make_without_models(resolver):
    with pytest.raises(VehicleError) as exc:
        await resolver.resolve(year=2020, make="SRT", model="Viper")
    assert exc.value.code == VehicleErrorCode.MODEL_NOT_FOUND


@pytest.mark.parametrize(
    "spoken, digits",
    [
        ("f hundred and fifty", "f150"),  # Sergio's call, 2026-11-11
        ("one hundred and fifty", "150"),
        ("f one fifty", "f150"),
        ("fifteen hundred", "1500"),
        ("ram twenty five hundred", "ram2500"),
        ("twenty twenty one", "2021"),
        ("four runner", "4runner"),
        ("F-150", "f150"),
    ],
)
def test_spoken_numbers_normalize_to_digits(spoken, digits):
    from mia.vehicles import normalize

    assert normalize(spoken) == digits
