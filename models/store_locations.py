from __future__ import annotations

from functools import lru_cache

import pandas as pd

from config import APP_ROOT


# Coordinates are taken from the official store pages' "Get Directions"
# links, which point to Google Maps with exact lat/lon values.
HILTI_UK_STORES: tuple[dict[str, object], ...] = (
    {
        "name": "Construction Hub Belfast",
        "city": "Belfast",
        "postcode": "BT3 9BP",
        "district": "BT3",
        "latitude": 54.6247464,
        "longitude": -5.914934,
        "url": "https://www.hilti.co.uk/stores/belfast",
    },
    {
        "name": "Construction Hub Birmingham",
        "city": "Birmingham",
        "postcode": "B6 4EX",
        "district": "B6",
        "latitude": 52.490428,
        "longitude": -1.889839,
        "url": "https://www.hilti.co.uk/stores/birmingham",
    },
    {
        "name": "Construction Hub Cardiff",
        "city": "Cardiff",
        "postcode": "CF24 5PF",
        "district": "CF24",
        "latitude": 51.47478,
        "longitude": -3.155192,
        "url": "https://www.hilti.co.uk/stores/cardiff",
    },
    {
        "name": "Construction Hub Edinburgh",
        "city": "Edinburgh",
        "postcode": "EH15 1TB",
        "district": "EH15",
        "latitude": 55.965067,
        "longitude": -3.132471,
        "url": "https://www.hilti.co.uk/stores/edinburgh",
    },
    {
        "name": "Construction Hub Edmonton",
        "city": "London",
        "postcode": "N18 3AF",
        "district": "N18",
        "latitude": 51.612631,
        "longitude": -0.047118,
        "url": "https://www.hilti.co.uk/stores/edmonton",
    },
    {
        "name": "Construction Hub Glasgow",
        "city": "Glasgow",
        "postcode": "G5 8SG",
        "district": "G5",
        "latitude": 55.853214,
        "longitude": -4.274367,
        "url": "https://www.hilti.co.uk/stores/glasgow",
    },
    {
        "name": "Construction Hub Liverpool",
        "city": "Liverpool",
        "postcode": "L6 1NA",
        "district": "L6",
        "latitude": 53.412112,
        "longitude": -2.96462,
        "url": "https://www.hilti.co.uk/stores/liverpool",
    },
    {
        "name": "Construction Hub Manchester",
        "city": "Manchester",
        "postcode": "M5 3EY",
        "district": "M5",
        "latitude": 53.467505,
        "longitude": -2.280784,
        "url": "https://www.hilti.co.uk/stores/manchester",
    },
    {
        "name": "Construction Hub Southwark",
        "city": "London",
        "postcode": "SE1 0UE",
        "district": "SE1",
        "latitude": 51.504287,
        "longitude": -0.101739,
        "url": "https://www.hilti.co.uk/stores/southwark",
    },
)


@lru_cache(maxsize=1)
def load_hilti_store_locations() -> pd.DataFrame:
    stores = pd.DataFrame(HILTI_UK_STORES)
    lookup_path = APP_ROOT / "data" / "postcode_district_local_authority_lookup.csv"
    if not lookup_path.exists():
        return stores

    lookup = pd.read_csv(
        lookup_path,
        usecols=["PostDist", "local_authority_code", "local_authority_name"],
    ).rename(columns={"PostDist": "district"})
    lookup["district"] = lookup["district"].astype(str).str.upper().str.strip()
    stores["district"] = stores["district"].astype(str).str.upper().str.strip()
    return stores.merge(lookup, on="district", how="left")
