from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "media.yml"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PAGE_WIDTH, _ = A4

BLUE = HexColor("#183a63")
LIGHT_BLUE = HexColor("#d9e8f2")
BORDER = HexColor("#9aa9b5")
GREEN = HexColor("#d9ecd3")
RED = HexColor("#f1cccc")
GREY = HexColor("#666666")

FONT_REGULAR_CANDIDATES = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
]
FONT_BOLD_CANDIDATES = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
]


def find_font(candidates: list[Path]) -> Path | None:
    """Renvoie la première police disponible sur le runner GitHub."""
    return next((path for path in candidates if path.exists()), None)


def configure_fonts() -> tuple[str, str]:
    """Enregistre une police Unicode afin que les accents français soient affichés."""
    regular = find_font(FONT_REGULAR_CANDIDATES)
    bold = find_font(FONT_BOLD_CANDIDATES)

    if regular and bold:
        pdfmetrics.registerFont(TTFont("MediaSans", str(regular)))
        pdfmetrics.registerFont(TTFont("MediaSansBold", str(bold)))
        return "MediaSans", "MediaSansBold"

    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = configure_fonts()
STYLES = getSampleStyleSheet()

STYLES.add(
    ParagraphStyle(
        name="ReportTitle",
        parent=STYLES["Title"],
        fontName=FONT_BOLD,
        fontSize=21,
        leading=26,
        alignment=TA_CENTER,
        textColor=BLUE,
        spaceAfter=12,
    )
)
STYLES.add(
    ParagraphStyle(
        name="ReportSubtitle",
        parent=STYLES["BodyText"],
        fontName=FONT,
        fontSize=13,
        leading=17,
        alignment=TA_CENTER,
        textColor=GREY,
        spaceAfter=16,
    )
)
STYLES.add(
    ParagraphStyle(
        name="SectionTitle",
        parent=STYLES["Heading1"],
        fontName=FONT_BOLD,
        fontSize=16,
        leading=20,
        textColor=BLUE,
        spaceBefore=8,
        spaceAfter=8,
    )
)
STYLES.add(
    ParagraphStyle(
        name="SubsectionTitle",
        parent=STYLES["Heading2"],
        fontName=FONT_BOLD,
        fontSize=12.5,
        leading=16,
        textColor=HexColor("#315c88"),
        spaceBefore=8,
        spaceAfter=5,
    )
)
STYLES.add(
    ParagraphStyle(
        name="BodyFrench",
        parent=STYLES["BodyText"],
        fontName=FONT,
        fontSize=8.8,
        leading=12,
        spaceAfter=5,
    )
)
STYLES.add(
    ParagraphStyle(
        name="SmallFrench",
        parent=STYLES["BodyText"],
        fontName=FONT,
        fontSize=7.1,
        leading=9,
    )
)
STYLES.add(
    ParagraphStyle(
        name="CellFrench",
        parent=STYLES["BodyText"],
        fontName=FONT,
        fontSize=7.1,
        leading=9,
    )
)
STYLES.add(
    ParagraphStyle(
        name="CellFrenchBold",
        parent=STYLES["BodyText"],
        fontName=FONT_BOLD,
        fontSize=7.1,
        leading=9,
    )
)


def paragraph(text: str, style: str = "BodyFrench") -> Paragraph:
    """Protège les caractères utilisés dans le mini-HTML de ReportLab."""
    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("\n", "<br/>")
    return Paragraph(text, STYLES[style])


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return default


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_period(args: argparse.Namespace) -> tuple[date, date, Path]:
    """Trouve le JSON hebdomadaire demandé, ou le plus récent disponible."""
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        path = DATA_DIR / f"articles_{start.isoformat()}_{end.isoformat()}.json"
        if not path.exists():
            raise FileNotFoundError(f"Fichier de données introuvable : {path}")
        return start, end, path

    candidates = sorted(DATA_DIR.glob("articles_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "Aucun fichier articles_YYYY-MM-DD_YYYY-MM-DD.json n'a été trouvé. "
            "Exécutez d'abord collect_rss.py."
        )

    path = candidates[-1]
    match = re.search(r"articles_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$", path.name)
    if not match:
        raise ValueError(f"Nom de fichier hebdomadaire inattendu : {path.name}")

    return date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2)), path


def format_date_range(start: date, end: date) -> str:
    months = [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]

    if start.year == end.year and start.month == end.month:
        return f"du {start.day} au {end.day} {months[start.month]} {start.year}"

    if start.year == end.year:
        return f"du {start.day} {months[start.month]} au {end.day} {months[end.month]} {start.year}"

    return f"du {start.day} {months[start.month]} {start.year} au {end.day} {months[end.month]} {end.year}"


def short_url(url: str) -> str:
    """Conserve un lien lisible sans augmenter excessivement la hauteur des cellules."""
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}".replace("www.", "")[:95]
    except ValueError:
        return url[:95]


def article_cell(articles: list[dict[str, Any]], status: str) -> str:
    """Fabrique la cellule éditoriale d'un tableau de médias."""
    if not articles:
        messages = {
            "archive_to_check": "Aucun contenu individuel RSS vérifié ; archives du média à consulter.",
            "replay_to_check": "Contenu audiovisuel à vérifier dans les replays ou archives.",
            "not_found": "Aucun contenu individuel accessible identifié dans la période.",
        }
        return messages.get(status, "Aucun contenu individuel accessible identifié dans la période.")

    parts: list[str] = []
    for article in articles:
        title = article.get("title", "Sans titre")
        published = article.get("published_date", "")
        summary = article.get("summary", "").strip()
        url = article.get("url", "")

        item = f"<b>{title}</b>"
        if published:
            item += f" — {published}"
        if summary:
            item += f"<br/>{summary[:220]}"
        if url:
            item += f"<br/><font color='#1b6ca8'>{short_url(url)}</font>"
        parts.append(item)

    return "<br/><br/>".join(parts)


def build_media_table(rows: list[dict[str, Any]]) -> Table:
    data: list[list[Paragraph]] = [
        [
            paragraph("Média", "CellFrenchBold"),
            paragraph("Orientation retenue", "CellFrenchBold"),
            paragraph("Article / vidéo de la période", "CellFrenchBold"),
        ]
    ]

    for row in rows:
        data.append(
            [
                paragraph(row["name"], "CellFrench"),
                paragraph(row["orientation"], "CellFrench"),
                paragraph(article_cell(row["articles"], row["status"]), "CellFrench"),
            ]
        )

    table = Table(
        data,
        colWidths=[34 * mm, 46 * mm, 105 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
                ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def orientation_group(media: dict[str, Any]) -> str:
    """
    Classe les médias non indépendants en deux encarts indicatifs.
    Les médias explicitement de gauche ou de service public sont dans le premier.
    """
    orientation = media.get("orientation", "").lower()
    left_markers = ("gauche", "progressiste", "internationaliste", "service public", "communiste")
    return "gauche" if any(marker in orientation for marker in left_markers) else "droite"


def infer_topics(articles: list[dict[str, Any]], topics: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Classement simple et transparent par mots-clés, sans prétendre inférer une ligne éditoriale."""
    keywords = {
        "économie et social": (
            "budget", "dette", "inflation", "salaire", "emploi", "travail",
            "pouvoir d'achat", "carburant", "énergie", "grève", "social",
        ),
        "politique et démocratie": (
            "présidentielle", "élection", "gouvernement", "parlement", "parti",
            "macron", "rn", "lfi", "politique", "démocratie",
        ),
        "sécurité et justice pénale": (
            "police", "justice", "procès", "prison", "terrorisme", "sécurité",
            "crime", "violence", "attentat",
        ),
        "monde et Europe": (
            "ukraine", "russie", "europe", "ue", "israël", "gaza", "iran",
            "moyen-orient", "international", "otan",
        ),
        "écologie": (
            "climat", "écologie", "sécheresse", "canicule", "eau", "pesticide",
            "biodiversité", "pollution", "environnement",
        ),
        "numérique et IA": (
            "ia", "intelligence artificielle", "numérique", "réseaux sociaux",
            "plateforme", "internet", "données", "algorithme",
        ),
        "culture et médias": (
            "culture", "cinéma", "musique", "livre", "télévision", "média",
            "journalisme", "radio", "artiste",
        ),
    }

    grouped = {topic: [] for topic in topics}

    for article in articles:
        haystack = " ".join(
            [
                article.get("title", ""),
                article.get("summary", ""),
            ]
        ).lower()

        matched = False
        for topic in topics:
            if any(word in haystack for word in keywords.get(topic, ())):
                grouped[topic].append(article)
                matched = True

        if not matched:
            grouped["politique et démocratie"].append(article)

    return grouped


def topic_paragraph(topic: str, articles: list[dict[str, Any]]) -> str:
    if not articles:
        return (
            "Les contenus RSS disponibles ne font pas ressortir de sujet représentatif "
            "pour cette rubrique pendant la période."
        )

    counter = Counter(article.get("media", "") for article in articles)
    media_names = ", ".join(name for name, _ in counter.most_common(4) if name)
    titles = "; ".join(article.get("title", "") for article in articles[:3])

    return (
        f"Les contenus collectés font notamment ressortir : {titles}. "
        f"Médias représentés : {media_names}."
    )


def build_tracking_table(cumulative: dict[str, Any], weekly_rows: list[dict[str, Any]]) -> Table:
    by_slug = {row["slug"]: row for row in weekly_rows}
    all_rows = sorted(
        weekly_rows,
        key=lambda row: (not row["has_article_this_week"], row["name"].lower()),
    )

    data: list[list[Paragraph]] = [
        [
            paragraph("Média", "CellFrenchBold"),
            paragraph("Catégorie", "CellFrenchBold"),
            paragraph("Positionnement indicatif", "CellFrenchBold"),
            paragraph("Cumul d’articles", "CellFrenchBold"),
            paragraph("Au moins un article cette semaine", "CellFrenchBold"),
        ]
    ]

    row_backgrounds: list[tuple[int, colors.Color]] = []

    for index, row in enumerate(all_rows, start=1):
        media_total = cumulative.get("media", {}).get(row["slug"], {}).get("total_articles", 0)
        found = row["has_article_this_week"]
        data.append(
            [
                paragraph(row["name"], "CellFrench"),
                paragraph("Indépendant" if row["category"] == "independent" else "Non indépendant", "CellFrench"),
                paragraph(row["orientation"], "CellFrench"),
                paragraph(str(media_total), "CellFrench"),
                paragraph("Oui" if found else "Non", "CellFrench"),
            ]
        )
        row_backgrounds.append((index, GREEN if found else RED))

    table = Table(
        data,
        colWidths=[39 * mm, 32 * mm, 65 * mm, 23 * mm, 31 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )

    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for index, colour in row_backgrounds:
        commands.append(("BACKGROUND", (4, index), (4, index), colour))

    table.setStyle(TableStyle(commands))
    return table


def footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(15 * mm, 10 * mm, "Synthèse des médias français — rapport hebdomadaire")
    canvas.drawRightString(195 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère le PDF détaillé de synthèse des médias."
    )
    parser.add_argument("--start", help="Début de période YYYY-MM-DD")
    parser.add_argument("--end", help="Fin de période YYYY-MM-DD")
    args = parser.parse_args()

    start, end, weekly_path = resolve_period(args)
    configuration = load_yaml(CONFIG_PATH)
    weekly = load_json(weekly_path, {})
    cumulative = load_json(DATA_DIR / "cumulative.json", {"media": {}, "history": []})

    articles = weekly.get("articles", [])
    statuses = weekly.get("media_statuses", {})

    articles_by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        articles_by_slug[article.get("slug", "")].append(article)

    media_rows: list[dict[str, Any]] = []
    for media in configuration.get("media", []):
        slug = media["slug"]
        media_rows.append(
            {
                "slug": slug,
                "name": media["name"],
                "category": media["category"],
                "orientation": media["orientation"],
                "articles": articles_by_slug.get(slug, []),
                "status": statuses.get(slug, "not_found"),
                "has_article_this_week": bool(articles_by_slug.get(slug, [])),
            }
        )

    independent_rows = [row for row in media_rows if row["category"] == "independent"]
    non_independent_rows = [row for row in media_rows if row["category"] == "non_independent"]
    left_rows = [row for row in non_independent_rows if orientation_group(row) == "gauche"]
    right_rows = [row for row in non_independent_rows if orientation_group(row) == "droite"]

    topics = configuration.get("topics", [])
    grouped_topics = infer_topics(articles, topics)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / f"synthese_medias_{start.isoformat()}_{end.isoformat()}.pdf"

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title="Synthèse des médias français",
        author="Synthèse médias",
    )

    story: list[Any] = []

    story.extend(
        [
            paragraph("Synthèse des médias en France", "ReportTitle"),
            paragraph(f"Semaine {format_date_range(start, end)}", "ReportSubtitle"),
            paragraph(
                f"Document généré le {datetime.now().strftime('%d/%m/%Y')} à partir des flux et archives configurés.",
                "BodyFrench",
            ),
            Spacer(1, 8),
            paragraph("Préambule — méthode", "SectionTitle"),
            paragraph(
                "Ce document compare les sujets et angles éditoriaux mis en avant par les médias "
                "pendant la période observée. Les catégories « indépendant » et « non indépendant » "
                "sont utilisées au sens structurel et pratique ; elles ne mesurent pas la qualité, "
                "la fiabilité ou la neutralité d’un contenu. Les positionnements politiques sont indicatifs.",
            ),
            paragraph(
                "La collecte automatique privilégie les flux RSS. Pour les médias ne disposant pas "
                "d’un flux configuré, le rapport affiche explicitement « archives à consulter » ou "
                "« replay à vérifier », afin de ne pas attribuer de contenu non vérifié.",
            ),
            paragraph("Actualité transversale de la semaine", "SectionTitle"),
            paragraph(
                f"La collecte a retenu {len(articles)} contenu(s) individuels provenant de "
                f"{sum(1 for row in media_rows if row['has_article_this_week'])} média(s). "
                "Les thèmes ci-dessous reflètent uniquement les contenus effectivement collectés.",
            ),
        ]
    )

    for topic in topics:
        topic_articles = grouped_topics.get(topic, [])
        if topic_articles:
            story.append(paragraph(topic.capitalize(), "SubsectionTitle"))
            story.append(paragraph(topic_paragraph(topic, topic_articles)))

    story.extend(
        [
            PageBreak(),
            paragraph("Synthèse 1 — Médias non indépendants", "SectionTitle"),
            paragraph(
                "Les médias ci-dessous appartiennent à de grands groupes, à l’audiovisuel public "
                "ou à des structures disposant d’un actionnaire ou d’un cadre institutionnel important. "
                "Les encarts d’orientation sont indicatifs.",
            ),
            paragraph("Encart gauche / centre-gauche", "SubsectionTitle"),
            build_media_table(left_rows),
            Spacer(1, 7),
            paragraph("Encart droite / centre-droit", "SubsectionTitle"),
            build_media_table(right_rows),
            PageBreak(),
            paragraph("Synthèse 2 — Médias indépendants", "SectionTitle"),
            paragraph(
                "Ces médias disposent d’une structure éditoriale ou économique plus autonome au regard "
                "des grands groupes industriels et financiers. Cette catégorie n’implique pas une absence "
                "de ligne éditoriale.",
            ),
            build_media_table(independent_rows),
            Spacer(1, 8),
            paragraph("Lecture thématique", "SectionTitle"),
        ]
    )

    for topic in topics:
        story.append(paragraph(topic.capitalize(), "SubsectionTitle"))
        story.append(paragraph(topic_paragraph(topic, grouped_topics.get(topic, []))))

    story.extend(
        [
            PageBreak(),
            paragraph("Annexe — suivi des médias", "SectionTitle"),
            paragraph(
                "Le cumul correspond aux URL distinctes collectées depuis la mise en place du suivi. "
                "Le statut de la semaine indique si au moins un contenu individuel a été retenu.",
            ),
            build_tracking_table(cumulative, media_rows),
            Spacer(1, 8),
            paragraph(
                "Note : La Croix est exclue de la liste conformément à la configuration. "
                "Les médias sans article RSS vérifié restent recensés afin de rendre visibles les limites de collecte.",
                "SmallFrench",
            ),
        ]
    )

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF généré : {output_path}")


if __name__ == "__main__":
    main()
