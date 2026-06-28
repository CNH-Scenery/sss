from sqlalchemy import inspect, text

from app.db import create_engine_from_url, init_db


def test_create_engine_from_url_connects_to_sqlite_database(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'tacit_trader_test.db'}"
    engine = create_engine_from_url(database_url)

    with engine.connect() as connection:
        result = connection.execute(text("select 1")).scalar_one()

    assert result == 1


def test_init_db_creates_candle_cache_table(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'tables.db'}")

    init_db(engine)

    assert "candles" in inspect(engine).get_table_names()
