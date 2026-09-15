from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import csv
import json
import sys

import feedparser
from dateutil import parser as date_parser

# -----------------------------
# Configuration
# -----------------------------
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "sources_rss.csv"      # fichier CSV contenant les flux RSS et métadonnées
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ARTICLES_FILE = OUTPUT_DIR / "articles_collectes.json"
ERRORS_FILE = OUTPUT_DIR / "erreurs_rss.json"

# Limite le nombre d'articles par média (à ajuster selon besoin)
MAX_ARTICLES_PAR_MEDIA = 3

# -----------------------------
# Helpers
# -----------------------------
def previous_week():
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(days=7)
    end = current_monday - timedelta(days=1)
    return start, end

def load_sources():
    sources = []
    with DATA_FILE.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Attente minimale: chaque ligne doit contenir media, categorie, positionnement, url_rss
            if not row.get("media"):
                continue
            sources.append(row)
    return sources

def get_entry_date(entry):
    # Priorité: published / updated / created
    for field in ("published", "updated", "created"):
        val = entry.get(field)
        if val:
            try:
                dt = date_parser.parse(val)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt.date()
            except Exception:
                pass
    # Fallback: parsing des tuples si présent
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        v = entry.get(field)
        if v:
            try:
                return date(v.tm_year, v.tm_mon, v.tm_mday)
            except Exception:
                pass
    return None

def clean_text(value):
    if not value:
        return ""
    s = str(value).replace("\n", " ").strip()
    # Élimine les espaces superflus
    parts = [p for p in s.split() if p]
    return " ".join(parts)

def collect_source(source, start, end):
    feed = feedparser.parse(source.get("url_rss", ""))
    if feed.bozo and not feed.entries:
        # bozo_exception peut exister; on capture et on lève une erreur
        error = getattr(feed, "bozo_exception", "Flux RSS invalide")
        raise RuntimeError(str(error))

    articles = []
    for entry in feed.entries:
        published_date = get_entry_date(entry)
        if published_date is None:
            continue
        if not (start <= published_date <= end):
            continue

        link = clean_text(entry.get("link", ""))
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", entry.get("description", "")))

        if not title or not link:
            continue

        articles.append({
            "media": source["media"],
            "categorie": source["categorie"],
            "positionnement": source["positionnement"],
            "date": published_date.isoformat(),
            "title": title,
            "url": link,
            "summary_rss": summary[:1000],
        })

    # Trier par date puis par titre, puis limiter au maximum par média
    articles.sort(
        key=lambda it: (it["date"], it["title"]),
        reverse=True
    )
    return articles[:MAX_ARTICLES_PAR_MEDIA]

# -----------------------------
# Main
# -----------------------------
def main():
    start, end = previous_week()
    sources = load_sources()

    all_articles = []
    errors = []

    for source in sources:
        try:
            articles = collect_source(source, start, end)
            if articles:
                all_articles.extend(articles)
            # journalisation légère
            print(f"{source.get('media','?')} : {len(articles)} article(s) retenu(s)")
        except Exception as e:
            errors.append({
                "media": source.get("media","?"),
                "url_rss": source.get("url_rss","?"),
                "error": str(e)
            })
            print(f"{source.get('media','?')} : erreur — {e}")

    # Tri final: on conserve l’ordre par date+titre déjà appliqué, mais on peut faire un tri global par média si nécessaire
    # Sauvegardes
    result = {
        "periode_debut": start.isoformat(),
        "periode_fin": end.isoformat(),
        "nombre_articles": len(all_articles),
        "articles": all_articles
    }

    ARTICLES_FILE = OUTPUT_DIR / "articles_collectes.json"
    ERRORS_FILE = OUTPUT_DIR / "erreurs_rss.json"

    ARTICLES_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ERRORS_FILE.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Total retenu : {len(all_articles)}")
    print(f"Fichier articles : {ARTICLES_FILE}")
    print(f"Fichier erreurs : {ERRORS_FILE}")

if __name__ == "__main__":
    main()
