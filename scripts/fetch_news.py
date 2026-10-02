#!/usr/bin/env python3
"""
Fetch world news from RSS feeds, work out which countries each story is about,
and write data/news.json for the map.

Uses only the Python standard library. Run from the project root:

    python3 scripts/fetch_news.py
"""

from __future__ import annotations

import email.utils
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from countries import ALIASES, IGNORE, SKIP_MAP_NAME  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "data" / "world.json"
OUT = ROOT / "data" / "news.json"
FEEDS = Path(__file__).parent / "feeds.json"

KEEP_HOURS = 36          # stories older than this drop off the map
MAX_PER_COUNTRY = 40     # keeps very busy countries readable
MAX_COUNTRIES_PER_STORY = 3
SUMMARY_CHARS = 240
TIMEOUT = 20
USER_AGENT = "NewsmapBot/1.0 (+https://github.com/)"

# Chinese translation (optional). Set the GEMINI_API_KEY secret to turn it on.
# Only new stories are translated; earlier translations are reused.
MODELS = [m.strip() for m in os.environ.get("NEWSMAP_MODEL", "gemini-flash-lite-latest,gemini-flash-latest").split(",") if m.strip()]
TRANSLATE_BATCH = 20
TRANSLATE_MAX = 400      # safety cap on stories translated per run


# ---------------------------------------------------------------- matching

def build_matcher():
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    valid = {f["id"]: f["properties"]["n"] for f in world["features"]}

    phrases: dict[str, str | None] = {}
    for cid, name in valid.items():
        if cid not in SKIP_MAP_NAME:
            phrases[name] = cid
    for cid, words in ALIASES.items():
        if cid not in valid:
            continue
        for w in words:
            phrases[w] = cid
    for w in IGNORE:
        phrases[w] = None

    # Longest first so "South Sudan" wins over "Sudan".
    ordered = sorted(phrases, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w'’-])(" + "|".join(re.escape(p) for p in ordered) + r")(?:'s|’s)?(?![\w-])"
    )
    return pattern, phrases


PATTERN, PHRASES = build_matcher()


def countries_in(text: str) -> list[str]:
    found: list[str] = []
    for m in PATTERN.finditer(text):
        cid = PHRASES.get(m.group(1))
        if cid and cid not in found:
            found.append(cid)
    return found


def tag(title: str, summary: str) -> list[str]:
    """Countries named in the headline; if none, those in the first sentence."""
    ids = countries_in(title)
    if not ids:
        first = re.split(r"(?<=[.!?])\s", summary, maxsplit=1)[0]
        ids = countries_in(first)
    return ids[:MAX_COUNTRIES_PER_STORY]


# ---------------------------------------------------------------- feeds

def local(tag_name: str) -> str:
    return tag_name.rsplit("}", 1)[-1]


def child_text(el: ET.Element, *names: str) -> str:
    for c in el:
        if local(c.tag) in names:
            if local(c.tag) == "link" and c.get("href"):
                return c.get("href", "")
            return (c.text or "").strip()
    return ""


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > SUMMARY_CHARS:
        text = text[:SUMMARY_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def read_feed(source: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        root = ET.fromstring(r.read())

    items = [el for el in root.iter() if local(el.tag) in ("item", "entry")]
    stories = []
    for it in items:
        title = clean(child_text(it, "title"))
        link = child_text(it, "link", "guid").strip()
        if not title or not link.startswith("http"):
            continue
        summary = clean(child_text(it, "description", "summary", "content"))
        published = parse_date(child_text(it, "pubDate", "published", "updated", "date"))
        stories.append({"t": title, "s": summary, "src": source, "u": link, "d": published})
    return stories


# ---------------------------------------------------------------- translation

PROMPT = """Translate these news headlines and summaries from English into Simplified Chinese.
Use the style of a mainland Chinese news site: concise, neutral and accurate. Use the standard
Chinese names for people, places and organisations; keep names without a common Chinese form in English.
Reply with ONLY a JSON array, one object per input item, in the same order:
[{"i": <same i>, "t": "<Chinese headline>", "s": "<Chinese summary, or empty if none>"}]

Items:
"""


def call_gemini(key: str, model: str, text: str) -> str:
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"maxOutputTokens": 8000, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body, method="POST",
        headers={"x-goog-api-key": key, "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read())
    candidates = data.get("candidates", [])
    if not candidates:
        return ""
    return "".join(
        part.get("text", "")
        for part in candidates[0].get("content", {}).get("parts", [])
        if not part.get("thought")
    )


def translate(stories: list[dict]) -> int:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    todo = [s for s in stories if not s.get("tz")][:TRANSLATE_MAX]
    if not key or not todo:
        if todo:
            print(f"Chinese translation skipped for {len(todo)} stories (no GEMINI_API_KEY).")
        return 0

    done, models = 0, list(MODELS)
    for start in range(0, len(todo), TRANSLATE_BATCH):
        batch = todo[start:start + TRANSLATE_BATCH]
        items = [{"i": n, "t": s["t"], "s": s["s"]} for n, s in enumerate(batch)]
        text = PROMPT + json.dumps(items, ensure_ascii=False)
        while models:
            try:
                reply = call_gemini(key, models[0], text)
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 404) and len(models) > 1:   # model retired or unknown: try the next one
                    print(f"  model {models[0]} unavailable ({e.code}); trying {models[1]}", file=sys.stderr)
                    models.pop(0)
                    continue
                print(f"  translation request failed ({e.code}); continuing without it", file=sys.stderr)
                return done
            except Exception as e:
                print(f"  translation request failed ({e}); continuing without it", file=sys.stderr)
                return done
        else:
            return done
        try:
            m = re.search(r"\[.*\]", reply, re.S)
            rows = json.loads(m.group(0)) if m else []
        except ValueError:
            rows = []
        for row in rows:
            try:
                s = batch[int(row["i"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            if isinstance(row.get("t"), str) and row["t"].strip():
                s["tz"] = row["t"].strip()
                s["sz"] = (row.get("s") or "").strip()
                done += 1
    print(f"Translated {done} new stories into Chinese.")
    return done


# ---------------------------------------------------------------- main

def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def main() -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=KEEP_HOURS)

    previous = {}
    if OUT.exists():
        try:
            for s in json.loads(OUT.read_text(encoding="utf-8")).get("stories", []):
                previous[s["u"]] = s
        except (ValueError, KeyError):
            pass

    feeds = json.loads(FEEDS.read_text(encoding="utf-8"))
    collected, ok = [], 0
    for f in feeds:
        try:
            got = read_feed(f["source"], f["url"])
            collected.extend(got)
            ok += 1
            print(f"  {len(got):>3}  {f['source']}  {f['url']}")
        except Exception as e:  # one broken feed must not stop the update
            print(f"  ERR  {f['source']}  {f['url']}  ({e})", file=sys.stderr)

    if ok == 0:
        print("No feeds could be read; keeping the existing news.json.", file=sys.stderr)
        return 1

    seen_urls, seen_titles, stories = set(), set(), []
    for s in collected:
        key_t = norm_title(s["t"])
        if s["u"] in seen_urls or key_t in seen_titles:
            continue
        seen_urls.add(s["u"])
        seen_titles.add(key_t)

        # Keep the first time we saw an undated story so it ages out properly.
        when = s["d"]
        if when is None:
            old = previous.get(s["u"])
            when = parse_date(old["d"]) if old else now
        if when < cutoff:
            continue

        ids = tag(s["t"], s["s"])
        if not ids:
            continue

        story = {
            "id": hashlib.sha1(s["u"].encode()).hexdigest()[:10],
            "t": s["t"], "s": s["s"], "src": s["src"], "u": s["u"],
            "d": when.isoformat(timespec="minutes"), "c": ids,
        }
        old = previous.get(s["u"])
        if old and old.get("tz") and old.get("t") == s["t"]:
            story["tz"], story["sz"] = old["tz"], old.get("sz", "")
        stories.append(story)

    stories.sort(key=lambda x: x["d"], reverse=True)

    # Cap very busy countries so the sidebar stays usable.
    counts: dict[str, int] = {}
    kept = []
    for s in stories:
        if all(counts.get(c, 0) >= MAX_PER_COUNTRY for c in s["c"]):
            continue
        for c in s["c"]:
            counts[c] = counts.get(c, 0) + 1
        kept.append(s)

    translate(kept)

    OUT.write_text(json.dumps(
        {"updated": now.isoformat(timespec="minutes"), "stories": kept},
        ensure_ascii=False, separators=(",", ":"),
    ), encoding="utf-8")
    print(f"Wrote {len(kept)} stories across {len(counts)} countries from {ok}/{len(feeds)} feeds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
