from pathlib import Path
from datetime import date, timedelta
import csv
import os
import smtplib
from email.message import EmailMessage

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics


BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "cumul_medias.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SMTP_USERNAME = os.environ["SMTP_USERNAME"]
SMTP_APP_PASSWORD = os.environ["SMTP_APP_PASSWORD"]
EMAIL_TO = os.environ["EMAIL_TO"]


def previous_week():
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(days=7)
    end = current_monday - timedelta(days=1)
    return start, end


def format_fr(day):
    months = [
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
    return f"{day.day} {months[day.month - 1]} {day.year}"


def load_media():
    with DATA_FILE.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def get_fonts():
    candidate_fonts = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        ),
    ]

    for normal_path, bold_path in candidate_fonts:
        if os.path.exists(normal_path) and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("DejaVu", normal_path))
            pdfmetrics.registerFont(TTFont("DejaVuBold", bold_path))
            return "DejaVu", "DejaVuBold"

    return "Helvetica", "Helvetica-Bold"


def build_pdf(media, start, end):
    filename = f"synthese_medias_{start.isoformat()}_{end.isoformat()}.pdf"
    pdf_path = OUTPUT_DIR / filename

    normal_font, bold_font = get_fonts()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleFR",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=20,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
        spaceAfter=16,
    )

    subtitle_style = ParagraphStyle(
        "SubtitleFR",
        parent=styles["BodyText"],
        fontName=normal_font,
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=14,
    )

    body_style = ParagraphStyle(
        "BodyFR",
        parent=styles["BodyText"],
        fontName=normal_font,
        fontSize=9,
        leading=12,
        spaceAfter=6,
    )

    cell_style = ParagraphStyle(
        "CellFR",
        parent=styles["BodyText"],
        fontName=normal_font,
        fontSize=7,
        leading=8.5,
    )

    header_style = ParagraphStyle(
        "HeaderFR",
        parent=cell_style,
        fontName=bold_font,
        textColor=colors.HexColor("#17365D"),
    )

    story = []

    story.append(
        Paragraph("Synthèse des médias en France", title_style)
    )

    story.append(
        Paragraph(
            f"Semaine du {format_fr(start)} au {format_fr(end)}",
            subtitle_style,
        )
    )

    story.append(
        Paragraph(
            "Version automatisée de test. "
            "Cette première version vérifie le bon fonctionnement de "
            "l’automatisation, de l’e-mail et du suivi cumulatif.",
            body_style,
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph("Annexe — suivi des médias", body_style)
    )

    headers = [
        "Média",
        "Catégorie",
        "Positionnement indicatif",
        "Cumul d’articles",
        "Au moins un article cette semaine",
    ]

    sorted_media = sorted(
        media,
        key=lambda row: (
            -int(row["cumul_articles"]),
            0 if row["article_cette_semaine"] == "Oui" else 1,
            row["media"].lower(),
        ),
    )

    rows = [
        [Paragraph(header, header_style) for header in headers]
    ]

    for item in sorted_media:
        rows.append(
            [
                Paragraph(item["media"], cell_style),
                Paragraph(item["categorie"], cell_style),
                Paragraph(item["positionnement"], cell_style),
                Paragraph(item["cumul_articles"], cell_style),
                Paragraph(item["article_cette_semaine"], cell_style),
            ]
        )

    table = Table(
        rows,
        colWidths=[
            3.9 * cm,
            2.7 * cm,
            6.7 * cm,
            2.6 * cm,
            3.2 * cm,
        ],
        repeatRows=1,
    )

    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A6A6A6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    for row_index, item in enumerate(sorted_media, start=1):
        if item["article_cette_semaine"] == "Oui":
            table_style.append(
                (
                    "BACKGROUND",
                    (4, row_index),
                    (4, row_index),
                    colors.HexColor("#D9EAD3"),
                )
            )
        else:
            table_style.extend(
                [
                    (
                        "BACKGROUND",
                        (0, row_index),
                        (0, row_index),
                        colors.HexColor("#F4CCCC"),
                    ),
                    (
                        "BACKGROUND",
                        (4, row_index),
                        (4, row_index),
                        colors.HexColor("#F4CCCC"),
                    ),
                ]
            )

    table.setStyle(TableStyle(table_style))
    story.append(table)

    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=1.25 * cm,
        rightMargin=1.25 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        title="Synthèse des médias français",
    )

    document.build(story)

    return pdf_path


def build_email_body(start, end):
    return f"""Vous trouverez ci-joint la synthèse des médias français couvrant la semaine du {format_fr(start)} au {format_fr(end)}.

Points chauds de l’actualité :
- Le ralentissement économique, la croissance française et la préparation budgétaire.
- Les évolutions politiques et les débats liés à la présidentielle de 2027.
- Les tensions internationales, européennes et énergétiques.
- Les enjeux écologiques, sociaux, sanitaires et territoriaux.
- Les débats liés au numérique, à l’intelligence artificielle et aux médias.

Le document joint contient le suivi cumulatif des médias et le statut de présence d’au moins un article pendant la semaine.
"""


def send_email(pdf_path, start, end):
    message = EmailMessage()

    message["From"] = SMTP_USERNAME
    message["To"] = EMAIL_TO
    message["Subject"] = (
        "Synthèse des médias français — "
        f"semaine du {format_fr(start)} au {format_fr(end)}"
    )

    message.set_content(build_email_body(start, end))

    with pdf_path.open("rb") as attachment:
        message.add_attachment(
            attachment.read(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SMTP_USERNAME, SMTP_APP_PASSWORD)
        smtp.send_message(message)


def main():
    start, end = previous_week()
    media = load_media()
    pdf_path = build_pdf(media, start, end)
    send_email(pdf_path, start, end)
    print(f"Rapport généré et envoyé : {pdf_path}")


if __name__ == "__main__":
    main()
