# Newsmap

A world map of today's news. Each country shows how many stories mention it; click a
country to see the stories and open the original articles.

The site is free to run. It lives on **GitHub Pages**, and a **GitHub Actions** job
refreshes the news every day by reading RSS feeds from major international outlets
(BBC, Al Jazeera, The Guardian, NPR, DW, France 24, CBC).

## What's in here

| Path | What it does |
|---|---|
| `index.html` | The website: map, country list and sidebar |
| `data/world.json` | Country shapes for the map (Natural Earth, public domain) |
| `data/news.json` | Today's stories. Rewritten automatically every day |
| `scripts/fetch_news.py` | Reads the feeds, decides which countries each story is about, writes `data/news.json` |
| `scripts/feeds.json` | The list of news feeds. Add or remove sources here |
| `scripts/countries.py` | Words that link a headline to a country (names, capitals, cities, leaders) |
| `.github/workflows/update-news.yml` | Runs the update daily and publishes the site |

## Put it online (about 10 minutes)

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository.** Click **+** → **New repository**, name it `newsmap`,
   choose **Public**, and click **Create repository**.
3. **Upload the files.** On the new repository page click **uploading an existing file**,
   then drag in everything from this folder, including the `data`, `scripts` and
   `.github` folders. Click **Commit changes**.
   *The `.github` folder is hidden on Mac and Windows. On Mac press
   Cmd+Shift+. in Finder to show it; on Windows turn on "Hidden items" in File Explorer.*
4. **Turn on GitHub Pages.** Go to **Settings** → **Pages**. Under **Source** choose
   **GitHub Actions**.
5. **Run the first update.** Go to the **Actions** tab. If asked, click
   **I understand my workflows, go ahead and enable them**. Open
   **Update news and publish site** → **Run workflow** → **Run workflow**.
6. **Open your site.** When the run shows a green check (a minute or two), the address
   is shown on the run page and under **Settings → Pages**. It looks like
   `https://YOUR-USERNAME.github.io/newsmap/`.

From then on the news refreshes every day at 11:00 UTC by itself.

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
