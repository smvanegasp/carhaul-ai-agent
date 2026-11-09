import time

from mia import catalog


async def test_snapshot_survives_a_restart_without_new_calls(client, fake_api, tmp_path):
    snap = await catalog.fetch(client)
    calls = sum(fake_api.calls.values())
    assert calls > 1 and snap["index"]
    path = tmp_path / "catalog.json"
    catalog.save(path, snap)

    loaded = catalog.load(path)
    assert loaded and loaded["index"] == snap["index"]
    assert set(loaded["cache"]) == set(snap["cache"])

    # A new client seeded from the file answers catalog lookups without calling the API.
    from mia.carhauler import CarHaulerClient
    from mia.vehicles import VehicleResolver

    fresh = CarHaulerClient(api_key="test-key", base_url=client._base_url, retry_wait=0)
    fresh.seed_cache(loaded["cache"])
    resolver = VehicleResolver(fresh, model_index=loaded["index"])
    await resolver.model_index()
    assert await fresh.makes() == await client.makes()
    assert sum(fake_api.calls.values()) == calls
    await fresh.aclose()


def test_stale_or_missing_or_broken_files_are_ignored(tmp_path):
    path = tmp_path / "catalog.json"
    assert catalog.load(path) is None
    snap = {"cache": {("/car/makes", ()): (0.0, [{"id": 1, "name": "Toyota"}])}, "index": []}
    catalog.save(path, snap, now=time.time() - catalog.MAX_AGE_SECONDS - 1)
    assert catalog.load(path) is None
    catalog.save(path, snap)
    assert catalog.load(path)["cache"][("/car/makes", ())][1][0]["name"] == "Toyota"
    path.write_text("{not json", encoding="utf-8")
    assert catalog.load(path) is None
