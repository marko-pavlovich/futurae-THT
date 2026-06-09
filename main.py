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

def main():
    
    args = parse_args()
    
    selected_cities = DEFAULT_CITIES | dict(args.extra_cities)
    print(selected_cities)

if __name__ == "__main__":
    main()
