from __future__ import annotations

from functools import lru_cache

import pandas as pd


# Coordinates are taken from the official Hilti UK store pages' "Get Directions"
# links, which point to Google Maps with exact lat/lon values.
HILTI_UK_STORES: tuple[dict[str, object], ...] = (
    {
        "name": "Hilti Store Belfast",
        "city": "Belfast",
        "postcode": "BT3 9BP",
        "district": "BT3",
        "latitude": 54.6247464,
        "longitude": -5.914934,
        "url": "https://www.hilti.co.uk/stores/belfast",
    },
    {
        "name": "Hilti Store Birmingham",
        "city": "Birmingham",
        "postcode": "B6 4EX",
        "district": "B6",
        "latitude": 52.490428,
        "longitude": -1.889839,
        "url": "https://www.hilti.co.uk/stores/birmingham",
    },
    {
        "name": "Hilti Store Cardiff",
        "city": "Cardiff",
        "postcode": "CF24 5PF",
        "district": "CF24",
        "latitude": 51.47478,
        "longitude": -3.155192,
        "url": "https://www.hilti.co.uk/stores/cardiff",
    },
    {
        "name": "Hilti Store Edinburgh",
        "city": "Edinburgh",
        "postcode": "EH15 1TB",
        "district": "EH15",
        "latitude": 55.965067,
        "longitude": -3.132471,
        "url": "https://www.hilti.co.uk/stores/edinburgh",
    },
    {
        "name": "Hilti Store Edmonton",
        "city": "London",
        "postcode": "N18 3AF",
        "district": "N18",
        "latitude": 51.612631,
        "longitude": -0.047118,
        "url": "https://www.hilti.co.uk/stores/edmonton",
    },
    {
        "name": "Hilti Store Glasgow",
        "city": "Glasgow",
        "postcode": "G5 8SG",
        "district": "G5",
        "latitude": 55.853214,
        "longitude": -4.274367,
        "url": "https://www.hilti.co.uk/stores/glasgow",
    },
    {
        "name": "Hilti Store Liverpool",
        "city": "Liverpool",
        "postcode": "L6 1NA",
        "district": "L6",
        "latitude": 53.412112,
        "longitude": -2.96462,
        "url": "https://www.hilti.co.uk/stores/liverpool",
    },
    {
        "name": "Hilti Store Manchester",
        "city": "Manchester",
        "postcode": "M5 3EY",
        "district": "M5",
        "latitude": 53.467505,
        "longitude": -2.280784,
        "url": "https://www.hilti.co.uk/stores/manchester",
    },
    {
        "name": "Hilti Store Southwark",
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
    return pd.DataFrame(HILTI_UK_STORES)
