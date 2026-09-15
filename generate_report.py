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
    """Retourne le lundi
