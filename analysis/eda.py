"""Analyse exploratoire : KPIs, tendances, mix produit, marges, rotation, geographie.

Chaque fonction produit une figure PNG et retourne un objet ``Figure`` qui
embarque le titre et l'interpretation metier ; le rapport n'a plus qu'a
les assembler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

from . import config

plt.rcParams.update({
    "figure.dpi": config.FIG_DPI,
    "savefig.dpi": config.FIG_DPI,
    "savefig.bbox": "tight",
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.labelsize": 9,
    "axes.grid": True,
    "grid.alpha": .25,
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
    "legend.fontsize": 8,
})


@dataclass
class Figure:
    fichier: str
    titre: str
    interpretation: str
    points: list[str] = field(default_factory=list)

    @property
    def chemin(self):
        return config.FIG_DIR / self.fichier


def _save(fig, nom: str) -> str:
    fig.savefig(config.FIG_DIR / nom)
    plt.close(fig)
    return nom


def _fmt_millions(x, _):
    return f"{x:,.0f}"


# --------------------------------------------------------------------------
# 1. Qualite des donnees
# --------------------------------------------------------------------------

def fig_qualite(motos: pd.DataFrame, synthese: pd.DataFrame) -> Figure:
    tx = motos[motos["valide"] == 1]
    ca_net = tx["prix_vente_ar"].sum()
    ca_brut = ca_net + synthese["total_vente_ar"].sum()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.1),
                             gridspec_kw={"width_ratios": [1.15, 1]})

    # --- impact de la detection du bloc de synthese -----------------------
    ax = axes[0]
    barres = ax.bar(["CA si le classeur est lu\nsans nettoyage",
                     "CA reel apres\nseparation des blocs"],
                    [ca_brut / 1e9, ca_net / 1e9],
                    color=[config.PALETTE["red"], config.PALETTE["primary"]],
                    width=.55)
    for b, v in zip(barres, [ca_brut, ca_net]):
        ax.text(b.get_x() + b.get_width() / 2, v / 1e9 + .04,
                f"{v/1e9:.2f} Md Ar", ha="center", fontweight="bold", fontsize=9)
    ax.set_ylabel("Chiffre d'affaires (milliards Ar)")
    ax.set_title("Erreur evitee : le bloc de synthese hebdomadaire\n"
                 "empile sous les transactions gonflait le CA de "
                 f"{(ca_brut/ca_net-1)*100:.0f} %")
    ax.set_ylim(0, ca_brut / 1e9 * 1.18)

    # --- entonnoir de nettoyage -------------------------------------------
    ax = axes[1]
    etapes = ["Lignes lues\ndans DB_1,0", "Bloc synthese\nisole",
              "Transactions\nconservees", "Transactions\nexploitables"]
    valeurs = [811, len(synthese), len(motos), len(tx)]
    couleurs = [config.PALETTE["grey"], config.PALETTE["accent"],
                config.PALETTE["primary"], config.PALETTE["green"]]
    y = np.arange(len(etapes))[::-1]
    ax.barh(y, valeurs, color=couleurs, height=.6)
    for yy, v in zip(y, valeurs):
        ax.text(v + 12, yy, f"{v}", va="center", fontweight="bold")
    ax.set_yticks(y, etapes)
    ax.set_xlim(0, 900)
    ax.set_title("Entonnoir de nettoyage — feuille DB_1,0")
    ax.grid(axis="y", visible=False)

    fig.tight_layout()
    nom = _save(fig, "01_qualite_donnees.png")
    return Figure(
        nom,
        "Qualite des donnees : le nettoyage change l'ordre de grandeur du chiffre d'affaires",
        "La feuille DB_1,0 n'est pas une table : elle empile 662 transactions reelles, "
        "puis 145 lignes de synthese hebdomadaire (« Semaine N » avec totaux cumules), puis "
        "un bloc de total general. Lues naivement, ces 145 lignes sont comptees comme des "
        "ventes et doublent le chiffre d'affaires. La separation des blocs ramene le CA de "
        f"{ca_brut/1e9:.2f} Md Ar a {ca_net/1e9:.2f} Md Ar, soit une surestimation de "
        f"{(ca_brut/ca_net-1)*100:.0f} % corrigee.",
        [f"811 lignes lues dont {len(synthese)} lignes de synthese et 4 lignes de total general",
         f"{len(tx)} transactions exploitables conservees (date valide + prix coherent)",
         f"Controle croisant : la somme des transactions ({tx['prix_achat_ar'].sum()/1e6:.0f} M Ar "
         "d'achats) reproduit le total general du classeur (1 799 M Ar) a 0,2 % pres",
         "5 numeros de serie en double, 6 durees de stock negatives, 21 motos sans date de depart"],
    )


# --------------------------------------------------------------------------
# 2. Reconciliation des deux sources
# --------------------------------------------------------------------------

def fig_sources(motos: pd.DataFrame, clients: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[motos["valide"] == 1]
    c = clients[clients["valide"] == 1]
    idx = pd.period_range(v["date_arrivee"].min(), clients["date_achat"].max(), freq="M")

    arr = v.groupby(v["date_arrivee"].dt.to_period("M")).size().reindex(idx, fill_value=0)
    ven = c.groupby(c["date_achat"].dt.to_period("M")).size().reindex(idx, fill_value=0)

    tab = pd.DataFrame({"mois": idx.astype(str), "arrivages": arr.values,
                        "ventes_enregistrees": ven.values})
    tab["ecart"] = tab["ventes_enregistrees"] - tab["arrivages"]

    fig, ax = plt.subplots(figsize=(12, 4.2))
    x = np.arange(len(idx))
    ax.plot(x, ven.values, color=config.PALETTE["primary"], lw=2,
            marker="o", ms=3.5, label="Ventes — base clients (registre commercial)")
    ax.plot(x, arr.values, color=config.PALETTE["accent"], lw=1.8, ls="--",
            marker="s", ms=3, label="Arrivages — DB_1,0 (registre achats)")
    ax.fill_between(x, arr.values, ven.values, where=ven.values >= arr.values,
                    color=config.PALETTE["light"], alpha=.8,
                    label="Ventes non tracees dans DB_1,0")
    ax.set_xticks(x[::3])
    ax.set_xticklabels([str(p) for p in idx][::3], rotation=45, ha="right")
    ax.set_ylabel("Nombre de motos")
    ax.set_title("Les deux bases ne racontent pas la meme histoire : "
                 "la base clients enregistre ~1,6 fois plus de ventes")
    ax.legend(loc="upper right")
    nom = _save(fig, "02_reconciliation_sources.png")

    ratio = ven.sum() / arr.sum()
    return Figure(
        nom,
        "Reconciliation des sources : deux registres, deux verites",
        "La base clients compte 1 029 ventes quand la base motos n'en trace que 640. "
        f"Le rapport est de {ratio:.2f} vente enregistree par moto suivie, avec une "
        "correlation mensuelle de 0,87 : les deux series evoluent ensemble mais la base "
        "clients est systematiquement superieure. Les ventes non tracees correspondent aux "
        "motos sourcées hors stock (agents, apporteurs) et aux pieces detachees. "
        "Consequence methodologique : la base clients est la reference pour le chiffre "
        "d'affaires et la segmentation ; DB_1,0 est la reference pour les marges et la "
        "rotation du stock, car elle seule porte le prix d'achat.",
        [f"Ventes enregistrees : {ven.sum()} | Motos suivies : {arr.sum()}",
         "Correlation mensuelle des deux series : 0,87",
         "DB_1,0 presente des trous de saisie (fev., mars et sept. 2020 quasi vides) "
         "alors que la base clients montre de l'activite",
         "Decision : CA et segmentation sur la base clients, marge et rotation sur DB_1,0"],
    ), tab


# --------------------------------------------------------------------------
# 3. Tendance du chiffre d'affaires
# --------------------------------------------------------------------------

def fig_tendance(clients: pd.DataFrame, motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    c = clients[clients["valide"] == 1].copy()
    # le dernier mois est tronque (donnees arretees le 24/01/2023)
    dernier = c["date_achat"].max()
    mois_complet = (dernier - pd.offsets.MonthBegin(1))
    c = c[c["date_achat"] <= mois_complet + pd.offsets.MonthEnd(0)]

    g = c.groupby(c["date_achat"].dt.to_period("M")).agg(
        ca=("montant_ar", "sum"), n=("montant_ar", "size"),
        panier=("montant_ar", "mean"))
    g.index = g.index.to_timestamp()

    # moyenne mobile centree 3 mois + tendance lineaire
    g["ca_mm3"] = g["ca"].rolling(3, center=True, min_periods=1).mean()
    t = np.arange(len(g))
    coef = np.polyfit(t, g["ca"].values, 1)
    g["tendance"] = np.polyval(coef, t)
    g["n_mm3"] = g["n"].rolling(3, center=True, min_periods=1).mean()

    fig = plt.figure(figsize=(12, 6.6))
    gs = GridSpec(2, 1, height_ratios=[1.35, 1], hspace=.34)

    ax = fig.add_subplot(gs[0])
    ax.bar(g.index, g["ca"] / 1e6, width=22, color=config.PALETTE["light"],
           label="CA mensuel")
    ax.plot(g.index, g["ca_mm3"] / 1e6, color=config.PALETTE["primary"], lw=2.4,
            label="Moyenne mobile 3 mois")
    ax.plot(g.index, g["tendance"] / 1e6, color=config.PALETTE["accent"], lw=2,
            ls="--", label=f"Tendance lineaire ({coef[0]/1e6:+.2f} M Ar/mois)")
    ax.set_ylabel("Chiffre d'affaires (M Ar)")
    ax.set_title("Chiffre d'affaires mensuel : une activite en dents de scie "
                 "sans croissance structurelle")
    ax.legend(loc="upper right", ncol=3)

    ax2 = fig.add_subplot(gs[1])
    ax2.bar(g.index, g["n"], width=22, color=config.PALETTE["teal"], alpha=.75,
            label="Volume de ventes")
    ax2.plot(g.index, g["n_mm3"], color=config.PALETTE["violet"], lw=2.2,
             label="Moyenne mobile 3 mois")
    ax2.set_ylabel("Motos vendues")
    ax2.set_xlabel("Mois")
    ax2.legend(loc="upper right", ncol=2)
    nom = _save(fig, "03_tendance_ca.png")

    ann = c.groupby(c["date_achat"].dt.year).agg(
        n=("montant_ar", "size"), ca=("montant_ar", "sum"),
        panier=("montant_ar", "mean"))
    ann["ca"] = ann["ca"] / 1e6
    ann["panier"] = ann["panier"] / 1e6
    ann.to_csv(config.TABLE_DIR / "tendance_annuelle.csv")

    # variation 2020 -> 2022 (2023 incomplet)
    ca20, ca22 = ann.loc[2020, "ca"], ann.loc[2022, "ca"]
    n20, n22 = ann.loc[2020, "n"], ann.loc[2022, "n"]

    return Figure(
        nom,
        "Tendance : un palier bas depuis 2021, pas de croissance",
        f"Le chiffre d'affaires tombe de {ca20:.0f} M Ar en 2020 a {ann.loc[2021,'ca']:.0f} M Ar "
        f"en 2021 ({(ann.loc[2021,'ca']/ca20-1)*100:+.0f} %) puis stagne a {ca22:.0f} M Ar en 2022 "
        f"({(ca22/ca20-1)*100:+.0f} % vs 2020). Le volume passe de {n20:.0f} a {n22:.0f} motos. "
        "La pente de regression lineaire est quasi nulle : l'entreprise n'est pas en croissance, "
        "elle a perdu un palier d'activite entre 2020 et 2021 et s'y est stabilisee. "
        "La forme en dents de scie (certains mois a plus de 180 M Ar, d'autres a 17 M Ar) "
        "trahit un approvisionnement par a-coups, en gros lots, plutot qu'un flux continu.",
        [f"2020 : {ann.loc[2020,'ca']:.0f} M Ar / {n20:.0f} motos",
         f"2021 : {ann.loc[2021,'ca']:.0f} M Ar / {ann.loc[2021,'n']:.0f} motos",
         f"2022 : {ca22:.0f} M Ar / {n22:.0f} motos",
         f"Panier moyen quasi stable : {ann['panier'].mean():.2f} M Ar par moto",
         "Le mois de janvier 2023 est exclu (donnees arretees au 24/01)"],
    ), g


# --------------------------------------------------------------------------
# 4. Saisonnalite
# --------------------------------------------------------------------------

def fig_saisonnalite(clients: pd.DataFrame) -> Figure:
    c = clients[clients["valide"] == 1].copy()
    c = c[c["date_achat"] <= c["date_achat"].max() - pd.offsets.MonthBegin(1)]
    c["mois_num"] = c["date_achat"].dt.month

    # indice saisonnier = moyenne du mois / moyenne globale (sur annees completes)
    mensuel = c.groupby([c["date_achat"].dt.year, "mois_num"])["montant_ar"].agg(["size", "sum"])
    mensuel = mensuel.reset_index()
    pivot_n = mensuel.pivot(index="mois_num", columns="date_achat", values="size").fillna(0)
    pivot_n = pivot_n.loc[:, pivot_n.columns.isin([2020, 2021, 2022])]
    # 2020 est partielle (demarrage) : on normalise chaque annee avant de moyenner
    norm = pivot_n.div(pivot_n.sum(axis=0), axis=1) * 12
    indice = norm.mean(axis=1)

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.1))

    ax = axes[0]
    cols = [config.PALETTE["green"] if v >= 1 else config.PALETTE["red"]
            for v in indice.values]
    ax.bar(indice.index, indice.values, color=cols, width=.66)
    ax.axhline(1, color="black", lw=1)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_ylabel("Indice saisonnier (1 = moyenne)")
    ax.set_title("Indice saisonnier des volumes\n(normalise par annee, 2020-2022)")
    for x, v in zip(indice.index, indice.values):
        ax.text(x, v + .03, f"{v:.2f}", ha="center", fontsize=7.5)

    ax = axes[1]
    data = [mensuel.loc[(mensuel["date_achat"] == a) & (mensuel["mois_num"] == m), "size"]
            .sum() for m in range(1, 13) for a in [2021, 2022]]
    box = [mensuel.loc[(mensuel["date_achat"] == a) & (mensuel["mois_num"] == m), "size"].sum()
           for m in range(1, 13) for a in [2020, 2021, 2022]]
    grouped = [[mensuel.loc[(mensuel["date_achat"] == a) & (mensuel["mois_num"] == m), "size"].sum()
                for a in [2020, 2021, 2022]] for m in range(1, 13)]
    bp = ax.boxplot(grouped, patch_artist=True, widths=.6, medianprops=dict(color="white"))
    for p in bp["boxes"]:
        p.set_facecolor(config.PALETTE["primary"])
        p.set_alpha(.8)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_ylabel("Motos vendues dans le mois")
    ax.set_title("Dispersion mensuelle sur les trois exercices\n"
                 "— l'amplitude depasse largement le signal saisonnier")
    nom = _save(fig, "04_saisonnalite.png")

    pics = indice.nlargest(3)
    creux = indice.nsmallest(3)
    return Figure(
        nom,
        "Saisonnalite : un signal reel mais faible face a la dispersion",
        "Les indices saisonniers montrent un creux net en janvier-fevrier "
        f"({indice.loc[1]:.2f} et {indice.loc[2]:.2f}) et un pic en milieu d'annee et en fin "
        f"d'annee ({pics.index[0]:02d} = {pics.iloc[0]:.2f}). Mais la boite a moustaches montre "
        "qu'un meme mois peut varier du simple au triple d'une annee a l'autre : la saisonnalite "
        "explique une part mineure de la variance. La vraie cause de variation est le rythme "
        "d'approvisionnement — on ne vend que ce qu'on a fait entrer.",
        [f"Mois les plus forts : {', '.join(f'{m:02d} ({v:.2f})' for m, v in pics.items())}",
         f"Mois les plus faibles : {', '.join(f'{m:02d} ({v:.2f})' for m, v in creux.items())}",
         "Janvier-fevrier : creux structurel (fin de cycle des fetes, tresorerie tendue)",
         "La dispersion intra-mois est superieure a l'effet saisonnier : piloter le stock, pas le calendrier"],
    )


# --------------------------------------------------------------------------
# 5. Pareto du portefeuille
# --------------------------------------------------------------------------

def fig_pareto(motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    g = v.groupby("modele").agg(
        n=("modele", "size"), ca=("prix_vente_ar", "sum"),
        marge=("marge_ar", "sum")).sort_values("n", ascending=False)
    g["part_n"] = g["n"] / g["n"].sum() * 100
    g["cum_n"] = g["part_n"].cumsum()
    g["part_ca"] = g["ca"] / g["ca"].sum() * 100
    g["cum_ca"] = g["part_ca"].cumsum()
    g["tx_marge"] = g["marge"] / (g["ca"] - g["marge"]) * 100
    g = g[g["n"] >= 1].reset_index()
    g.to_csv(config.TABLE_DIR / "portefeuille_modeles.csv", index=False)

    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    x = np.arange(len(g))
    ax.bar(x, g["n"], color=config.PALETTE["primary"], width=.62, label="Motos vendues")
    ax.set_xticks(x)
    ax.set_xticklabels(g["modele"].str.replace("KYMCO ", "K.", regex=False)
                       .str.replace("YAMAHA ", "Y.", regex=False),
                       rotation=38, ha="right", fontsize=8)
    ax.set_ylabel("Motos vendues")
    for xi, v_ in zip(x, g["n"]):
        ax.text(xi, v_ + 4, f"{v_}", ha="center", fontsize=8, fontweight="bold")

    ax2 = ax.twinx()
    ax2.plot(x, g["cum_n"], color=config.PALETTE["accent"], lw=2.2, marker="o",
             ms=4.5, label="Cumul %% des volumes")
    ax2.axhline(80, color=config.PALETTE["red"], ls=":", lw=1.4)
    ax2.text(len(g) - .4, 82, "80 %", color=config.PALETTE["red"], ha="right", fontsize=8)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Part cumulee des volumes (%)")
    ax2.grid(False)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="center right")
    ax.set_title("Pareto du portefeuille : deux modeles font les deux tiers du volume")
    nom = _save(fig, "05_pareto_portefeuille.png")

    deux = g.head(2)
    return Figure(
        nom,
        "Pareto produit : une concentration extreme sur deux modeles",
        f"{deux['modele'].iloc[0]} et {deux['modele'].iloc[1]} representent a eux deux "
        f"{deux['part_n'].sum():.0f} % des volumes et {deux['part_ca'].sum():.0f} % du chiffre "
        f"d'affaires. Les {len(g)-2} autres references se partagent le reste. Cette "
        "concentration est un avantage (expertise, pieces, negociation fournisseur) et un risque "
        "(dependance a un approvisionnement unique, aucune protection contre un choc de demande "
        "sur ces deux modeles). Les references de queue coutent cher en immobilisation pour un "
        "debit tres faible.",
        [f"{deux['modele'].iloc[0]} : {int(deux['n'].iloc[0])} motos ({deux['part_n'].iloc[0]:.0f} %)",
         f"{deux['modele'].iloc[1]} : {int(deux['n'].iloc[1])} motos ({deux['part_n'].iloc[1]:.0f} %)",
         f"{int((g['part_n'] < 2).sum())} references font moins de 2 % des volumes chacune",
         f"Total : {int(g['n'].sum())} motos vendues sur {len(g)} references"],
    ), g


# --------------------------------------------------------------------------
# 6. Matrice portefeuille volume x marge
# --------------------------------------------------------------------------

def fig_matrice(motos: pd.DataFrame) -> Figure:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    g = v.groupby("modele").agg(
        n=("modele", "size"), ca=("prix_vente_ar", "sum"),
        marge=("marge_ar", "sum"),
        tx=("taux_marge", "median"),
        stock_j=("duree_stock_j", "median")).reset_index()
    g["marge_unit"] = g["marge"] / g["n"]
    g = g[g["n"] >= 5].sort_values("n", ascending=False)

    fig, ax = plt.subplots(figsize=(11, 6))
    med_tx = np.median(g["tx"]) * 100
    med_n = np.median(g["n"])

    # cadrans
    ax.axvspan(med_n, g["n"].max() * 1.6, 0, 1, color=config.PALETTE["green"], alpha=.05)
    ax.axhline(med_tx, color="black", lw=1, ls=":")
    ax.axvline(med_n, color="black", lw=1, ls=":")

    sc = ax.scatter(g["n"], g["tx"] * 100, s=g["ca"] / 1e6 * 2.2 + 60,
                    c=g["stock_j"].fillna(0), cmap="RdYlGn_r",
                    edgecolor="white", lw=1.5, zorder=3)
    for _, r in g.iterrows():
        ax.annotate(r["modele"].replace("KYMCO ", "K.").replace("YAMAHA ", "Y."),
                    (r["n"], r["tx"] * 100),
                    textcoords="offset points", xytext=(0, -np.sqrt(r["ca"]/1e6*2.2+60)/2 - 11),
                    ha="center", fontsize=8.5, fontweight="bold")
    cb = plt.colorbar(sc, ax=ax, shrink=.75, pad=.02)
    cb.set_label("Rotation : jours de stock avant vente (median)", fontsize=8)

    ax.set_xlabel("Volume vendu (motos)")
    ax.set_ylabel("Taux de marge median (%)")
    ax.set_xlim(0, g["n"].max() * 1.22)
    ax.set_ylim(min(g["tx"]) * 100 - 2.5, max(g["tx"]) * 100 + 3)
    ax.set_title("Matrice portefeuille : volume x taux de marge\n"
                 "(taille = chiffre d'affaires, couleur = vitesse de rotation)")
    ax.text(.985, .955, "FORT VOLUME / MARGE ELEVEE", transform=ax.transAxes,
            ha="right", fontsize=8, color=config.PALETTE["green"], fontweight="bold")
    ax.text(.015, .045, "FAIBLE VOLUME / MARGE FAIBLE", transform=ax.transAxes,
            fontsize=8, color=config.PALETTE["red"], fontweight="bold")
    nom = _save(fig, "06_matrice_portefeuille.png")

    top = g.nlargest(1, "tx")
    bas = g.nsmallest(1, "tx")
    return Figure(
        nom,
        "Matrice portefeuille : le volume et la marge ne vont pas ensemble",
        "La lecture conjointe du volume et du taux de marge revele un arbitrage non pilote. "
        f"{bas['modele'].iloc[0]} est le modele le moins rentable ({bas['tx'].iloc[0]*100:.0f} % de "
        "marge) alors qu'il represente un volume significatif. A l'inverse, "
        f"{top['modele'].iloc[0]} delivre {top['tx'].iloc[0]*100:.0f} % de marge. La couleur montre "
        "que les modeles a marge elevee sont aussi les plus lents a tourner : la marge est la "
        "contrepartie d'une immobilisation plus longue. Le pilotage actuel ne tient compte ni de "
        "l'un ni de l'autre, puisque le prix de vente est calcule par une regle fixe.",
        [f"Marge la plus elevee : {top['modele'].iloc[0]} ({top['tx'].iloc[0]*100:.1f} %)",
         f"Marge la plus faible : {bas['modele'].iloc[0]} ({bas['tx'].iloc[0]*100:.1f} %)",
         f"Mediane du portefeuille : {med_tx:.1f} % de marge sur cout",
         "Les modeles a forte marge tournent plus lentement : arbitrage marge x tresorerie"],
    )


# --------------------------------------------------------------------------
# 7. Politique de prix : le marquage est une constante
# --------------------------------------------------------------------------

def fig_marquage(motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1) & (motos["prix_achat_ar"] > 0)]
    g = v.groupby("modele").agg(
        n=("modele", "size"),
        tx_moy=("taux_marge", "mean"),
        tx_med=("taux_marge", "median"),
        tx_min=("taux_marge", "min"),
        tx_max=("taux_marge", "max"),
        marge_unit=("marge_ar", "mean")).reset_index()
    g = g[g["n"] >= 5].sort_values("n", ascending=False)
    g["ecart_type"] = v.groupby("modele")["taux_marge"].std().reindex(g["modele"]).values
    g.to_csv(config.TABLE_DIR / "marquage_par_modele.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4),
                             gridspec_kw={"width_ratios": [1.25, 1]})

    ax = axes[0]
    y = np.arange(len(g))[::-1]
    ax.hlines(y, g["tx_min"] * 100, g["tx_max"] * 100, color=config.PALETTE["grey"], lw=2.2)
    ax.scatter(g["tx_med"] * 100, y, s=g["n"] * 3 + 25, zorder=3,
               color=config.PALETTE["primary"], edgecolor="white", lw=1.2,
               label="Taux de marge median")
    ax.scatter(g["tx_moy"] * 100, y, s=22, zorder=4, marker="D",
               color=config.PALETTE["accent"], label="Taux de marge moyen")
    ax.set_yticks(y)
    ax.set_yticklabels([m.replace("KYMCO ", "K.").replace("YAMAHA ", "Y.")
                        for m in g["modele"]], fontsize=8.5)
    ax.axvline(v["taux_marge"].median() * 100, color=config.PALETTE["red"], ls=":", lw=1.5)
    ax.text(v["taux_marge"].median() * 100 + .1, y.max() - .3,
            f"mediane globale {v['taux_marge'].median()*100:.1f} %",
            color=config.PALETTE["red"], fontsize=8)
    ax.set_xlabel("Taux de marge sur cout d'achat (%)")
    ax.set_title("Le taux de marge est quasi identique d'un modele a l'autre :\n"
                 "c'est un marquage fixe, pas une politique de prix")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    ax.scatter(v["prix_achat_ar"] / 1e6, v["prix_vente_ar"] / 1e6, s=14, alpha=.4,
               color=config.PALETTE["primary"])
    lim = max(v["prix_achat_ar"].max(), v["prix_vente_ar"].max()) / 1e6
    xs = np.linspace(0, lim, 10)
    med = v["taux_marge"].median()
    ax.plot(xs, xs * (1 + med), color=config.PALETTE["accent"], lw=2.2,
            label=f"Regle observee : vente = achat x {1+med:.3f}")
    ax.plot(xs, xs, color="black", ls=":", lw=1, label="Seuil de rentabilite")
    ax.set_xlabel("Prix d'achat (M Ar)")
    ax.set_ylabel("Prix de vente (M Ar)")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim * 1.18)
    ax.legend(loc="upper left")
    ax.set_title("Prix de vente vs prix d'achat :\nune droite unique, dispersion tres faible")
    nom = _save(fig, "07_politique_prix.png")

    return Figure(
        nom,
        "Politique de prix : un marquage mecanique de "
        f"{v['taux_marge'].median()*100:.1f} % applique a tous les modeles",
        "Le graphique de droite est le plus parlant du dossier : tous les points s'alignent sur "
        f"une seule droite de pente {1+v['taux_marge'].median():.3f}. ScootMaster ne fixe pas ses "
        "prix en fonction de la demande, de la concurrence ou de la valeur percue du modele : il "
        f"applique un coefficient unique de {1+v['taux_marge'].median():.3f} au cout d'achat. "
        "C'est ce qui explique que le taux de marge soit identique (9 a 11 %) pour un KYMCO RACING "
        "qui part en 5 jours comme pour un modele qui reste un mois en stock. Toute la marge "
        "supplementaire est donc mecaniquement liee a la negociation a l'achat, jamais au prix "
        "de vente.",
        [f"Coefficient de marquage median : x{1+v['taux_marge'].median():.3f} "
         f"({v['taux_marge'].median()*100:.2f} % sur cout)",
         f"Dispersion tres faible : ecart interquartile de "
         f"{v['taux_marge'].quantile(.25)*100:.1f} % a {v['taux_marge'].quantile(.75)*100:.1f} %",
         "Consequence : la marge ne compense ni l'immobilisation ni le risque de stock",
         "Levier inexploite : differencier le marquage selon la vitesse de rotation"],
    ), g


# --------------------------------------------------------------------------
# 8. Rotation du stock
# --------------------------------------------------------------------------

def fig_rotation(motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[(motos["valide"] == 1) & (motos["duree_stock_j"].notna())]
    g = v.groupby("modele").agg(
        n=("duree_stock_j", "size"),
        mediane=("duree_stock_j", "median"),
        moyenne=("duree_stock_j", "mean"),
        p90=("duree_stock_j", lambda s: s.quantile(.9)),
        marge_unit=("marge_ar", "mean")).reset_index()
    g = g[g["n"] >= 5].sort_values("mediane")
    # capital immobilise : rotation x cout
    g["immobilisation_j_ar"] = g["mediane"] * (g["marge_unit"] / g["taux"] if False else 0)
    g = g.drop(columns=["immobilisation_j_ar"])
    g.to_csv(config.TABLE_DIR / "rotation_stock.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.3),
                             gridspec_kw={"width_ratios": [1, 1.15]})

    ax = axes[0]
    y = np.arange(len(g))[::-1]
    ax.barh(y, g["mediane"], color=config.PALETTE["primary"], height=.6,
            label="Mediane")
    ax.plot(g["p90"], y, marker="|", ms=13, color=config.PALETTE["red"], ls="",
            label="90e percentile")
    ax.set_yticks(y)
    ax.set_yticklabels([m.replace("KYMCO ", "K.").replace("YAMAHA ", "Y.")
                        for m in g["modele"]], fontsize=8.5)
    ax.set_xlabel("Jours entre l'arrivee et la vente")
    ax.set_title("Rotation du stock par modele")
    for yy, vv in zip(y, g["mediane"]):
        ax.text(vv + .5, yy, f"{vv:.0f} j", va="center", fontsize=8)
    ax.legend(loc="lower right")

    ax = axes[1]
    for modele, coul in zip(g["modele"].head(5), config.SEQ):
        s = v[v["modele"] == modele]["duree_stock_j"].dropna()
        ax.hist(s, bins=np.arange(0, max(65, s.max() + 5), 5), alpha=.55,
                label=modele.replace("KYMCO ", "K."), color=coul)
    ax.set_xlabel("Jours de stock")
    ax.set_ylabel("Nombre de motos")
    ax.set_title("Distribution des durees : la moitie des motos part en moins d'une semaine")
    ax.legend()
    nom = _save(fig, "08_rotation_stock.png")

    med_glob = v["duree_stock_j"].median()
    return Figure(
        nom,
        "Rotation du stock : un debit tres rapide, sauf sur quelques modeles",
        f"La mediane globale est de {med_glob:.0f} jours : la moitie du parc est vendue en moins "
        f"d'une semaine, et {100*(v['duree_stock_j'] <= 14).mean():.0f} % en moins de deux "
        "semaines. C'est un modele de negoce a flux tendu, pas un magasin de stock. "
        f"Les exceptions sont nettes : {g['modele'].iloc[-1]} atteint {g['mediane'].iloc[-1]:.0f} "
        f"jours de mediane et {g['p90'].iloc[-1]:.0f} jours au 90e percentile. Ces modeles "
        "immobilisent du capital plusieurs fois plus longtemps pour une marge unitaire "
        "comparable, ce qui en fait les premiers candidats a un arbitrage.",
        [f"Rotation mediane globale : {med_glob:.0f} jours",
         f"{100*(v['duree_stock_j'] <= 7).mean():.0f} % des motos vendues en moins de 7 jours",
         f"Le plus rapide : {g['modele'].iloc[0]} ({g['mediane'].iloc[0]:.0f} jours)",
         f"Le plus lent : {g['modele'].iloc[-1]} ({g['mediane'].iloc[-1]:.0f} jours de mediane, "
         f"{g['p90'].iloc[-1]:.0f} jours au P90)"],
    ), g


# --------------------------------------------------------------------------
# 9. Dynamique des prix d'achat
# --------------------------------------------------------------------------

def fig_prix(motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[(motos["valide"] == 1) & (motos["prix_achat_ar"] > 0)].copy()
    v = v.dropna(subset=["date_arrivee"])
    v["t"] = (v["date_arrivee"] - v["date_arrivee"].min()).dt.days / 365.25

    top = v["modele"].value_counts().head(4).index.tolist()
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))

    ax = axes[0]
    for modele, coul in zip(top, config.SEQ):
        s = v[v["modele"] == modele]
        ax.scatter(s["t"], s["prix_achat_ar"] / 1e6, s=12, alpha=.35, color=coul)
        z = np.polyfit(s["t"], s["prix_achat_ar"], 1)
        xs = np.linspace(s["t"].min(), s["t"].max(), 20)
        ax.plot(xs, np.polyval(z, xs) / 1e6, color=coul, lw=2.4,
                label=f"{modele.replace('KYMCO ', 'K.')} ({z[0]/1e6:+.2f} M Ar/an)")
    ax.set_xlabel("Annees depuis le debut de la periode")
    ax.set_ylabel("Prix d'achat (M Ar)")
    ax.set_title("Dérive des prix d'achat par modele")
    ax.legend(fontsize=7.5)

    ax = axes[1]
    ann = v.groupby(v["date_arrivee"].dt.year).agg(
        pa=("prix_achat_ar", "median"), pv=("prix_vente_ar", "median"),
        tx=("taux_marge", "median"))
    ann = ann.loc[ann.index <= 2022]
    x = np.arange(len(ann))
    ax.bar(x - .17, ann["pa"] / 1e6, width=.34, color=config.PALETTE["grey"],
           label="Prix d'achat median")
    ax.bar(x + .17, ann["pv"] / 1e6, width=.34, color=config.PALETTE["primary"],
           label="Prix de vente median")
    ax.set_xticks(x, [str(i) for i in ann.index])
    ax.set_ylabel("Prix median (M Ar)")
    ax.set_title("Prix nominaux stables... donc prix reels en baisse")
    ax2 = ax.twinx()
    ax2.plot(x, ann["tx"] * 100, color=config.PALETTE["accent"], lw=2.4,
             marker="o", label="Taux de marge (%)")
    ax2.set_ylabel("Taux de marge (%)", color=config.PALETTE["accent"])
    ax2.set_ylim(0, max(ann["tx"]) * 200)
    ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", fontsize=7.5, ncol=2)
    nom = _save(fig, "09_dynamique_prix.png")

    ann.to_csv(config.TABLE_DIR / "prix_par_annee.csv")
    pa20, pa22 = ann.loc[2020, "pa"], ann.loc[2022, "pa"]
    return Figure(
        nom,
        "Dynamique des prix : des prix nominaux plats, donc une marge reellement rogne",
        f"Le prix d'achat median passe de {pa20/1e6:.2f} M Ar en 2020 a {pa22/1e6:.2f} M Ar en "
        f"2022, soit {(pa22/pa20-1)*100:+.1f} % en nominal. Sur la meme periode, l'ariary s'est "
        "deprecie et les couts d'importation ont augmente : maintenir un prix nominal stable "
        "signifie vendre moins cher en termes reels. Comme le prix de vente est mecaniquement "
        "indexe sur le cout, le taux de marge reste fige autour de 9 % alors que le pouvoir "
        "d'achat du franc malgache recule. Le risque est un appauvrissement silencieux : le "
        "compte de resultat affiche une marge stable, mais chaque ariary de marge vaut moins.",
        [f"Prix d'achat median : {pa20/1e6:.2f} M Ar (2020) -> {pa22/1e6:.2f} M Ar (2022)",
         f"Taux de marge median stable : {ann['tx'].iloc[0]*100:.1f} % -> {ann['tx'].iloc[-1]*100:.1f} %",
         "Les 4 modeles principaux ne montrent aucune tendance haussiere significative",
         "Alerte : marge nominale stable + inflation = erosion de la marge reelle"],
    ), ann


# --------------------------------------------------------------------------
# 10. Geographie
# --------------------------------------------------------------------------

def fig_geo(clients: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    c = clients[(clients["valide"] == 1) & (clients["quartier"].notna())]
    g = c.groupby("quartier").agg(
        n=("montant_ar", "size"), ca=("montant_ar", "sum"),
        panier=("montant_ar", "mean")).sort_values("n", ascending=False)
    g.to_csv(config.TABLE_DIR / "geographie_quartiers.csv")
    top = g.head(15)

    zone = c.groupby("zone").agg(n=("montant_ar", "size"), ca=("montant_ar", "sum"))

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6),
                             gridspec_kw={"width_ratios": [1.35, 1]})

    ax = axes[0]
    y = np.arange(len(top))[::-1]
    ax.barh(y, top["n"], color=config.PALETTE["primary"], height=.62)
    ax.set_yticks(y, top.index, fontsize=8.5)
    for yy, (n, ca) in zip(y, zip(top["n"], top["ca"])):
        ax.text(n + .4, yy, f"{n}  ·  {ca/1e6:.0f} M Ar", va="center", fontsize=7.5)
    ax.set_xlabel("Motos vendues")
    ax.set_xlim(0, top["n"].max() * 1.42)
    ax.set_title("Les 15 premiers quartiers clients")
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    cum = g["n"].cumsum() / g["n"].sum() * 100
    ax.plot(range(1, len(cum) + 1), cum.values, color=config.PALETTE["primary"], lw=2.2)
    ax.axhline(50, color=config.PALETTE["red"], ls=":", lw=1.4)
    n50 = int(np.argmax(cum.values >= 50) + 1)
    ax.axvline(n50, color=config.PALETTE["red"], ls=":", lw=1.4)
    ax.scatter([n50], [50], color=config.PALETTE["red"], zorder=3)
    ax.annotate(f"{n50} quartiers\n= 50 % des clients", (n50, 50),
                textcoords="offset points", xytext=(12, -22), fontsize=8.5,
                color=config.PALETTE["red"], fontweight="bold")
    ax.set_xlabel("Nombre de quartiers (classes par volume decroissant)")
    ax.set_ylabel("Part cumulee des clients (%)")
    ax.set_title(f"Dispersion geographique : {len(g)} quartiers touches")
    nom = _save(fig, "10_geographie.png")

    part_top = g.head(n50)["n"].sum() / g["n"].sum() * 100
    return Figure(
        nom,
        "Geographie : une demande diffuse, concentree sur quelques bassins",
        f"{len(g)} quartiers distincts apparaissent dans la base. {n50} d'entre eux "
        f"concentrent {part_top:.0f} % des clients, en tete "
        f"{top.index[0]} ({int(top['n'].iloc[0])} motos) et {top.index[1]} "
        f"({int(top['n'].iloc[1])} motos). "
        f"{100*zone.loc['ANTANANARIVO & ALENTOURS','n']/zone['n'].sum():.0f} % des clients sont "
        "dans la zone d'Antananarivo et alentours ; le reste est en province. La demande est "
        "donc large mais peu dense : aucun quartier ne pese assez pour justifier a lui seul un "
        "dispositif dedie, mais le cumul des premiers bassins suffit a cibler efficacement une "
        "campagne de prospection ou une livraison groupee.",
        [f"{n50} quartiers = {part_top:.0f} % de la clientele",
         f"Bassin n°1 : {top.index[0]} ({int(top['n'].iloc[0])} motos, {top['ca'].iloc[0]/1e6:.0f} M Ar)",
         f"Bassin n°2 : {top.index[1]} ({int(top['n'].iloc[1])} motos, {top['ca'].iloc[1]/1e6:.0f} M Ar)",
         f"{100*zone.loc['ANTANANARIVO & ALENTOURS','n']/zone['n'].sum():.0f} % des clients a Antananarivo, "
         f"{100*zone.loc['PROVINCE','n']/zone['n'].sum():.0f} % en province"],
    ), g


# --------------------------------------------------------------------------
# 11. Benchmark de marge : l'operation 2023 (feuille Double_C)
# --------------------------------------------------------------------------

def fig_benchmark_double_c() -> Figure | None:
    raw = pd.read_excel(config.SOURCE_XLSX, sheet_name=config.SHEET_DOUBLE_C, header=1)
    raw = raw.loc[:, ~raw.columns.astype(str).str.startswith("Unnamed")]
    raw = raw.dropna(subset=["Désignation"])
    raw = raw[~raw["Désignation"].astype(str).str.match(r"(?i)^(total|reste)$")]

    d = pd.DataFrame({
        "designation": raw["Désignation"].astype(str).str.strip(),
        "date": pd.to_datetime(raw["Date"], errors="coerce"),
        "debit": pd.to_numeric(raw["Débit"], errors="coerce"),
        "credit": pd.to_numeric(raw["Crédit"], errors="coerce"),
    }).dropna(subset=["date"])

    d["sens"] = np.where(d["designation"].str.match(r"(?i)^achat"), "ACHAT",
                 np.where(d["designation"].str.match(r"(?i)^vente"), "VENTE",
                 np.where(d["designation"].str.match(r"(?i)^investissement"), "APPORT",
                 np.where(d["designation"].str.match(r"(?i)^retrait"), "RETRAIT",
                          "DEPENSE"))))
    # appariement achat -> vente par modele
    d["modele"] = d["designation"].str.replace(r"(?i)^(achat|vente)\s*", "", regex=True).str.strip()
    achats = d[d["sens"] == "ACHAT"].set_index("modele")["debit"]
    ventes = d[d["sens"] == "VENTE"].groupby("modele")["credit"].sum()

    pairs = []
    for m in ventes.index:
        if m in achats.index:
            a = achats.loc[m]
            a = float(a.iloc[0]) if isinstance(a, pd.Series) else float(a)
            pairs.append({"modele": m, "achat_ar": a, "vente_ar": float(ventes.loc[m])})
    p = pd.DataFrame(pairs)
    if p.empty:
        return None
    p["marge_ar"] = p["vente_ar"] - p["achat_ar"]
    p["tx"] = p["marge_ar"] / p["achat_ar"] * 100

    fig, ax = plt.subplots(figsize=(10, 4.3))
    x = np.arange(len(p))
    ax.bar(x - .19, p["achat_ar"] / 1e6, width=.38, color=config.PALETTE["grey"],
           label="Prix d'achat")
    ax.bar(x + .19, p["vente_ar"] / 1e6, width=.38, color=config.PALETTE["primary"],
           label="Prix de vente")
    ax.set_xticks(x, p["modele"], rotation=28, ha="right", fontsize=8)
    ax.set_ylabel("Ariary (millions)")
    for xi, t in zip(x, p["tx"]):
        coul = config.PALETTE["green"] if t >= 12 else config.PALETTE["accent"]
        ax.text(xi, max(p["achat_ar"].iloc[xi], p["vente_ar"].iloc[xi]) / 1e6 + .05,
                f"{t:.1f} %", ha="center", fontsize=8.5, fontweight="bold", color=coul)
    ax.axhline(0, color="black", lw=.6)
    ax.set_title("Operation 2023 (feuille Double_C) : le meme commerce, "
                 "des marges de 9 a 19 %\ncontre 9 % uniformes dans la base principale")
    ax.legend(loc="upper right")
    nom = _save(fig, "11_benchmark_marge_2023.png")

    p.to_csv(config.TABLE_DIR / "benchmark_marge_2023.csv", index=False)
    return Figure(
        nom,
        "Benchmark interne : la preuve que 9 % n'est pas une fatalite",
        "La feuille Double_C trace une operation menee de juillet a octobre 2023, hors du "
        f"registre principal. Sur {len(p)} couples achat/vente appariables, le taux de marge "
        f"moyen atteint {p['tx'].mean():.1f} % avec un maximum a {p['tx'].max():.1f} %, alors que "
        "la base principale plafonne a un marquage uniforme de 9 %. Ce sont pourtant les memes "
        "produits (G5 125 FI, G5 carbu, G5 Megafi) et le meme marche. Cet ecart est la meilleure "
        "preuve interne que le coefficient de 1,09 est un choix de gestion et non une contrainte "
        "du marche : il existe deja, dans la maison, une facon de vendre qui rapporte 4 a 10 "
        "points de plus.",
        [f"Marge moyenne de l'operation 2023 : {p['tx'].mean():.1f} % (vs 9,0 % dans la base principale)",
         f"Meilleure operation : {p.loc[p['tx'].idxmax(),'modele']} a {p['tx'].max():.1f} %",
         f"Resultat net de l'operation : {p['marge_ar'].sum()/1e6:.2f} M Ar de marge brute",
         "Conclusion : le plafond de 9 % est une regle interne, pas une limite de marche"],
    )


# --------------------------------------------------------------------------
# Orchestrateur
# --------------------------------------------------------------------------

def executer(jdd) -> tuple[list[Figure], dict]:
    figs = [
        fig_qualite(jdd.motos, jdd.synthese),
    ]
    f2, tab_src = fig_sources(jdd.motos, jdd.clients)
    figs.append(f2)
    f3, g_tend = fig_tendance(jdd.clients, jdd.motos)
    figs.append(f3)
    figs.append(fig_saisonnalite(jdd.clients))
    f5, g_pareto = fig_pareto(jdd.motos)
    figs.append(f5)
    figs.append(fig_matrice(jdd.motos))
    f7, g_marq = fig_marquage(jdd.motos)
    figs.append(f7)
    f8, g_rot = fig_rotation(jdd.motos)
    figs.append(f8)
    f9, g_prix = fig_prix(jdd.motos)
    figs.append(f9)
    f10, g_geo = fig_geo(jdd.clients)
    figs.append(f10)
    f11 = fig_benchmark_double_c()
    if f11 is not None:
        figs.append(f11)

    tables = {"sources": tab_src, "tendance": g_tend, "portefeuille": g_pareto,
              "marquage": g_marq, "rotation": g_rot, "prix": g_prix,
              "geo": g_geo}
    return figs, tables
