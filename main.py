import argparse
import os
from datetime import timedelta

import openmeteo_requests
import pandas as pd
import requests
import requests_cache
from rich.console import Console
from rich.table import Table

OUTPUT_DIR = "output"

console = Console()


DEFAULT_CITIES = {
    "zurich": {"latitude": 47.38, "longitude": 8.54},
    "london": {"latitude": 51.51, "longitude": -0.13},
    "new_york": {"latitude": 40.71, "longitude": -74.01},
}

DEFAULT_METRICS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "cloud_cover",
]

ADVANCED_METRICS = DEFAULT_METRICS + [
    "apparent_temperature",
    "relative_humidity_2m",
    "uv_index",
    "wind_gusts_10m",
    "surface_pressure",
]

METRICS_RANGES = {
    "temperature_2m": (-80, 60),
    "precipitation": (0, 500),
    "wind_speed_10m": (0, 200),
    "cloud_cover": (0, 100),
    "apparent_temperature": (-80, 60),
    "relative_humidity_2m": (0, 100),
    "uv_index": (0, 20),
    "wind_gusts_10m": (0, 300),
    "surface_pressure": (800, 1100),
}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_coordinates(city_name: str) -> dict[str, float]:

    # lookup city coordinates using the open-meteo api

    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city_name, "count": 1, "language": "en"},
    )

    response.raise_for_status()

    results = response.json().get("results")
    if not results:
        raise ValueError(f"City {city_name} coordinates not found")

    result = results[0]
    return {
        "latitude": round(result["latitude"], 2),
        "longitude": round(result["longitude"], 2),
    }


def parse_city(city_name: str) -> tuple[str, dict[str, float]]:

    # try to find the city coordinates, either in the defaults, or via API

    if city_name in DEFAULT_CITIES:
        return city_name, DEFAULT_CITIES[city_name]

    try:
        return city_name, get_coordinates(city_name)

    except ValueError:
        raise argparse.ArgumentTypeError(
            f"City '{city_name}' not found in geocoding API"
        )


def parse_args():

    # parse possible arguments, they always default to the task description
    parser = argparse.ArgumentParser(description="Fetch 7-day hourly weather forecast")

    parser.add_argument(
        "--extra-cities",
        nargs="+",
        type=parse_city,
        default=[(name, coords) for name, coords in DEFAULT_CITIES.items()],
        help="Cities to fetch by their name. Default is zurich, london, new_york",
    )

    parser.add_argument(
        "--mode",
        choices=["basic", "advanced"],
        default="basic",
        help="basic: core metrics + cloud cover (default). advanced: extended variable set",
    )

    return parser.parse_args()


def fetch_city(
    client: openmeteo_requests.Client,
    city_name: str,
    city_coords: dict[str, float],
    metrics_params: list[str],
) -> pd.DataFrame:

    # fetch required data for a single city, all the data from metrics_params is included

    params = {
        "latitude": city_coords["latitude"],
        "longitude": city_coords["longitude"],
        "hourly": metrics_params,
        "forecast_days": 7,
    }

    response = client.weather_api(FORECAST_URL, params=params)[0]

    hourly = response.Hourly()

    data = {
        "time": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s"),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s"),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        ),
        "city": city_name,
    }

    for i, var in enumerate(metrics_params):
        data[var] = hourly.Variables(i).ValuesAsNumpy()

    return pd.DataFrame(data)


def fetch_all_data(
    client: openmeteo_requests.Client,
    cities: dict[str, dict[str, float]],
    metrics_params: list[str],
) -> pd.DataFrame:

    # fetch data for all cities, catch an exception if it fails

    frames = []

    for city_name, coords in cities.items():
        try:
            df = fetch_city(
                client=client,
                city_name=city_name,
                city_coords=coords,
                metrics_params=metrics_params,
            )
            frames.append(df)
        except Exception as e:
            print(f"Error when fetching data for city {city_name} - {e}")

    if not frames:
        raise RuntimeError("No data fetched - all cities failed")
    return pd.concat(frames, ignore_index=True)


def clean_data(df: pd.DataFrame) -> pd.DataFrame:

    # convert to appropriate datatypes and impute missing values

    df["time"] = pd.to_datetime(df["time"])
    df["city"] = df["city"].astype(str)

    numeric_cols = [col for col in df.columns if col not in ("time", "city")]
    df[numeric_cols] = df[numeric_cols].astype(float)

    missing = df.isnull().sum()
    if missing.any():
        print(f"Warning: missing values found:\n{missing[missing>0]} ")
        print(f"Imputed with mean")
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())

    return df


def validate_data(df: pd.DataFrame):

    # validate the values received from the api

    invalidations = []

    for metric, (low, high) in METRICS_RANGES.items():

        if metric not in df.columns:
            continue

        out_of_range = ~df[metric].between(low, high)

        if out_of_range.any():
            invalidations.append(
                f"{metric}: {out_of_range.sum()} values out of range [{low}, {high}]"
            )

    if invalidations:
        print("Validation warnings")
        for invalidation in invalidations:
            print(invalidation)

    else:
        print("Validation passed")


def print_summary(df: pd.DataFrame, mode: str = "basic"):

    avg_temp = df.groupby("city")["temperature_2m"].mean().round(2)
    total_precip = df.groupby("city")["precipitation"].sum().round(2)
    coldest_row = df.loc[df["temperature_2m"].idxmin()]

    table = Table(title="7-day weather summary")
    table.add_column("city", style="bold")
    table.add_column("avg temp (°C)", justify="right")
    table.add_column("total precip (mm)", justify="right")

    if mode == "advanced":
        avg_wind = df.groupby("city")["wind_speed_10m"].mean().round(2)
        avg_humidity = df.groupby("city")["relative_humidity_2m"].mean().round(2)
        max_uv = df.groupby("city")["uv_index"].max().round(2)
        max_gusts = df.groupby("city")["wind_gusts_10m"].max().round(2)
        avg_feels_like = df.groupby("city")["apparent_temperature"].mean().round(2)

        table.add_column("avg wind (km/h)", justify="right")
        table.add_column("avg humidity (%)", justify="right")
        table.add_column("max uv index", justify="right")
        table.add_column("max gusts (km/h)", justify="right")
        table.add_column("feels like (°C)", justify="right")

    for city in avg_temp.index:
        row = [city, str(avg_temp[city]), str(total_precip[city])]
        if mode == "advanced":
            row.extend(
                [
                    str(avg_wind[city]),
                    str(avg_humidity[city]),
                    str(max_uv[city]),
                    str(max_gusts[city]),
                    str(avg_feels_like[city]),
                ]
            )
        table.add_row(*row)

    console.print(table)
    console.print(
        f"\n[bold]coldest hour:[/bold] {coldest_row['city']} at {coldest_row['time']} — {round(coldest_row['temperature_2m'], 2)}°C\n"
    )


def main():

    args = parse_args()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    cache_session = requests_cache.CachedSession(
        ".cache", expire_after=timedelta(hours=6)
    )
    client = openmeteo_requests.Client(session=cache_session)

    selected_cities = DEFAULT_CITIES | dict(args.extra_cities)

    metrics = ADVANCED_METRICS if args.mode == "advanced" else DEFAULT_METRICS
    df = fetch_all_data(client=client, cities=selected_cities, metrics_params=metrics)

    df_cleaned = clean_data(df=df)

    validate_data(df=df_cleaned)

    cities_str = "_".join(sorted(selected_cities.keys()))
    timestamp = df["time"].min().strftime("%Y%m%d")
    filename = f"weather_{cities_str}_{args.mode}_{timestamp}.csv"
    df_cleaned.to_csv(f"{OUTPUT_DIR}/{filename}", index=False)
    print(f"Data can be found at {OUTPUT_DIR}/{filename}\n")

    print_summary(df_cleaned, mode=args.mode)


if __name__ == "__main__":
    main()
