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

    for key in ("published_parsed",
