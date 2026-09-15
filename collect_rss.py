from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import csv
import json

import feedparser
from dateutil import parser as date_parser


BASE_DIR = Path(__file__).parent
SOURCES_FILE = BASE_DIR / "data" / "sources_rss.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ARTICLES_FILE = OUTPUT_DIR / "articles_collectes.json"
ERRORS_FILE = OUTPUT_DIR / "erreurs_rss.json"

MAX_ARTICLES_PAR_MEDIA = 3

def previous_week():
    """Retourne la période du lundi au dimanche précédents."""
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(days=7)
    end = current_monday - timedelta(days=1)
    return start, end


def load_sources():
    """Charge la liste des flux RSS."""
    with SOURCES_FILE.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def get_entry_date(entry):
    """Retourne la date de publication d'un article RSS, ou None."""
    for field in ("published", "updated", "created"):
        value = entry.get(field)
        if value:
            try:
                parsed = date_parser.parse(value)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed.date()
            except (ValueError, TypeError, OverflowError):
                pass

    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(field)
        if value:
            try:
                return date(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                )
            except (AttributeError, TypeError, ValueError):
                pass

    return None


def clean_text(value):
    """Nettoie légèrement les champs issus du RSS."""
    if not value:
        return ""

    return " ".join(str(value).replace("\n", " ").split())


def collect_source(source, start, end):
    """Télécharge et filtre un flux RSS."""
    parsed_feed = feedparser.parse(source["url_rss"])

    if parsed_feed.bozo and not parsed_feed.entries:
        error = getattr(parsed_feed, "bozo_exception", "Flux invalide")
        raise RuntimeError(str(error))

    articles = []

    for entry in parsed_feed.entries:
        published_date = get_entry_date(entry)

        if published_date is None:
            continue

        if not start <= published_date <= end:
            continue

        link = clean_text(entry.get("link", ""))
        title = clean_text(entry.get("title", ""))
        summary = clean_text(
            entry.get("summary", entry.get("description", ""))
        )

        if not title or not link:
            continue

        articles.append(
            {
                "media": source["media"],
                "categorie": source["categorie"],
                "positionnement": source["positionnement"],
                "date": published_date.isoformat(),
                "title": title,
                "url": link,
                "summary_rss": summary[:1000],
            }
        )

    return articles


def main():
    start, end = previous_week()
    sources = load_sources()

    all_articles = []
    errors = []

    for source in sources:
        try:
            articles = collect_source(source, start, end)
            all_articles.extend(articles)
            print(
                f"{source['media']} : {len(articles)} article(s) "
                f"retenu(s)"
            )
        except Exception as error:
            errors.append(
                {
                    "media": source["media"],
                    "url_rss": source["url_rss"],
                    "error": str(error),
                }
            )
            print(f"{source['media']} : erreur — {error}")

    all_articles.sort(
        key=lambda item: (item["date"], item["media"], item["title"]),
        reverse=True,
    )

    result = {
        "periode_debut": start.isoformat(),
        "periode_fin": end.isoformat(),
        "nombre_articles": len(all_articles),
        "articles": all_articles,
    }

    ARTICLES_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ERRORS_FILE.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Total retenu : {len(all_articles)}")
    print(f"Fichier articles : {ARTICLES_FILE}")
    print(f"Fichier erreurs : {ERRORS_FILE}")


if __name__ == "__main__":
    main()
