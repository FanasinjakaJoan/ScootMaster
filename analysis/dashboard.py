"""Tableau de bord interactif (Plotly) — output/dashboard.html.

Complement du rapport statique : graphiques survolables, zoomables et filtres
(range-slider temporel) pour explorer librement les resultats.  Genere un HTML
auto-suffisant (plotly.js embarque).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config
from . import forecast

C = config.PALETTE


def _m(v):  # millions
    return v / 1e6


def _kpi_cards() -> str:
    tend = pd.read_csv(config.TABLE_DIR / "tendance_annuelle.csv")
    port = pd.read_csv(config.TABLE_DIR / "portefeuille_modeles.csv")
    seg = pd.read_csv(config.TABLE_DIR / "profils_segments.csv")
    scen = pd.read_csv(config.TABLE_DIR / "scenarios_marge.csv")
    prev = pd.read_csv(config.TABLE_DIR / "previsions_12_mois.csv")
    ca20 = tend[tend.iloc[:, 0] == 2020]["ca"].iloc[0]
    ca22 = tend[tend.iloc[:, 0] == 2022]["ca"].iloc[0]
    top2 = port.head(2)["part_n"].sum()
    fid = int(seg[seg["segment_nom"].str.startswith("FIDELES")]["n"].sum())
    g13 = scen[scen["taux"] == .13]["gain_vs_statu_quo_ar"].iloc[0]

    cards = [
        ("CA 2022", f"{ca22:,.0f} M Ar".replace(",", " "), f"{(ca22/ca20-1)*100:+.0f} % vs 2020"),
        ("Concentration RACING+G5", f"{top2:.0f} %", "des volumes"),
        ("Marquage observe", "9,1 %", "coefficient fixe x1,09"),
        ("Clients fideles", f"{fid}", "reachat ~7 %"),
        ("Gain a 13 %", f"+{g13/1e6:.0f} M Ar/an", "volumes constants"),
        ("CA prevu 12 mois", f"{prev['ca_prevu_MAr'].sum():.0f} M Ar", "trajectoire plate"),
    ]
    html = "<div class='kpis'>"
    for k, v, s in cards:
        html += f"<div class='kpi'><div class='l'>{k}</div><div class='v'>{v}</div><div class='l'>{s}</div></div>"
    html += "</div>"
    return html


def _fig_ca_volume(clients: pd.DataFrame) -> go.Figure:
    c = clients[clients["valide"] == 1]
    g = c.groupby(c["date_achat"].dt.to_period("M")).agg(
        ca=("montant_ar", "sum"), n=("montant_ar", "size"))
    g.index = g.index.to_timestamp()
    g["mm3"] = g["ca"].rolling(3, center=True, min_periods=1).mean()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=g.index, y=_m(g["ca"]), name="CA mensuel (M Ar)",
                         marker_color=C["light"]), secondary_y=False)
    fig.add_trace(go.Scatter(x=g.index, y=_m(g["mm3"]), name="Moyenne mobile 3 mois",
                             line=dict(color=C["primary"], width=2.5)), secondary_y=False)
    fig.add_trace(go.Scatter(x=g.index, y=g["n"], name="Motos vendues",
                             line=dict(color=C["accent"], width=2), yaxis="y2"),
                  secondary_y=True)
    fig.update_layout(
        title="Chiffre d'affaires et volume mensuels — faites glisser la fenetre pour zoomer",
        barmode="overlay", height=420,
        xaxis=dict(rangeslider=dict(visible=True, thickness=.06)),
        yaxis=dict(title="CA (M Ar)"), yaxis2=dict(title="Motos", overlaying="y",
                                                   side="right", showgrid=False))
    fig.update_layout(legend=dict(orientation="h", y=1.12))
    return fig


def _fig_modeles(motos: pd.DataFrame) -> go.Figure:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    g = v.groupby("modele").agg(n=("modele", "size"), ca=("prix_vente_ar", "sum"),
                                tx=("taux_marge", "median")).sort_values("n", ascending=True)
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Motos vendues par modele",
                                                        "Taux de marge median (%)"),
                        horizontal_spacing=.12, column_widths=[.62, .38])
    fig.add_trace(go.Bar(y=g.index, x=g["n"], orientation="h", marker_color=C["primary"],
                         text=g["n"], textposition="outside"), row=1, col=1)
    fig.add_trace(go.Bar(y=g.index, x=g["tx"] * 100, orientation="h",
                         marker_color=np.where(g["tx"] * 100 >= 9, C["green"], C["red"]),
                         text=(g["tx"] * 100).round(1), textposition="outside"), row=1, col=2)
    fig.update_layout(height=430, showlegend=False,
                      title="Portefeuille : volume a gauche, rentabilite a droite")
    fig.update_yaxes(tickfont=dict(size=9))
    return fig


def _fig_matrice(motos: pd.DataFrame) -> go.Figure:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    g = v.groupby("modele").agg(n=("modele", "size"), ca=("prix_vente_ar", "sum"),
                                marge=("marge_ar", "sum"), tx=("taux_marge", "median"),
                                rot=("duree_stock_j", "median")).reset_index()
    g = g[g["n"] >= 3]
    fig = go.Figure(go.Scatter(
        x=g["n"], y=g["tx"] * 100, mode="markers+text", text=g["modele"],
        textposition="top center", textfont=dict(size=9),
        marker=dict(size=np.sqrt(g["ca"]) / 900, color=g["rot"].fillna(0),
                    colorscale="RdYlGn_r", colorbar=dict(title="Jours de stock"),
                    line=dict(color="white", width=1)),
        customdata=np.stack([g["ca"] / 1e6, g["marge"] / 1e6, g["rot"].fillna(0)], axis=1),
        hovertemplate="<b>%{text}</b><br>Volume : %{x} motos<br>Marge : %{y:.1f} %"
                      "<br>CA : %{customdata[0]:.0f} M Ar<br>Rotation : %{customdata[2]:.0f} j"
                      "<extra></extra>"))
    fig.update_layout(title="Matrice volume x marge (taille = CA, couleur = rotation)",
                      height=460,
                      xaxis_title="Volume vendu", yaxis_title="Taux de marge median (%)")
    return fig


def _fig_gammes_temps(clients: pd.DataFrame) -> go.Figure:
    c = clients[clients["valide"] == 1]
    top = c["gamme"].value_counts().head(5).index.tolist()
    g = c[c["gamme"].isin(top)].groupby(
        [c["date_achat"].dt.to_period("Q"), "gamme"]).size().unstack(fill_value=0)
    g.index = g.index.to_timestamp()
    fig = go.Figure()
    for i, col in enumerate(g.columns):
        fig.add_trace(go.Scatter(x=g.index, y=g[col], name=col, stackgroup="one",
                                 line=dict(width=1), opacity=.85,
                                 marker_color=config.SEQ[i % len(config.SEQ)]))
    fig.update_layout(title="Evolution trimestrielle du mix vendu (5 premieres gammes)",
                      height=420, yaxis_title="Motos vendues / trimestre",
                      legend=dict(orientation="h", y=1.1))
    return fig


def _fig_segments() -> go.Figure:
    seg = pd.read_csv(config.TABLE_DIR / "profils_segments.csv")
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Clients par palier",
                                                        "Depense moyenne (M Ar)"),
                        specs=[[{"type": "domain"}, {"type": "bar"}]])
    fig.add_trace(go.Pie(labels=seg["segment_nom"], values=seg["n"], hole=.5,
                         marker_colors=config.SEQ[:len(seg)],
                         textinfo="percent", hovertemplate="%{label}<br>%{value} clients<extra></extra>"),
                  row=1, col=1)
    s2 = seg.sort_values("ca")
    fig.add_trace(go.Bar(y=s2["segment_nom"], x=s2["ca"] / 1e6, orientation="h",
                         marker_color=config.SEQ[:len(s2)],
                         text=(s2["ca"] / 1e6).round(2), textposition="outside"), row=1, col=2)
    fig.update_layout(height=420, showlegend=False,
                      title="Segmentation de valeur : le noyau fidele porte le CA")
    fig.update_yaxes(tickfont=dict(size=8.5))
    return fig


def _fig_geo() -> go.Figure:
    geo = pd.read_csv(config.TABLE_DIR / "geographie_quartiers.csv").head(12)
    fig = go.Figure(go.Bar(x=geo["n"], y=geo["quartier"], orientation="h",
                           marker_color=C["primary"], text=geo["n"],
                           textposition="outside",
                           customdata=(geo["ca"] / 1e6).round(0),
                           hovertemplate="<b>%{y}</b><br>%{x} motos<br>%{customdata} M Ar<extra></extra>"))
    fig.update_layout(title="Principaux quartiers clients", height=430,
                      yaxis=dict(autorange="reversed", tickfont=dict(size=9)))
    return fig


def _fig_prev(clients: pd.DataFrame) -> go.Figure:
    _, s_vol, info = forecast.prevision_globale(
        clients, "n", "Motos", "_tmp_prev.png", "tmp")
    hist = forecast._serie_mensuelle(clients, "n")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index.to_timestamp(), y=hist.values, name="Historique",
                             line=dict(color=C["primary"], width=2)))
    fx = s_vol.index.to_timestamp()
    resid = info["total_hi"] - info["total_prev"]
    lo = np.clip(s_vol.values - resid / 1.96 * 1.96 * .5, 0, None)
    hi = s_vol.values + resid / 1.96 * 1.96 * .5
    fig.add_trace(go.Scatter(x=fx, y=hi, name="Borne haute", line=dict(width=0),
                             showlegend=False))
    fig.add_trace(go.Scatter(x=fx, y=lo, name="Intervalle 95 %", fill="tonexty",
                             line=dict(width=0), fillcolor="rgba(232,131,58,.18)"))
    fig.add_trace(go.Scatter(x=fx, y=s_vol.values, name=f"Prevision ({info['modele']})",
                             line=dict(color=C["accent"], width=2.4, dash="dot")))
    fig.update_layout(title="Prevision du volume mensuel (12 mois) et intervalle",
                      height=420, legend=dict(orientation="h", y=1.1))
    return fig


CSS = """
<style>
:root{--p:#1f4e79;--a:#e8833a;--bg:#f4f7fa;--tx:#1c2733}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
 font-family:'Segoe UI',system-ui,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 70px}
header{background:linear-gradient(120deg,var(--p),#2d6da8);color:#fff;padding:30px 0 24px}
header h1{margin:0;font-size:26px}
header .sub{opacity:.9;font-size:13px;margin-top:4px}
h2{color:var(--p);font-size:19px;margin-top:40px;border-left:5px solid var(--a);padding-left:10px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:10px 14px;
 box-shadow:0 1px 4px rgba(20,40,70,.06);margin:14px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}
.kpi{background:#fff;border:1px solid #e2e8f0;border-left:4px solid var(--a);
 border-radius:8px;padding:12px 14px}
.kpi .v{font-size:20px;font-weight:700;color:var(--p)}
.kpi .l{font-size:12px;color:#5a6b7c}
nav a{color:#fff;background:rgba(255,255,255,.15);padding:6px 14px;border-radius:20px;
 text-decoration:none;font-size:13px;margin-right:8px;display:inline-block;margin-top:10px}
nav a:hover{background:rgba(255,255,255,.3)}
.note{font-size:12.5px;color:#5a6b7c;margin-top:6px}
</style>"""


def construire(jdd) -> str:
    divs = []
    first = True

    def add(fig, note=""):
        nonlocal first
        divs.append("<div class='card'>" +
                    fig.to_html(full_html=False, include_plotlyjs=first) +
                    (f"<div class='note'>{note}</div>" if note else "") + "</div>")
        first = False

    figs = [
        (_fig_ca_volume(jdd.clients), "Survolez pour lire chaque mois ; utilisez la barre de zoom sous l'axe."),
        (_fig_modeles(jdd.motos), "Volume et rentabilite par modele."),
        (_fig_matrice(jdd.motos), "Survolez les bulles pour le detail (CA, marge, rotation)."),
        (_fig_gammes_temps(jdd.clients), "La demande bascule vers RACING ; G5 recule."),
        (_fig_segments(), "Paliers de valeur clients."),
        (_fig_geo(), "Concentration geographique."),
        (_fig_prev(jdd.clients), "Trajectoire plate, bornes larges."),
    ]
    for f, n in figs:
        add(f, n)

    html = ("<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>ScootMaster — Tableau de bord interactif</title>" + CSS +
            "</head><body><header><div class='wrap'>"
            "<h1>ScootMaster — Tableau de bord interactif</h1>"
            "<div class='sub'>Explorez les resultats : survol, zoom et filtres actifs.</div>"
            "<nav><a href='rapport_data_scootmaster.html'>Rapport complet</a>"
            "<a href='figures/'>Toutes les figures</a></nav>"
            "</div></header><div class='wrap'>" + _kpi_cards() +
            "<h2>Performance commerciale</h2>" + divs[0] + divs[1] +
            "<h2>Portefeuille & marges</h2>" + divs[2] + divs[3] +
            "<h2>Clients & territoire</h2>" + divs[4] + divs[5] +
            "<h2>Projection</h2>" + divs[6] +
            "</div></body></html>")

    # nettoyage du fichier temporaire genere par la prevision
    tmp = config.FIG_DIR / "_tmp_prev.png"
    if tmp.exists():
        tmp.unlink()

    out = config.OUTPUT_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    from . import etl
    jdd = etl.charger()
    print(construire(jdd))
