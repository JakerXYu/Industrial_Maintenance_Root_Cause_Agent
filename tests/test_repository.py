"""Tests for the read-only repository."""


def test_get_asset_existing_and_missing(repository):
    asset = repository.get_asset("A001")
    assert asset is not None
    assert asset.asset_id == "A001"
    assert repository.get_asset("DOES_NOT_EXIST") is None


def test_list_assets(repository):
    assets = repository.list_assets()
    assert len(assets) == 25
    ids = [asset.asset_id for asset in assets]
    assert ids == sorted(ids)


def test_search_recent_work_orders(repository):
    orders = repository.search_recent_work_orders("A001", 30, 100)
    assert orders
    assert all(order.asset_id == "A001" for order in orders)


def test_get_recent_meter_readings(repository):
    readings = repository.get_recent_meter_readings("A001", 7, 100000)
    assert readings
    assert all(reading.asset_id == "A001" for reading in readings)
