from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.common import display_value


def _register_unicode_font() -> tuple[str, str]:
    candidates = [
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"), Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf")),
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path(reportlab.__file__).parent / "fonts" / "Vera.ttf", Path(reportlab.__file__).parent / "fonts" / "VeraBd.ttf"),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("TE-Regular", str(regular)))
            pdfmetrics.registerFont(TTFont("TE-Bold", str(bold)))
            return "TE-Regular", "TE-Bold"
    raise RuntimeError("No se encontró una fuente Unicode instalada para generar el PDF")


class NumberedCanvasMixin:
    pass


class PDFRenderer:
    def __init__(self, max_table_rows=5000): self.max_table_rows = max_table_rows

    def render(self, path: Path, title: str, campaign_name: str, report_date: date, period: tuple[date | None, date | None], sections: list[dict[str, Any]]):
        regular, bold = _register_unicode_font()
        styles = getSampleStyleSheet()
        for style in styles.byName.values(): style.fontName = regular
        styles["Title"].fontName = bold; styles["Heading1"].fontName = bold; styles["Heading2"].fontName = bold
        cover = ParagraphStyle("Cover", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, leading=28, textColor=colors.HexColor("#16324F"))
        subtitle = ParagraphStyle("Subtitle", parent=styles["Heading2"], alignment=TA_CENTER, fontName=bold)
        context = sections[0].get("context", {}) if sections else {}
        story = [Spacer(1, 30 * mm), Paragraph("TERRITORIO ELECTORAL", cover), Spacer(1, 8 * mm), Paragraph(str(context.get("report_kind","INFORME EJECUTIVO<br/>ELECCIÓN ACTUAL")), subtitle)]
        election = context.get("election_name")
        if election: story += [Spacer(1, 8 * mm), Paragraph(str(election), subtitle)]
        cover_rows = [
            ["Cantón", context.get("canton_name", "No disponible")], ["Campaña", campaign_name],
            ["Fecha del informe", report_date], ["Corte del registro electoral", context.get("snapshot_date")],
            ["Modelo", context.get("model_code")], ["Versión", context.get("model_version")],
        ]
        if context.get("study_name"):
            cover_rows=[["Estudio",context.get("study_name")],["Tipo",context.get("study_type")],["Campaña",campaign_name],["Inicio de campo",context.get("fieldwork_start_date")],["Fin de campo",context.get("fieldwork_end_date")],["Fecha publicación",context.get("publication_date")]]
        cover_table = Table([[Paragraph(str(k), styles["BodyText"]), Paragraph(display_value(v, "date" if isinstance(v, date) else None), styles["BodyText"])] for k, v in cover_rows], colWidths=[55 * mm, 90 * mm])
        cover_table.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), bold), ("LINEBELOW", (0, 0), (-1, -1), .25, colors.HexColor("#CED7E0")), ("PADDING", (0, 0), (-1, -1), 7)]))
        story += [Spacer(1, 12 * mm), cover_table, PageBreak()]
        for section in sections:
            story.append(Paragraph(str(section["title"]), styles["Heading1"]))
            if section.get("subtitle"): story.append(Paragraph(str(section["subtitle"]), styles["Heading2"]))
            if section.get("text"): story.extend([Paragraph(str(section["text"]).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 4 * mm)])
            rows = section.get("rows", [])[:self.max_table_rows]
            headers = section.get("headers", [])
            formats = section.get("formats", [])
            if rows:
                rendered = []
                if headers: rendered.append([Paragraph(str(v), styles["BodyText"]) for v in headers])
                for row in rows:
                    rendered.append([Paragraph(display_value(v, formats[i] if i < len(formats) else None), styles["BodyText"]) for i, v in enumerate(row)])
                available = A4[0] - 30 * mm
                widths = section.get("col_widths")
                if widths: widths = [available * float(w) / sum(widths) for w in widths]
                table = Table(rendered, repeatRows=1 if headers else 0, hAlign="LEFT", colWidths=widths)
                table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#9AA9B8")), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), regular), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), section.get("font_size", 7.5)), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
                story.append(table)
            story.append(Spacer(1, 6 * mm))

        def footer(canvas, doc):
            canvas.saveState(); canvas.setFont(regular, 8); canvas.setFillColor(colors.HexColor("#526579"))
            canvas.drawString(15 * mm, 9 * mm, "Territorio Electoral · Informe Ejecutivo")
            canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Página {doc.page}")
            canvas.restoreState()
        SimpleDocTemplate(str(path), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=14 * mm, bottomMargin=17 * mm, title=title, author="Territorio Electoral", subject="Informe Ejecutivo — Elección Actual").build(story, onFirstPage=footer, onLaterPages=footer)
