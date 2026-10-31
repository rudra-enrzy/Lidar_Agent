"""PDF version of a span report: the same table as the Excel, then every screenshot (when they exist) with its Reference Image
name; each Reference Image cell links to its picture inside the PDF."""
import os
from datetime import datetime
from xml.sax.saxutils import escape
from .templates import TOWER_TYPE_TEXT, groups


def build_pdf(path, meta, ttype, results, remarks, image_prefix, image_dir=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, Image
    from PIL import Image as PI

    ss = getSampleStyleSheet()
    cell = ParagraphStyle("c", parent=ss["BodyText"], fontSize=8.5, leading=10.5)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
    ctr = ParagraphStyle("cc", parent=cell, alignment=1)
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=15, leading=18)
    P = lambda t, st=cell: Paragraph(escape(str(t)).replace("\n", "<br/>"), st)

    def d(x):
        try: return datetime.strptime(x, "%Y-%m-%d").strftime("%d-%m-%Y") if x else ""
        except ValueError: return str(x)

    def png(ref): return os.path.join(image_dir, ref + ".png") if image_dir else None
    have = lambda ref: bool(png(ref)) and os.path.isfile(png(ref))

    logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
    head_t = Paragraph("Powerline Vegetation and Sag Analysis using Drone LiDAR System", title)
    if os.path.isfile(logo):
        lw, lh = PI.open(logo).size
        top = Table([[Image(logo, width=1.1 * cm * lw / lh, height=1.1 * cm), head_t, ""]],
                    colWidths=[2.2 * cm, 21.1 * cm, 2.2 * cm])
        top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT")]))
        story = [top]
    else:
        story = [head_t]
    head = [("Client", meta.get("client", "")), ("Line Details", meta.get("line", "")), ("Tower No", meta.get("tower_no", "")),
            ("Span", meta.get("span", "")), ("No of Circuit", meta.get("circuit", "")),
            ("Powerline Capacity", meta.get("capacity", "")), ("Tower Lat-Long", meta.get("latlon", "")),
            ("Tower Type", TOWER_TYPE_TEXT[ttype]), ("Tower Structure", meta.get("structure", "Lattice Tower ")),
            ("Date of Data Capture", d(meta.get("capture_date"))), ("Date of Inspection", d(meta.get("inspection_date")))]
    t = Table([[P(k, cellb), P(v)] for k, v in head], colWidths=[5.5 * cm, 20 * cm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, colors.black), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F8")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(1, .4 * cm)]

    rows = [[P(x, cellb) for x in ("Clearances Type", "Observation Type", "LiDAR Measurement (m)", "Reference Image", "Suggestion / Remarks")]]
    spans, n, shots = [], 0, []
    for grp, obs in groups(ttype, results):
        start = len(rows)
        for label, key in obs:
            r = results[key]
            if r["conf"] == "na": val, ref = "N/A", ""
            elif r["value"] is not None:
                n += 1; ref = f"{image_prefix}-{n}"; val = f"{r['value']:.2f}"
                if have(ref): shots.append((ref, label.strip(), val))
            else: val, ref = "", ""
            link = f'<a href="#{ref}" color="#0563C1"><u>{escape(ref)}</u></a>' if ref and have(ref) else escape(ref)
            rows.append(["", P(label), P(val, ctr), Paragraph(link, ctr), P(remarks.get(key, ""))])
        rows[start][0] = P(grp, cellb)
        if len(rows) - 1 > start: spans.append(("SPAN", (0, start), (0, len(rows) - 1)))
    span_ref = f"{image_prefix}-Span"
    if have(span_ref): shots.append((span_ref, "Span", ""))
    rows.append([P("Span", cellb), "", "", Paragraph(f'<a href="#{span_ref}" color="#0563C1"><u>{span_ref}</u></a>' if have(span_ref) else span_ref, ctr), ""])
    tb = Table(rows, colWidths=[4.2 * cm, 7 * cm, 3 * cm, 3.2 * cm, 8.1 * cm], repeatRows=1)
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")] + spans))
    story.append(tb)

    if shots:
        story.append(PageBreak()); story.append(Paragraph("Reference images", title))
        W = 12.4 * cm
        def pic(ref, label, val):
            w, h = PI.open(png(ref)).size
            cap = f'<a name="{ref}"/><b>{escape(ref)}</b> &nbsp; {escape(label)}' + (f" &nbsp; <b>{val} m</b>" if val else "")
            return [Paragraph(cap, cell), Image(png(ref), width=W, height=W * h / w)]
        cells = [pic(*s) for s in shots]
        grid = []
        for i in range(0, len(cells), 2):
            pair = cells[i:i + 2]; pair += [[Spacer(1, 1)]] * (2 - len(pair))
            grid.append(pair)
        for i in range(0, len(grid), 2):                       # two rows of two pictures per page
            g = Table(grid[i:i + 2], colWidths=[13 * cm, 13 * cm])
            g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            story.append(g)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=1.1 * cm, rightMargin=1.1 * cm, topMargin=1 * cm, bottomMargin=1 * cm,
                            title=f"Sag and Vegetation Clearance Report {meta.get('span', '')}")
    doc.build(story)
    return path
