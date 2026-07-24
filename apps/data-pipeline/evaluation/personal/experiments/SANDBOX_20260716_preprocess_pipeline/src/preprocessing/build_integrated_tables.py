"""Build relational integrated tables (no naive row-concat of heterogeneous sources)."""
from __future__ import annotations

import pandas as pd

from .utils import save_table
from . import paths


def build_poi_master(tour: pd.DataFrame, parks: pd.DataFrame, city: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """poi with coords vs city tour without coords."""
    t = pd.DataFrame({
        "poi_id": "TOUR-" + tour["contentid"].astype("string"),
        "poi_type": "TOUR_API",
        "name": tour.get("title"),
        "address": tour.get("address_std"),
        "lat": tour.get("lat"),
        "lng": tour.get("lng"),
        "source": "TourAPI",
        "isMock": False,
        "encoding_repaired": tour.get("encoding_repaired", False),
        "has_coords": True,
    })
    p = pd.DataFrame({
        "poi_id": "PARK-" + parks["mngNo"].astype("string"),
        "poi_type": "PARK_WALK",
        "name": parks.get("parkNm"),
        "address": parks.get("representative_address"),
        "lat": parks.get("lat_num"),
        "lng": parks.get("lng"),
        "source": "WalkParks",
        "isMock": False,
        "address_source": parks.get("address_source"),
        "has_coords": parks.get("coord_valid", True),
    })
    poi = pd.concat([t, p], ignore_index=True, sort=False)

    city_nocoord = pd.DataFrame({
        "poi_id": city["poi_id"],
        "poi_type": "CITY_TOUR",
        "name": city.get("name"),
        "address": city.get("address"),
        "lat": pd.NA,
        "lng": pd.NA,
        "source": "Daegu_CityTour",
        "isMock": False,
        "has_coords": False,
        "needs_geocoding": True,
    })
    return poi, city_nocoord


def persist_all(tables: dict[str, pd.DataFrame]) -> None:
    paths.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paths.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        save_table(df, paths.PROCESSED_DIR / name)
