# Newsmap

A world map of today's news. Each country shows how many stories mention it; click a
country to see the stories and open the original articles.

The site can run without a paid translation API. It lives on **GitHub Pages**, and a **GitHub Actions** job
refreshes the news every day by reading RSS feeds from major international outlets
(BBC, Al Jazeera, The Guardian, NPR, DW, France 24, CBC).

## What's in here

| Path | What it does |
|---|---|
| `index.html` | The website: map, country list and sidebar |
| `data/world.json` | Country shapes and English/Chinese country names for the map (Natural Earth, public domain) |
| `data/news.json` | Today's stories. Rewritten automatically every day |
| `scripts/fetch_news.py` | Reads the feeds, decides which countries each story is about, writes `data/news.json` |
| `scripts/feeds.json` | The list of news feeds. Add or remove sources here |
| `scripts/countries.py` | Words that link a headline to a country (names, capitals, cities, leaders) |
| `.github/workflows/update-news.yml` | Runs the update daily and publishes the site |

From then on the news refreshes every day at 11:00 UTC by itself.

## Languages: EN, CN, Both

The switch in the top-left corner changes the language. **EN** shows everything in English,
**CN** shows the interface, country names and stories in Simplified Chinese, and **Both** shows
English with Chinese next to every country name, headline and summary. The site remembers each
visitor's choice, starts in Chinese for visitors whose browser is set to Chinese, and you can
share a link that opens in a set language: `…/newsmap/?lang=zh`, `?lang=en` or `?lang=both`.

### Turning on Chinese translation of the news

The news feeds are in English, so the daily job translates new stories into Chinese using the
Google Gemini API. This is optional; without it, CN mode shows the Chinese interface and country names,
with English headlines.

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
   See Google’s [API key guide](https://ai.google.dev/gemini-api/docs/api-key) for setup details.
2. In your GitHub repository go to **Settings → Secrets and variables → Actions →
   New repository secret**. Name it `GEMINI_API_KEY` and paste the key. Click **Add secret**.
3. Run the workflow once from the **Actions** tab. The log shows a line such as
   `Translated 142 new stories into Chinese.`

The workflow passes this secret to the updater as `GEMINI_API_KEY`. For local updates, set
the same environment variable before running `python3 scripts/fetch_news.py`.

Only new stories are translated; earlier translations are reused to reduce API usage.
Costs and quotas depend on your Gemini model and account; check the current
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).
The default model is `gemini-flash-lite-latest`, with `gemini-flash-latest` as a fallback.
You can set `NEWSMAP_MODEL` in the workflow’s **Fetch today’s news** step to a Gemini model
ID or a comma-separated list of model IDs, tried in order if a model is unavailable.
These `latest` aliases can change over time; use a specific model ID if you want to pin a version.
Translations are automatic and can contain mistakes; every story links to the English original.

## Common changes

**Update more often.** In `.github/workflows/update-news.yml` change the cron line.
`"0 */6 * * *"` updates every 6 hours; `"0 * * * *"` every hour.

**Add or remove news sources.** Edit `scripts/feeds.json`. Any RSS or Atom feed works:

```json
{"source": "Name shown on the site", "url": "https://example.com/rss.xml"}
```

**A country is missed or tagged wrongly.** Add or remove words for it in
`scripts/countries.py`. Countries are identified by the ISO numeric codes used in
`data/world.json` (e.g. `"392"` is Japan). Phrases listed in `IGNORE` are never counted.

**How long stories stay.** `KEEP_HOURS` near the top of `scripts/fetch_news.py`
(default 36 hours). `MAX_PER_COUNTRY` caps very busy countries (default 40).

**Use your own domain.** Settings → Pages → Custom domain.

## Preview on your computer

The page loads its data files, so open it through a small local server rather than by
double-clicking:

```bash
python3 scripts/fetch_news.py     # optional: pull fresh news
python3 -m http.server 8000       # then open http://localhost:8000
```

## How stories are matched to countries

For each story the updater looks for country names, nationalities, capitals, major
cities and some leaders in the **headline**. If the headline names no country, it looks
at the first sentence of the summary. A story can belong to up to three countries.
Stories with no clear country are skipped. The matching is simple word matching, so
expect the occasional miss; adjust `countries.py` when you spot one.

## Notes

- Headlines, short summaries and links come from each outlet's public RSS feed, and
  every story links back to the original article. Check each outlet's feed terms if
  you plan to run the site commercially.
- If a feed is down, the rest still update. If every feed fails, the site keeps showing
  the previous day's news.
- Map data: Natural Earth via the `world-atlas` package. Map rendering: D3.
