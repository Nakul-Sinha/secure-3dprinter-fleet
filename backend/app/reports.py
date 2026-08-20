"""PDF reporting for the audit trail."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#1f4e79")
RULE = colors.HexColor("#d9e1ea")
ZEBRA = colors.HexColor("#eef3f8")
OK = colors.HexColor("#2e7d32")
BAD = colors.HexColor("#c0392b")


def audit_pdf(buf, events, check, target: str | None = None) -> None:
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=16 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            title="Audit trail")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=17, textColor=BRAND, alignment=0)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=7.2, leading=9)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")

    story = [Paragraph("Audit trail", h1), Spacer(1, 4)]
    status = "intact" if check.ok else f"TAMPERED: {check.reason}"
    attested = "attested by a signed checkpoint" if getattr(check, "attested", False) \
        else "not yet attested by a checkpoint"
    shown = len(events)
    story.append(Paragraph(
        f"Secure 3D-Printer Fleet, tier A0 tamper-evident log.<br/>"
        f"Integrity: <b>{status}</b> ({attested}).<br/>"
        f"Events in chain: {check.count}. Events shown below: {shown}."
        + (f"<br/>Filtered to target: {target}." if target else ""), body))
    story.append(Spacer(1, 8))

    rows = [[Paragraph(c, head) for c in ("seq", "actor", "action", "target", "timestamp", "hash")]]
    for e in events:
        rows.append([
            Paragraph(str(e.seq), cell),
            Paragraph(str(e.actor), cell),
            Paragraph(str(e.action), cell),
            Paragraph(str(e.target or "")[:22], cell),
            Paragraph(str(e.ts)[:19], cell),
            Paragraph(str(e.this_hash)[:16], cell),
        ])
    table = Table(rows, colWidths=[12 * mm, 22 * mm, 34 * mm, 34 * mm, 32 * mm, 32 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Every entry is hash-chained to its predecessor and signed with the fleet Ed25519 "
        "audit key. Verify independently with the public key from /api/audit/public-key.",
        ParagraphStyle("foot", parent=body, fontSize=8,
                       textColor=OK if check.ok else BAD)))
    doc.build(story)
