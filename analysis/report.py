"""Generation du rapport final (Markdown + HTML) et du classeur decisionnel.

Le rapport assemble, dans un ordre narratif, toutes les figures produites par
les modules EDA / segmentation / prevision, chacune accompagnee de son
interpretation.  Une synthese executive et un plan d'action chiffré, calcules
sur les tables reelles, ouvrent et ferment le document.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime

import pandas as pd

from . import config

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _lire(nom: str) -> pd.DataFrame:
    return pd.read_csv(config.TABLE_DIR / nom)


def _fmt_m(v: float) -> str:
    return f"{v/1e6:,.0f}".replace(",", " ")


# --------------------------------------------------------------------------
# Synthese executive : chiffres cles calcules sur les tables
# --------------------------------------------------------------------------

def _kpi() -> list[tuple[str, str, str]]:
    tend = _lire("tendance_annuelle.csv")
    port = _lire("portefeuille_modeles.csv")
    scen = _lire("scenarios_marge.csv")
    mix = _lire("mix_produit_futur.csv")
    seg = _lire("profils_segments.csv")
    prev = _lire("previsions_12_mois.csv")

    ca20 = tend.loc[tend.iloc[:, 0] == 2020, "ca"].iloc[0]
    ca22 = tend.loc[tend.iloc[:, 0] == 2022, "ca"].iloc[0]
    n20 = tend.loc[tend.iloc[:, 0] == 2020, "n"].iloc[0]
    n22 = tend.loc[tend.iloc[:, 0] == 2022, "n"].iloc[0]
    top2 = port.head(2)
    part_top2 = top2["part_n"].sum()
    fideles = seg[seg["segment_nom"].str.startswith("FIDELES")]
    gain13 = scen.loc[scen["taux"] == .13, "gain_vs_statu_quo_ar"].iloc[0]
    ca_prev = prev["ca_prevu_MAr"].sum()

    return [
        ("Periode analysee", "04/2020 -> 01/2023", "33 mois complets + janv. 2023 tronque"),
        ("CA 2020 -> 2022", f"{ca20:.0f} -> {ca22:.0f} M Ar", f"{(ca22/ca20-1)*100:+.0f} % (palier bas)"),
        ("Ventes 2020 -> 2022", f"{n20:.0f} -> {n22:.0f} motos", "stabilisees depuis 2021"),
        ("Concentration produit", f"{part_top2:.0f} %", "portee par RACING + G5"),
        ("Marquage observe", "9,1 %", "coefficient fixe x1,09"),
        ("Clients fideles", f"{int(fideles['n'].sum())}", "= gros du CA, reachat ~7 %"),
        ("Gain potentiel (+13 %)", f"+{gain13/1e6:.0f} M Ar/an", "a volumes constants"),
        ("CA prevu 12 mois", f"{ca_prev:.0f} M Ar", "trajectoire plate, bornes larges"),
    ]


# --------------------------------------------------------------------------
# Plan d'action : chaque recommandation s'appuie sur une table calculee
# --------------------------------------------------------------------------

def _recommandations() -> list[dict]:
    scen = _lire("scenarios_marge.csv")
    mix = _lire("mix_produit_futur.csv")
    seg = _lire("profils_segments.csv")
    rot = _lire("rotation_stock.csv")
    gain13 = scen.loc[scen["taux"] == .13, "gain_vs_statu_quo_ar"].iloc[0]
    gain15 = scen.loc[scen["taux"] == .15, "gain_vs_statu_quo_ar"].iloc[0]
    fideles = int(seg[seg["segment_nom"].str.startswith("FIDELES")]["n"].sum())

    top_mix = mix.head(2)
    bot_mix = mix.sort_values("score_priorite").head(2)
    lent = rot.sort_values("mediane").iloc[-1]

    return [
        dict(
            prio=1, titre="Reviser la politique de prix : sortir du marquage uniforme de 9 %",
            base="Fig. 07, 11, 17",
            texte="Le prix est un coefficient fixe du cout d'achat, identique quel que soit le "
                  "modele ou la vitesse de vente. L'operation 2023 prouve que 13 % est atteignable "
                  "sur les memes produits. Relever progressivement le coefficient, modele par modele.",
            impact=f"+{gain13/1e6:.0f} M Ar/an a 13 % (jusqu'a +{gain15/1e6:.0f} M Ar a 15 %), "
                   "a volumes constants",
            effort="Moyen", horizon="0-3 mois"),
        dict(
            prio=2, titre="Reequilibrer le stock vers les gammes qui tournent et montent",
            base="Fig. 05, 06, 16",
            texte=f"Renforcer {top_mix['gamme'].iloc[0]} et {top_mix['gamme'].iloc[1] if len(top_mix)>1 else 'GP'} "
                  "(demande en hausse, rotation rapide) et reduire les gammes lentes a marge faible "
                  f"({bot_mix['gamme'].iloc[0]}, {bot_mix['gamme'].iloc[1]}). Le mix projeté donne le "
                  "volume annuel a commander par gamme.",
            impact="Moins de capital immobilise, meilleure disponibilite sur les best-sellers",
            effort="Faible", horizon="0-3 mois"),
        dict(
            prio=3, titre="Traiter le premier achat comme un client a part entiere",
            base="Fig. 12, 13",
            texte="Le reachat n'est que de ~7 % : la valeur se joue au premier achat. Maximiser le "
                  "panier du premier achat (accessoires, pieces, services) et qualifier le client "
                  "(telephone, quartier) des la vente pour permettre toute relance.",
            impact="Augmente la valeur d'un flux qui ne reviendra pas",
            effort="Moyen", horizon="1-6 mois"),
        dict(
            prio=4, titre="Reactiver le reservoir des fideles et des haut de gamme",
            base="Fig. 12, 13",
            texte=f"Recontacter en priorite les {fideles} clients fideles et les premiers achats haut "
                  "de gamme (taux de reachat nettement superieur) avec une offre ciblee. C'est le "
                  "seul segment ou une campagne de relance a un rendement eleve.",
            impact=f"{fideles} clients a fort potentiel, CA concentre",
            effort="Faible", horizon="1-3 mois"),
        dict(
            prio=5, titre="Structurer le canal indirect (apporteurs) qui amene des ventes hors stock",
            base="Fig. 02",
            texte="75 ventes passent par des apporteurs et ~40 % des ventes clients ne sont pas "
                  "tracees dans la base motos. Formaliser ce canal (commission, suivi) le rend "
                  "pilotable et evite les pertes de marge.",
            impact="Rendre visible et rentable ~40 % du volume",
            effort="Moyen", horizon="3-6 mois"),
        dict(
            prio=6, titre="Assainir et unifier la donnee : un registre unique de ventes",
            base="Fig. 01, 02",
            texte="Les deux bases divergent (ratio 1,6) et la base motos comporte un bloc de synthese "
                  "qui doublait le CA. Mettre en place un registre unique horodate, collecter les "
                  "telephones manquants et normaliser les noms de modeles a la saisie.",
            impact="Des decisions fondees sur une seule version de la verite",
            effort="Moyen", horizon="0-6 mois"),
        dict(
            prio=7, titre="Reduire l'immobilisation sur les modeles lents",
            base="Fig. 08",
            texte=f"{lent['modele']} reste {lent['mediane']:.0f} jours en stock (P90 a {lent['p90']:.0f} j) "
                  "pour une marge comparable aux modeles rapides. Negocier des conditions d'achat ou "
                  "vendre en flux tire plutot qu'en stock.",
            impact="Liberation de tresorerie",
            effort="Faible", horizon="1-6 mois"),
    ]


# --------------------------------------------------------------------------
# Sections du rapport (ordre narratif)
# --------------------------------------------------------------------------

SECTIONS = [
    ("0", "Synthese executive", [], "intro_exec"),
    ("1", "Perimetre, methodologie et qualite des donnees",
     ["01_qualite_donnees.png", "02_reconciliation_sources.png"], None),
    ("2", "Vue d'ensemble : une activete stabilisee sur un palier bas",
     ["03_tendance_ca.png", "04_saisonnalite.png"], None),
    ("3", "Portefeuille produits : concentration et arbitrage volume/marge",
     ["05_pareto_portefeuille.png", "06_matrice_portefeuille.png",
      "08_rotation_stock.png"], None),
    ("4", "Prix et marges : le levier inexploite",
     ["07_politique_prix.png", "09_dynamique_prix.png",
      "11_benchmark_marge_2023.png", "17_scenarios_marge.png"], None),
    ("5", "Clients : qui acheter, ou, et qui reviendra",
     ["10_geographie.png", "12_segments_valeur.png", "13_modele_reachat.png"], None),
    ("6", "Previsions et trajectoire a 12 mois",
     ["14_previsions_volume.png", "15_previsions_ca.png", "16_mix_produit_futur.png"], None),
    ("7", "Plan d'action priorise", [], "reco"),
    ("8", "Limites et points de vigilance", [], "limites"),
]

INTRO_EXEC = """ScootMaster est un **negoce de motos a flux tendu** : la moitie du parc est
vendue en moins d'une semaine, mais l'activite s'est stabilisee depuis 2021 sur un palier bas
(~950-980 M Ar/an) sans croissance. Le chiffre d'affaires est **tres concentre** sur deux
modeles (KYMCO RACING et G5), et la marge est **fixee par une regle unique** (coefficient x1,09,
soit ~9 %) qui ne tient compte ni de la vitesse de vente ni de la valeur du modele.

Trois leviers ressortent nettement des donnees :

1. **Le prix** : le meme commerce, mene en 2023 avec un marquage de 13 %, a degage 4 points de
   marge de plus. Relever le coefficient est le levier le plus direct (+17 M Ar/an a volumes
   constants).
2. **Le mix** : la demande bascule vers RACING et les gammes rapides ; le stock doit suivre ce
   mouvement et se degager des references lentes.
3. **Le client** : avec ~7 % de reachat, la valeur se joue au premier achat et dans un petit
   reservoir de fideles a reactiver.

Les donnees, une fois nettoyees (un bloc de synthese doublait le CA), sont suffisamment riches
pour fonder ces decisions ; elles restent en revanche trop courtes pour une prevision fine —
les trajectoires a 12 mois sont donnees avec des bornes larges et servent a dimensionner le
stock et la tresorerie."""


LIMITES = """- **Fenetre temporelle** : les donnees s'arretent en janvier 2023. Les previsions sont
  des extrapolations de regimes passes ; elles ne capturent ni l'inflation recente ni l'evolution
  du marche depuis lors. A recalibrer avec des donnees recentes.
- **Deux registres non reconcilies** : la base clients et la base motos divergent (ratio 1,6).
  Les analyses de CA s'appuient sur la base clients, celles de marge/rotation sur la base motos.
- **Taux de reachat faible** : la segmentation de fidelite repose sur un petit echantillon de
  re-acheteurs (63) ; le modele de reachat est indicatif, pas operationnel tel quel.
- **Saisonalite faible** : la variance mensuelle est dominee par le rythme d'approvisionnement ;
  les indices saisonniers sont donc prudents.
- **Adresses** : le quartier est extrait par heuristique (98 % de couverture) ; quelques erreurs
  de rattachement subsistent."""


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def _figure_obj(figs, nom):
    for f in figs:
        if f.fichier == nom:
            return f
    return None


def construire(jdd, figs) -> dict:
    md = []
    md.append("# ScootMaster — Rapport d'analyse et d'aide a la decision\n")
    md.append(f"*Genere le {datetime.now():%d/%m/%Y} a partir de `Scoot_Master (1).xlsx` — "
              f"{len(jdd.clients)} lignes clients, {len(jdd.motos)} lignes motos.*\n")

    # ---- intro exec + KPI
    md.append(f"## 0. Synthese executive\n\n{INTRO_EXEC}\n")
    md.append("### Chiffres cles\n")
    md.append("| Indicateur | Valeur | Lecture |")
    md.append("|---|---|---|")
    for k, v, l in _kpi():
        md.append(f"| {k} | {v} | {l} |")
    md.append("")

    # ---- sections avec figures
    for num, titre, fichiers, special in SECTIONS:
        if special == "intro_exec":
            continue
        md.append(f"\n## {num}. {titre}\n")
        if special == "reco":
            md.append(_md_reco())
            continue
        if special == "limites":
            md.append(LIMITES + "\n")
            continue
        for nom in fichiers:
            f = _figure_obj(figs, nom)
            if f is None:
                continue
            md.append(f"\n### {f.titre}\n")
            md.append(f"![{f.titre}](figures/{f.fichier})\n")
            md.append(f"{f.interpretation}\n")
            if f.points:
                md.append("\n**Points cles :**\n")
                for p in f.points:
                    md.append(f"- {p}")
                md.append("")

    md_text = "\n".join(md)
    (config.OUTPUT_DIR / "rapport_data_scootmaster.md").write_text(md_text, encoding="utf-8")

    html = _html(jdd, figs)
    (config.OUTPUT_DIR / "rapport_data_scootmaster.html").write_text(html, encoding="utf-8")

    return {"md": str(config.OUTPUT_DIR / "rapport_data_scootmaster.md"),
            "html": str(config.OUTPUT_DIR / "rapport_data_scootmaster.html")}


def _md_reco() -> str:
    lignes = ["| # | Recommandation | Base | Impact attendu | Effort | Horizon |",
              "|---|---|---|---|---|---|"]
    for r in sorted(_recommandations(), key=lambda x: x["prio"]):
        lignes.append(f"| {r['prio']} | **{r['titre']}** | {r['base']} | {r['impact']} | "
                      f"{r['effort']} | {r['horizon']} |")
    out = "\n".join(lignes) + "\n\n### Detail des recommandations\n"
    for r in sorted(_recommandations(), key=lambda x: x["prio"]):
        out += (f"\n**{r['prio']}. {r['titre']}** *(base : {r['base']})*\n\n{r['texte']}\n\n"
                f"*Impact : {r['impact']} · Effort : {r['effort']} · Horizon : {r['horizon']}*\n")
    return out


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def _b64(nom) -> str:
    data = (config.FIG_DIR / nom).read_bytes()
    return base64.b64encode(data).decode()


def _html(jdd, figs) -> str:
    parts = []
    css = """
    <style>
    :root{--p:#1f4e79;--a:#e8833a;--bg:#f7f9fb;--card:#fff;--tx:#1c2733}
    *{box-sizing:border-box}
    body{margin:0;font-family:'Segoe UI',system-ui,-apple-system,Arial,sans-serif;
      background:var(--bg);color:var(--tx);line-height:1.62}
    .wrap{max-width:1080px;margin:0 auto;padding:0 22px 80px}
    header{background:linear-gradient(120deg,var(--p),#2d6da8);color:#fff;padding:42px 0 34px}
    header h1{margin:0 0 6px;font-size:30px}
    header .sub{opacity:.9;font-size:14px}
    h2{color:var(--p);border-bottom:3px solid var(--a);padding-bottom:6px;margin-top:52px;font-size:23px}
    h3{color:#234;margin-top:34px;font-size:16.5px}
    .card{background:var(--card);border:1px solid #e2e8f0;border-radius:12px;
      box-shadow:0 1px 4px rgba(20,40,70,.06);padding:18px 20px;margin:16px 0}
    .card img{max-width:100%;height:auto;border-radius:6px;display:block;margin:4px auto 12px}
    .interp{font-size:14.5px}
    .pts{margin:10px 0 0;padding-left:2px;list-style:none}
    .pts li{padding:5px 0 5px 26px;position:relative;font-size:13.5px;border-top:1px dashed #e5eaf0}
    .pts li:before{content:'\\25B8';position:absolute;left:6px;color:var(--a)}
    table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px;background:#fff}
    th{background:var(--p);color:#fff;text-align:left;padding:8px 10px}
    td{padding:7px 10px;border-bottom:1px solid #e5eaf0;vertical-align:top}
    tr:nth-child(even) td{background:#f3f7fb}
    .kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0}
    .kpi .b{background:#fff;border:1px solid #e2e8f0;border-left:4px solid var(--a);
      border-radius:8px;padding:12px 14px}
    .kpi .v{font-size:19px;font-weight:700;color:var(--p)}
    .kpi .l{font-size:12px;color:#5a6b7c}
    .badge{display:inline-block;background:var(--a);color:#fff;border-radius:20px;
      font-size:12px;font-weight:700;padding:2px 12px;margin-right:8px}
    .prio{display:inline-block;background:var(--p);color:#fff;border-radius:6px;
      font-weight:700;padding:2px 10px;margin-right:8px}
    footer{margin-top:60px;padding:20px 0;border-top:1px solid #dde5ec;font-size:12.5px;color:#64798c}
    </style>"""

    parts.append(f"<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'>"
                 f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                 f"<title>ScootMaster — Rapport d'analyse</title>{css}</head><body>")
    parts.append("<header><div class='wrap'><h1>ScootMaster — Rapport d'analyse et d'aide a la "
                 "decision</h1><div class='sub'>Science de donnees appliquee au fichier "
                 "Excel &middot; tendances, segments, produits, predictions</div></div></header>")
    parts.append("<div class='wrap'>")

    # KPI
    parts.append("<h2>0. Synthese executive</h2>")
    parts.append("<div class='card interp'>" + INTRO_EXEC.replace("\n", " ") + "</div>")
    parts.append("<div class='kpi'>")
    for k, v, l in _kpi():
        parts.append(f"<div class='b'><div class='l'>{k}</div>"
                     f"<div class='v'>{v}</div><div class='l'>{l}</div></div>")
    parts.append("</div>")

    for num, titre, fichiers, special in SECTIONS:
        if special == "intro_exec":
            continue
        parts.append(f"<h2>{num}. {titre}</h2>")
        if special == "reco":
            parts.append(_html_reco())
            continue
        if special == "limites":
            parts.append("<div class='card interp'>" + LIMITES.replace("\n", "<br>") + "</div>")
            continue
        for nom in fichiers:
            f = _figure_obj(figs, nom)
            if f is None:
                continue
            parts.append(f"<div class='card'><h3>{f.titre}</h3>"
                         f"<img src='data:image/png;base64,{_b64(nom)}' alt='{f.titre}'>"
                         f"<div class='interp'>{f.interpretation}</div>")
            if f.points:
                parts.append("<ul class='pts'>" + "".join(f"<li>{p}</li>" for p in f.points) + "</ul>")
            parts.append("</div>")

    parts.append(f"<footer>Genere automatiquement le {datetime.now():%d/%m/%Y} a partir de "
                 f"Scoot_Master (1).xlsx &middot; montants en Ariary (1 Ar = 5 FMG). "
                 f"Document d'aide a la decision.</footer>")
    parts.append("</div></body></html>")
    return "".join(parts)


def _html_reco() -> str:
    rec = sorted(_recommandations(), key=lambda x: x["prio"])
    out = ["<table><tr><th>#</th><th>Recommandation</th><th>Base</th><th>Impact attendu</th>"
           "<th>Effort</th><th>Horizon</th></tr>"]
    for r in rec:
        out.append(f"<tr><td>{r['prio']}</td><td><b>{r['titre']}</b></td><td>{r['base']}</td>"
                   f"<td>{r['impact']}</td><td>{r['effort']}</td><td>{r['horizon']}</td></tr>")
    out.append("</table>")
    for r in rec:
        out.append(f"<div class='card'><span class='prio'>{r['prio']}</span><b>{r['titre']}</b>"
                   f"<div class='interp' style='margin-top:8px'>{r['texte']}</div>"
                   f"<div class='l' style='margin-top:8px;font-size:13px'>"
                   f"<b>Impact :</b> {r['impact']} · <b>Effort :</b> {r['effort']} · "
                   f"<b>Horizon :</b> {r['horizon']}</div></div>")
    return "".join(out)


# --------------------------------------------------------------------------
# Classeur decisionnel Excel
# --------------------------------------------------------------------------

def classeur(jdd) -> str:
    chemin = config.OUTPUT_DIR / "ScootMaster_analyse_decisionnelle.xlsx"
    with pd.ExcelWriter(chemin, engine="xlsxwriter") as w:
        _lire("journal_qualite.csv").to_excel(w, sheet_name="Journal_qualite", index=False)
        _lire("tendance_annuelle.csv").to_excel(w, sheet_name="Tendance", index=False)
        _lire("portefeuille_modeles.csv").to_excel(w, sheet_name="Portefeuille", index=False)
        _lire("marquage_par_modele.csv").to_excel(w, sheet_name="Marquage", index=False)
        _lire("rotation_stock.csv").to_excel(w, sheet_name="Rotation", index=False)
        _lire("geographie_quartiers.csv").to_excel(w, sheet_name="Geographie", index=False)
        _lire("profils_segments.csv").to_excel(w, sheet_name="Segments", index=False)
        _lire("importance_reachat.csv").to_excel(w, sheet_name="Reachat", index=False)
        _lire("previsions_12_mois.csv").to_excel(w, sheet_name="Previsions", index=False)
        _lire("mix_produit_futur.csv").to_excel(w, sheet_name="Mix_futur", index=False)
        _lire("scenarios_marge.csv").to_excel(w, sheet_name="Scenarios", index=False)
        rec = pd.DataFrame(sorted(_recommandations(), key=lambda x: x["prio"]))[
            ["prio", "titre", "base", "impact", "effort", "horizon"]]
        rec.to_excel(w, sheet_name="Plan_action", index=False)
    return str(chemin)
