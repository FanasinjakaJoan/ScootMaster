"""Generation du rapport final au format PDF.

Convertit le rapport HTML en document PDF paginé, prêt à l'impression
et à la diffusion managériale, avec intégration des figures et des indicateurs.
"""
from __future__ import annotations

import re
from pathlib import Path
from xhtml2pdf import pisa

from . import config


CSS_PDF = """<style>
@page {
    size: a4 portrait;
    margin: 1.2cm 1.2cm 1.4cm 1.2cm;
}

body {
    font-family: Helvetica, Arial, sans-serif;
    color: #1a202c;
    font-size: 9.5pt;
    line-height: 1.4;
}

.header-banner {
    background-color: #1f4e79;
    color: #ffffff;
    padding: 16px 18px;
    margin-bottom: 16px;
}

.header-title {
    font-size: 19pt;
    font-weight: bold;
    margin: 0 0 6px 0;
    color: #ffffff;
}

.header-sub {
    font-size: 10pt;
    color: #d6e4f0;
}

h2 {
    color: #1f4e79;
    font-size: 13.5pt;
    border-bottom: 2px solid #e8833a;
    padding-bottom: 3px;
    margin-top: 18px;
    margin-bottom: 10px;
}

h3 {
    color: #1f4e79;
    font-size: 10.5pt;
    margin-top: 6px;
    margin-bottom: 6px;
}

.card {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    padding: 10px 12px;
    margin-bottom: 12px;
}

.interp {
    font-size: 9pt;
    color: #334155;
    line-height: 1.4;
}

.pts {
    margin: 6px 0 0 0;
    padding-left: 14px;
}

.pts li {
    font-size: 8.5pt;
    color: #475569;
    padding: 2px 0;
    border: none;
}

table {
    width: 100%;
    margin: 10px 0;
    font-size: 8pt;
}

th {
    background-color: #1f4e79;
    color: #ffffff;
    text-align: left;
    padding: 6px 7px;
    font-weight: bold;
}

td {
    padding: 5px 7px;
    border-bottom: 1px solid #e2e8f0;
    vertical-align: top;
}

tr:nth-child(even) td {
    background-color: #f8fafc;
}

.kpi-table {
    width: 100%;
    margin: 10px 0 14px 0;
}

.kpi-table td {
    width: 25%;
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #e8833a;
    padding: 8px 10px;
    vertical-align: top;
}

.kpi-title {
    font-size: 7.5pt;
    color: #64748b;
    font-weight: bold;
    text-transform: uppercase;
    margin-bottom: 4px;
}

.kpi-val {
    font-size: 13pt;
    font-weight: bold;
    color: #1f4e79;
    margin-bottom: 3px;
}

.kpi-sub {
    font-size: 7.5pt;
    color: #64748b;
}

.prio-badge {
    background-color: #e8833a;
    color: #ffffff;
    font-weight: bold;
    font-size: 8pt;
    padding: 1px 6px;
    margin-right: 6px;
}

footer {
    margin-top: 20px;
    border-top: 1px solid #cbd5e1;
    padding-top: 8px;
    font-size: 7.5pt;
    color: #64748b;
    text-align: center;
}
</style>"""


def generer(html_path: Path | None = None, pdf_path: Path | None = None) -> Path:
    if html_path is None:
        html_path = config.OUTPUT_DIR / "rapport_data_scootmaster.html"
    if pdf_path is None:
        pdf_path = config.OUTPUT_DIR / "rapport_data_scootmaster.pdf"

    html_text = html_path.read_text(encoding="utf-8")

    # Adapter le CSS pour le rendu PDF
    html_text = re.sub(r"<style>.*?</style>", CSS_PDF, html_text, flags=re.DOTALL)

    # Banniere d'en-tete
    html_text = re.sub(
        r"<header><div class='wrap'><h1>(.*?)</h1><div class='sub'>(.*?)</div></div></header>",
        r"<div class='header-banner'><div class='header-title'>\1</div><div class='header-sub'>\2</div></div>",
        html_text,
    )

    # Conversion mise en gras Markdown
    html_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", html_text)

    # Grille KPI vers tableau structuré
    def replace_kpis(match):
        content = match.group(1)
        items = re.findall(
            r"<div class='b'><div class='l'>([^<]*)</div><div class='v'>([^<]*)</div><div class='l'>([^<]*)</div></div>",
            content,
        )
        rows = []
        for i in range(0, len(items), 4):
            chunk = items[i : i + 4]
            tds = "".join(
                [
                    f"<td><div class='kpi-title'>{k}</div><div class='kpi-val'>{v}</div><div class='kpi-sub'>{sub}</div></td>"
                    for k, v, sub in chunk
                ]
            )
            while len(chunk) < 4:
                tds += "<td></td>"
                chunk.append(None)
            rows.append(f"<tr>{tds}</tr>")
        return f"<table class='kpi-table'>{''.join(rows)}</table>"

    html_text = re.sub(r"<div class='kpi'>(.*?)</div>\s*(?=<h2>)", replace_kpis, html_text, flags=re.DOTALL)
    html_text = html_text.replace("<span class='prio'>", "<span class='prio-badge'>")

    # Dimensions explicites des graphiques
    html_text = re.sub(r"<img\s+src=", r'<img width="510" src=', html_text)

    # Sauts de page par chapitre
    for s in [1, 2, 3, 4, 5, 6, 7, 8]:
        html_text = html_text.replace(f"<h2>{s}.", f"<pdf:nextpage /><h2>{s}.")

    with open(pdf_path, "wb") as f:
        pisa_status = pisa.CreatePDF(html_text, dest=f)

    if pisa_status.err:
        raise RuntimeError(f"Erreur lors de la generation du PDF : {pisa_status.err}")

    return pdf_path


if __name__ == "__main__":
    out = generer()
    print("PDF genere avec succes :", out)
