import argparse

import numpy as np
import pandas as pd
import openmeteo_requests
import requests

OUTPUT_DIR = "output"


DEFAULT_CITIES = {
    "zurich":   {"latitude": 47.38, "longitude": 8.54},
    "london":   {"latitude": 51.51, "longitude": -0.13},
    "new_york": {"latitude": 40.71, "longitude": -74.01},
}

DEFAULT_METRICS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "cloud_cover",
]

METRICS_RANGES = {
    "temperature_2m":       (-80, 60),
    "precipitation":        (0, 500),
    "wind_speed_10m":       (0, 200),
    "cloud_cover":          (0, 100),
}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

def get_coordinates(city_name):
    
    # lookup city coordinates using the open-meteo api
    
    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city_name, "count": 1, "language": "en"}
    )
    
    response.raise_for_status()
    
    results = response.json().get("results")
    if not results:
        raise ValueError(f"City {city_name} coordinates not found")

    result = results[0]
    return {"latitude": round(result["latitude"], 2), "longitude": round(result["longitude"], 2)}
    

def parse_city(city_name):
    
    # try to find the city coordinates, either in the defaults, or via API
    
    if city_name in DEFAULT_CITIES:
        return city_name, DEFAULT_CITIES[city_name]
    
    try:
        return city_name, get_coordinates(city_name)
    
    except ValueError:
        raise argparse.ArgumentTypeError(f"City '{city_name}' not found in geocoding API")
    
    

def parse_args():
    
    # parse possible arguments, they always default to the task description 
    parser = argparse.ArgumentParser(description="Fetch 7-day hourly weather forecast")
    
    parser.add_argument(
        "--extra-cities",
        nargs="+",
        type= parse_city,
        default=[(name, coords) for name,coords in DEFAULT_CITIES.items()],
        help="Cities to fetch by their name. Default is zurich, london, new_york"
        )
    
    return parser.parse_args()

def fetch_city(client, city_name, city_coords, metrics_params):
    
    # fetch required data for a single city, all the data from metrics_params is included
    
    params = {
        "latitude" : city_coords["latitude"],
        "longitude" : city_coords["longitude"],
        "hourly" : metrics_params,
        "forecast_days" : 7
    }
    
    response = client.weather_api(FORECAST_URL, params=params)[0]
    
    hourly = response.Hourly()
    
    data = {"time": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s"),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s"),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left"
    ), "city": city_name}
    
    for i, var in enumerate(metrics_params):
        data[var] = hourly.Variables(i).ValuesAsNumpy()
    
    return pd.DataFrame(data)

def fetch_all_data(client, cities, metrics_params):
    
    # fetch data for all cities, catch an exception if it fails
    
    frames = []
    
    for city_name, coords in cities.items():
        try:
            df = fetch_city(client=client, city_name=city_name, city_coords=coords, metrics_params=metrics_params)
            frames.append(df)
        except Exception as e:
            print(f"Error when fetching data for city {city_name} - {e}")
    
    if not frames:
        raise RuntimeError("No data fetched - all cities failed")    
    return pd.concat(frames, ignore_index=True)   
    
def clean_data(df):
    
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

def validate_data(df):
    
    invalidations = []
    
    for metric, (low, high) in METRICS_RANGES.items():
        
        if metric not in df.columns:
            continue
        
        out_of_range = out_of_range = ~df[metric].between(low, high)
        
        if out_of_range.any():
            invalidations.append(f"{metric}: {out_of_range.sum()} values out of range [{low}, {high}]")
        
    if invalidations:
        print("Validation warnings")
        for invalidation in invalidations:
            print(invalidation)
    
    else:
        print("Validation passed")
        
        
def main():
    
    args = parse_args()
    
    client = openmeteo_requests.Client()
    
    selected_cities = DEFAULT_CITIES | dict(args.extra_cities)
    
    df = fetch_all_data(client=client, cities=selected_cities, metrics_params=DEFAULT_METRICS)
    df_cleaned = clean_data(df=df)
    
    validate_data(df=df_cleaned)
    
    print(df_cleaned)
    
if __name__ == "__main__":
    main()
