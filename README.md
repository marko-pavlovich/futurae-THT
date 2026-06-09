# futurae-THT

[Skip to design choices](#choices)
## Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repo

```bash
git clone https://github.com/marko-pavlovich/futurae-THT.git
cd futurae-THT
```

### 3. Set up the environment

```bash
uv venv
source .venv/bin/activate 
uv sync
```

### 4. Run

```bash
python main.py
```

## Usage

```bash
# default: zurich, london, new_york — basic metrics
python main.py

# add extra cities by name
python main.py --extra-cities paris tokyo

# advanced metrics
python main.py --mode advanced

# combine
python main.py --extra-cities sydney berlin --mode advanced
```

## Output

Results are saved to `output/weather_{cities}_{mode}_{date}.csv`. A summary table with the needed metrics is printed to the console.

## Choices

- **Graceful city failure** - if one city's API call fails, the script logs a warning and continues with the remaining cities.
- **Open-Meteo `best_match` model** - automatically selects the best available model per location, ensuring consistent data across all three cities without hardcoding a regional model. (This is the default for the client calls)
- **Missing value imputation** - null values are filled with the column mean and logged. Open-Meteo rarely returns nulls with `best_match`, but the handling is explicit.
- **6-hour cache** - API responses are cached for 6 hours via `requests-cache`, matching Open-Meteo's global model update frequency and avoiding redundant calls during repeated runs.
- **`rich` for terminal output** - used for readable, formatted console tables instead of raw print statements.
- **Added additional features** - added options to include more cities, and to have a more advanced overview of the weather data, the console is dynamically updated for both cases

## Things I would improve

Add retry logic with exponential backoff for failed city requests, to distinguish transient network errors from actual API unavailability, and optionally fall back to the last cached response or to a different source. Also, allow for custom but known selection of more metrics to be considered. Finally, add timezone conversion per city for display purposes - currently all timestamps are in UTC, which is consistent for downstream comparisons but less intuitive for end users.

## LLM usage

See README analysis section below.

## Analysis task

1. I used Claude to speed up writing the code in some parts. For example, I prompted it to provide argparse descriptions and standard format, and I prompted it to provide me with a common tidy terminal output format. At the end, I used it to help me format this README. At each step, I verified the contents of the code by eye and also reviewed the output of the new code.

2. I would say that temperature is a bad metric to summarize 7 days of data for a city. Although it is one of the things people mostly care about, it still hides a lot of information. First, the 7 days is relatively a long time to consider the average, especially in changeable seasons such as spring or late summer. Additionally, other metrics such as rain precipitation, cloud coverage, relative humidity, or wind paint a fuller picture of what the weather was like.

3. The cities have a relatively similar moderate climate. We can try to connect the data more for London and Zurich, as they are in Europe, while NY is in North America. Additionally, as these are very popular cities, we can expect the data to be provided with high availability and with good accuracy, as they are well-covered by weather station infrastructure. In some less covered areas, we would need to have different policies for fallbacks.

4. If I had to choose one, I would opt for the graph. There, we could plot the data moving across the seven days, so we do not have to rely on averages and maxes. Tables are useful for further computations and analytics, while maps would be good for a user-side view, if the product were incorporated in such an app.

5. In the code, there is a graceful failure already implemented. When one of the city's API calls fails, the program continues for other cities. However, this approach ultimately does not provide the requested data. As mentioned in the improvements part, we could try to address the cause of this problem, and then, according to that, either return the cached data with a disclaimer, or have a fallback API where we could resort to.

6. For this simple case, I would run this script as a cron job, for example, every day at 6 am. Using `crontab`, I would schedule it as:

   ```bash
    0 6 * * * cd /path/to/futurae && .venv/bin/python main.py >> logs/cron.log 2>&1
   ```
   For a more complex pipeline, I would use an external orchestration service like Airflow or similar.

7. The first thing that came to my mind was privacy and data protection. Since the weather is publicly available, there is little harm in mismanaging it. However, for user data, I would follow the procedures that are present in each of the countries/territories. Additionally, imputing the data is also not possible, as those are real, meaningful facts about a person, whereas here it was merely an average of very changing weather metrics. Also, the results would be more safely saved, for example, on a trusted storage platform, and possibly sent in an encrypted fashion.