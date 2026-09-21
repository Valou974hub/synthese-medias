from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import yaml
from dateutil import parser as date_parser


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "media.yml"
DATA_DIR = ROOT / "data"
PARIS = ZoneInfo("Europe/Paris")


def clean_text(value: str | None) -> str:
    """Convertit un extrait HTML de flux RSS en texte court et lisible."""
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalise_title(value: str) -> str:
    """Normalise un titre pour limiter les doublons entre flux."""
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿñæœ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_entry_date(entry: Any) -> datetime | None:
    """Lit les principaux champs de date fournis par les flux RSS/Atom."""
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue

        try:
            parsed = date_parser.parse(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=PARIS)
            return parsed.astimezone(PARIS)
        except (ValueError, TypeError, OverflowError):
            continue

    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(
                    parsed.tm_year,
                    parsed.tm_mon,
                    parsed.tm_mday,
                    parsed.tm_hour,
                    parsed.tm_min,
                    parsed.tm_sec,
                    tzinfo=PARIS,
                )
            except (AttributeError, TypeError, ValueError):
                continue

    return None


def previous_complete_week(reference: datetime | None = None) -> tuple[date, date]:
    """
    Renvoie la semaine civile complète précédente : lundi à dimanche.

    Exemple : exécuté le lundi 21 septembre, le rapport couvre
    le lundi 14 septembre au dimanche 20 septembre inclus.
    """
    current = reference or datetime.now(PARIS)
    today = current.date()
    this_monday = today - timedelta(days=today.weekday())
    previous_monday = this_monday - timedelta(days=7)
    previous_sunday = this_monday - timedelta(days=1)
    return previous_monday, previous_sunday


def requested_period(args: argparse.Namespace) -> tuple[date, date]:
    """Permet aussi un lancement manuel avec --start et --end."""
    if bool(args.start) != bool(args.end):
        raise ValueError("--start et --end doivent être utilisés ensemble.")

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        if end < start:
            raise ValueError("La date de fin doit être postérieure à la date de début.")
        return start, end

    return previous_complete_week()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration introuvable : {path}")

    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}

    if not isinstance(content, dict):
        raise ValueError("Le fichier de configuration YAML est invalide.")

    return content


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def collect_from_feed(media: dict[str, Any], feed_url: str, start: date, end: date) -> list[dict[str, Any]]:
    """Collecte les entrées RSS/Atom du média appartenant à la période."""
    collected: list[dict[str, Any]] = []

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:  # feedparser ne laisse normalement pas remonter d'exception.
        print(f"[WARN] Flux inaccessible pour {media['name']} : {exc}", file=sys.stderr)
        return collected

    if getattr(feed, "bozo", False):
        error = getattr(feed, "bozo_exception", "format RSS/Atom incertain")
        print(f"[WARN] Flux possiblement invalide pour {media['name']} : {error}", file=sys.stderr)

    for entry in getattr(feed, "entries", []):
        published = parse_entry_date(entry)
        if not published or not (start <= published.date() <= end):
            continue

        title = clean_text(entry.get("title", ""))
        url = str(entry.get("link", "")).strip()
        if not title or not url:
            continue

        description = clean_text(
            entry.get("summary")
            or entry.get("description")
            or entry.get("content", [{}])[0].get("value", "")
        )

        collected.append(
            {
                "media": media["name"],
                "slug": media["slug"],
                "category": media["category"],
                "orientation": media["orientation"],
                "title": title,
                "url": url,
                "published_at": published.isoformat(),
                "published_date": published.date().isoformat(),
                "summary": description[:800],
                "source_type": "rss",
                "feed_url": feed_url,
                "topics": [],
            }
        )

    return collected


def collect_media(media: dict[str, Any], start: date, end: date) -> tuple[list[dict[str, Any]], str]:
    """
    Retourne les contenus retenus et un statut de collecte.

    Les médias sans flux restent dans le rapport : ils sont signalés plutôt que
    remplacés par des titres non vérifiés.
    """
    feeds = media.get("rss") or []
    all_entries: list[dict[str, Any]] = []

    for feed_url in feeds:
        all_entries.extend(collect_from_feed(media, feed_url, start, end))

    unique: dict[str, dict[str, Any]] = {}
    title_keys: set[str] = set()

    for article in sorted(all_entries, key=lambda row: row["published_at"], reverse=True):
        url = article["url"]
        title_key = normalise_title(article["title"])

        if url in unique or title_key in title_keys:
            continue

        unique[url] = article
        title_keys.add(title_key)

    selected = list(unique.values())[: int(media.get("max_items", 3))]

    if selected:
        return selected, "found"

    collection = media.get("collection", "archive")
    fallback_statuses = {
        "replay": "replay_to_check",
        "archive": "archive_to_check",
        "rss_or_archive": "archive_to_check",
    }
    return [], fallback_statuses.get(collection, "not_found")


def load_known_urls(cumulative: dict[str, Any]) -> set[str]:
    """Reconstruit l'ensemble des URL déjà comptabilisées."""
    known: set[str] = set()

    for media_data in cumulative.get("media", {}).values():
        for url in media_data.get("known_urls", []):
            known.add(url)

    return known


def update_cumulative(
    configuration: dict[str, Any],
    cumulative: dict[str, Any],
    articles: list[dict[str, Any]],
    statuses: dict[str, str],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Met à jour le cumul sans compter deux fois une URL déjà archivée."""
    cumulative.setdefault("media", {})
    cumulative.setdefault("history", [])

    known_urls = load_known_urls(cumulative)
    by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for article in articles:
        by_slug[article["slug"]].append(article)

    weekly_summary: list[dict[str, Any]] = []

    for media in configuration.get("media", []):
        slug = media["slug"]
        entry = cumulative["media"].setdefault(
            slug,
            {
                "name": media["name"],
                "category": media["category"],
                "orientation": media["orientation"],
                "total_articles": 0,
                "weeks_with_content": 0,
                "last_seen": None,
                "known_urls": [],
            },
        )

        weekly_articles = by_slug.get(slug, [])
        new_articles = [row for row in weekly_articles if row["url"] not in known_urls]

        if new_articles:
            entry["total_articles"] += len(new_articles)
            entry["weeks_with_content"] += 1
            entry["last_seen"] = max(row["published_date"] for row in weekly_articles)
            entry["known_urls"].extend(row["url"] for row in new_articles)
            known_urls.update(row["url"] for row in new_articles)

        weekly_summary.append(
            {
                "slug": slug,
                "name": media["name"],
                "category": media["category"],
                "orientation": media["orientation"],
                "article_count": len(weekly_articles),
                "has_article_this_week": bool(weekly_articles),
                "status": statuses[slug],
                "total_articles": entry["total_articles"],
            }
        )

    cumulative["history"].append(
        {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "generated_at": datetime.now(PARIS).isoformat(),
            "media": weekly_summary,
        }
    )

    # Garde les 104 dernières semaines, soit environ deux ans de suivi.
    cumulative["history"] = cumulative["history"][-104:]
    return cumulative


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collecte hebdomadaire d'articles RSS pour la synthèse des médias."
    )
    parser.add_argument("--start", help="Début de période au format YYYY-MM-DD")
    parser.add_argument("--end", help="Fin de période au format YYYY-MM-DD")
    args = parser.parse_args()

    start, end = requested_period(args)
    configuration = load_yaml(CONFIG_PATH)

    DATA_DIR.mkdir(exist_ok=True)
    articles: list[dict[str, Any]] = []
    statuses: dict[str, str] = {}

    for media in configuration.get("media", []):
        media_articles, status = collect_media(media, start, end)
        articles.extend(media_articles)
        statuses[media["slug"]] = status
        print(f"[INFO] {media['name']}: {len(media_articles)} article(s), statut={status}")

    articles.sort(
        key=lambda row: (row["media"], row["published_at"], row["title"]),
        reverse=False,
    )

    report_payload = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "generated_at": datetime.now(PARIS).isoformat(),
        "timezone": "Europe/Paris",
        "articles": articles,
        "media_statuses": statuses,
    }

    weekly_path = DATA_DIR / f"articles_{start.isoformat()}_{end.isoformat()}.json"
    save_json(weekly_path, report_payload)

    cumulative_path = DATA_DIR / "cumulative.json"
    cumulative = load_json(cumulative_path, {"media": {}, "history": []})
    cumulative = update_cumulative(configuration, cumulative, articles, statuses, start, end)
    save_json(cumulative_path, cumulative)

    print(f"[INFO] Fichier hebdomadaire écrit : {weekly_path}")
    print(f"[INFO] Suivi cumulatif mis à jour : {cumulative_path}")
    print(f"[INFO] Total d'articles retenus : {len(articles)}")


if __name__ == "__main__":
    main()
