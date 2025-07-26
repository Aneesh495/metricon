from __future__ import annotations

import contextlib
from typing import Iterator

import duckdb
import polars as pl

from metricon.schema.events import ARROW_SCHEMA
from metricon.storage.catalog import Catalog


@contextlib.contextmanager
def analytical_connection(
    catalog: Catalog, dataset_id: str, memory_limit: str = "1GB"
) -> Iterator[duckdb.DuckDBPyConnection]:
    manifest = catalog.dataset(dataset_id)["manifest"]
    paths = [str(catalog.root / part["path"]) for part in manifest["partitions"]]
    connection = duckdb.connect(":memory:")
    connection.execute("SET memory_limit=?", (memory_limit,))
    connection.execute("SET threads=2")
    temp = catalog.root / "query-temp"
    temp.mkdir(exist_ok=True)
    connection.execute("SET temp_directory=?", (str(temp),))
    if paths:
        connection.read_parquet(paths, union_by_name=True).create_view("events")
    else:
        import pyarrow as pa

        connection.register("events", pa.Table.from_pylist([], schema=ARROW_SCHEMA))
    try:
        yield connection
    finally:
        connection.close()


def scan_events(catalog: Catalog, dataset_id: str) -> pl.LazyFrame:
    manifest = catalog.dataset(dataset_id)["manifest"]
    paths = [str(catalog.root / part["path"]) for part in manifest["partitions"]]
    if not paths:
        import pyarrow as pa

        return pl.from_arrow(pa.Table.from_pylist([], schema=ARROW_SCHEMA)).lazy()
    return pl.scan_parquet(paths)
