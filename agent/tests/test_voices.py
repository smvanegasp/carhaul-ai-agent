"""Mia's voice choices (mia/voices.py) and their match with the API's list."""

import ast
from pathlib import Path

import pytest
from livekit.plugins import cartesia, deepgram, elevenlabs

from mia import voices

BACKEND_VOICES = Path(__file__).resolve().parents[2] / "backend" / "app" / "voices.py"


def _backend_list() -> tuple[list[str], str]:
    """The keys and default in backend/app/voices.py (read, not imported: another project)."""
    tree = ast.parse(BACKEND_VOICES.read_text(encoding="utf-8"))
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("VOICES", "DEFAULT")
    }
    return [key for key, _label in values["VOICES"]], values["DEFAULT"]


def test_the_api_offers_exactly_the_voices_the_worker_knows():
    keys, default = _backend_list()
    assert keys == list(voices.VOICES)
    assert default == voices.DEFAULT


def test_two_voices_per_provider():
    providers = [v.provider for v in voices.VOICES.values()]
    assert {p: providers.count(p) for p in set(providers)} == {
        "elevenlabs": 2,
        "cartesia": 2,
        "deepgram": 2,
    }


@pytest.mark.parametrize("key", [None, "", "nope", "elevenlabs-mia"])
def test_unknown_or_missing_voice_gets_the_default(key):
    assert voices.pick(key).key == voices.DEFAULT


@pytest.fixture
def keys(monkeypatch):
    for name in (
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID",
        "CARTESIA_API_KEY",
        "DEEPGRAM_API_KEY",
    ):
        monkeypatch.setenv(name, "test")


@pytest.mark.parametrize(
    ("key", "cls"),
    [
        ("elevenlabs-mia", elevenlabs.TTS),
        ("elevenlabs-jessica", elevenlabs.TTS),
        ("cartesia-courtney", cartesia.TTS),
        ("deepgram-thalia", deepgram.TTS),
    ],
)
def test_each_voice_builds_its_providers_tts(keys, key, cls):
    assert isinstance(voices.make_tts(voices.VOICES[key]), cls)
