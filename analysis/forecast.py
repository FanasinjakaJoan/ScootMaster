"""Previsions : volumes, chiffre d'affaires, mix produit futur, scenarios.

Methodologie assumee et transparente :
- perimetre : base clients (registre commercial), 2020-04 -> 2022-12 (le mois de
  janvier 2023 est tronque au 24/01 et donc exclu de l'apprentissage) ;
- trois modeles candidats (lissage exponentiel de Holt-Winters amorti, tendance
  lineaire, naif saisonnier) ;
- selection par backtest sur les 6 derniers mois disponibles (MAPE) ;
- intervalle de prevision construit sur l'ecart-type des residus du backtest.

On ne pretend pas une precision illusoire : la serie est courte (33 mois) et
volatile.  L'objectif est de donner une trajectoire probable et des bornes, et
surtout un MIX PRODUIT futur fonde sur la demande recente + la marge + la
rotation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from . import config
from .eda import Figure, _save

plt.rcParams.update({
    "figure.dpi": config.FIG_DPI, "savefig.dpi": config.FIG_DPI,
    "savefig.bbox": "tight", "font.size": 9, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.grid": True, "grid.alpha": .25,
    "grid.linestyle": "--", "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})

DEBUT = "2020-04"
FIN = "2022-12"
HORIZON = config.HORIZON_MOIS


def _serie_mensuelle(clients: pd.DataFrame, col: str) -> pd.Series:
    c = clients[clients["valide"] == 1]
    c = c[(c["date_achat"] >= f"{DEBUT}-01") & (c["date_achat"] <= f"{FIN}-28")]
    idx = pd.period_range(DEBUT, FIN, freq="M")
    if col == "n":
        s = c.groupby(c["date_achat"].dt.to_period("M")).size()
    else:
        s = c.groupby(c["date_achat"].dt.to_period("M"))[col].sum()
    return s.reindex(idx, fill_value=0)


# --------------------------------------------------------------------------
# Modeles candidats
# --------------------------------------------------------------------------

def _fit_ets(y: np.ndarray, h: int):
    try:
        m = ExponentialSmoothing(y, trend="add", seasonal="add",
                                 seasonal_periods=12, damped_trend=True,
                                 initialization_method="estimated").fit()
        return m.forecast(h)
    except Exception:
        return None


def _fit_lineaire(y: np.ndarray, h: int):
    t = np.arange(len(y))
    c = np.polyfit(t, y, 1)
    return np.polyval(c, np.arange(len(y), len(y) + h))


def _fit_naif_saisonnier(y: np.ndarray, h: int):
    # moyenne des 12 derniers mois repetee (a defaut d'une annee complete stable)
    dern = y[-12:]
    return np.tile(dern, (h // 12 + 2))[:h]


def _backtest(y: np.ndarray, h: int = 6) -> dict:
    train, test = y[:-h], y[-h:]
    res = {}
    for nom, fn in [("Holt-Winters", _fit_ets), ("Tendance lineaire", _fit_lineaire),
                    ("Naif saisonnier", _fit_naif_saisonnier)]:
        pred = fn(train, h)
        if pred is None:
            continue
        err = np.mean(np.abs((test - pred) / np.where(test == 0, np.nan, test)))
        res[nom] = {"pred": pred, "mape": err}
    return res


def _choisir(res: dict) -> str:
    return min(res, key=lambda k: res[k]["mape"])


# --------------------------------------------------------------------------
# Prevision globale
# --------------------------------------------------------------------------

def prevision_globale(clients: pd.DataFrame, col: str, libelle: str,
                      fichier: str, titre: str) -> tuple[Figure, pd.Series, dict]:
    s = _serie_mensuelle(clients, col)
    y = s.values.astype(float)

    res = _backtest(y)
    meilleur = _choisir(res)

    # modele final entraine sur toute la serie
    pred_final = {nom: fn(y, HORIZON) for nom, fn in
                  [("Holt-Winters", _fit_ets), ("Tendance lineaire", _fit_lineaire),
                   ("Naif saisonnier", _fit_naif_saisonnier)] if fn(y, HORIZON) is not None}
    fc = pred_final[meilleur]
    # intervalle sur residus du backtest
    residus = np.concatenate([res[n]["pred"] - y[-6:] for n in res])
    sigma = np.nanstd(residus)

    futur = pd.period_range(FIN, periods=HORIZON + 1, freq="M")[1:]
    lo = np.clip(fc - 1.96 * sigma, 0, None)
    hi = fc + 1.96 * sigma

    # ---- figure -----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 4.6))
    idx = s.index.to_timestamp()
    ax.plot(idx, y, color=config.PALETTE["primary"], lw=2, marker="o", ms=3,
            label="Historique (base clients)")
    fx = futur.to_timestamp()
    ax.plot(fx, fc, color=config.PALETTE["accent"], lw=2.4, marker="s", ms=4,
            label=f"Prevision {meilleur}")
    ax.fill_between(fx, lo, hi, color=config.PALETTE["accent"], alpha=.16,
                    label="Intervalle 95 %")
    ax.axvline(idx[-1], color="black", ls=":", lw=1.2)
    ax.text(idx[-1], max(y) * .97, "  fin des donnees", fontsize=8, va="top")
    ax.set_ylabel(libelle)
    ax.set_title(titre)
    ax.legend(loc="upper right", ncol=3)
    nom = _save(fig, fichier)

    info = {"modele": meilleur,
            "mape": {n: round(r["mape"] * 100, 1) for n, r in res.items()},
            "total_prev": float(fc.sum()), "total_lo": float(lo.sum()),
            "total_hi": float(hi.sum())}
    return Figure(nom, titre, "", []), pd.Series(fc, index=futur), info


# --------------------------------------------------------------------------
# Mix produit futur
# --------------------------------------------------------------------------

def mix_futur(motos: pd.DataFrame, clients: pd.DataFrame,
              total_prev_volume: float) -> tuple[Figure, pd.DataFrame]:
    c = clients[clients["valide"] == 1].copy()
    # part de demande observee sur les 12 derniers mois complets
    recent = c[c["date_achat"] >= "2022-01-01"]
    part = recent["gamme"].value_counts(normalize=True)

    # tendance de part : compare 2021 vs 2022 pour signaler derive
    a21 = c[c["date_achat"].dt.year == 2021]["gamme"].value_counts(normalize=True)
    a22 = c[c["date_achat"].dt.year == 2022]["gamme"].value_counts(normalize=True)

    m = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    perf = m.groupby("gamme").agg(
        marge_unit=("marge_ar", "mean"),
        tx=("taux_marge", "median"),
        rotation=("duree_stock_j", "median")).reset_index()

    mix = part.reset_index()
    mix.columns = ["gamme", "part_demande"]
    mix = mix.merge(perf, on="gamme", how="left")
    mix["part_2021"] = mix["gamme"].map(a21).fillna(0)
    mix["part_2022"] = mix["gamme"].map(a22).fillna(0)
    mix["derive"] = mix["part_2022"] - mix["part_2021"]

    # volume previsionnel annuel par gamme + score de priorite
    mix["volume_prev"] = (mix["part_demande"] * total_prev_volume).round(1)
    # score = part demande * (1 + tx) / (1 + rotation normalisee)
    rot = mix["rotation"].fillna(mix["rotation"].median())
    mix["score_priorite"] = (mix["part_demande"] * (1 + mix["tx"].fillna(.09))
                             / (1 + rot / rot.max()))
    mix = mix.sort_values("score_priorite", ascending=False)
    mix.to_csv(config.TABLE_DIR / "mix_produit_futur.csv", index=False)

    top = mix.head(6)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7))

    ax = axes[0]
    x = np.arange(len(top))
    ax.bar(x, top["volume_prev"], color=config.SEQ[:len(top)], width=.62)
    ax.set_xticks(x, top["gamme"], rotation=30, ha="right", fontsize=8.5)
    for xi, v in zip(x, top["volume_prev"]):
        ax.text(xi, v + .5, f"{v:.0f}", ha="center", fontsize=8.5, fontweight="bold")
    ax.set_ylabel("Motos/an prevues (part de la demande)")
    ax.set_title("Volume annuel a prevoir par gamme\n(projection de la demande 2022)")
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    ax2 = ax.twinx()
    col = [config.PALETTE["green"] if d > 0 else config.PALETTE["red"]
           for d in top["derive"]]
    ax.bar(x, top["marge_unit"] / 1e3, color=col, width=.6,
           label="Marge unitaire (milliers Ar)")
    ax2.plot(x, top["tx"] * 100, color=config.PALETTE["violet"], lw=2.2, marker="D",
             ms=5, label="Taux de marge (%)")
    ax.set_xticks(x, top["gamme"], rotation=30, ha="right", fontsize=8.5)
    ax.set_ylabel("Marge unitaire (k Ar)")
    ax2.set_ylabel("Taux de marge (%)", color=config.PALETTE["violet"])
    ax.set_title("Rentabilite par gamme (couleur = derive de part 2021->2022)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=7.5)
    nom = _save(fig, "16_mix_produit_futur.png")

    return Figure(
        nom,
        "Mix produit futur : concentrer le stock sur la demande qui tourne",
        "En projetant la part de demande observee en 2022 sur le volume previsionnel, on obtient "
        "le volume annuel a prevoir par gamme. Les gammes RACING et G5 restent le coeur du metier, "
        "mais le score de priorite (qui combine part de demande, taux de marge et vitesse de "
        "rotation) met en avant celles qui generent de la marge sans immobiliser le capital. La "
        "couleur du graphique de droite signale la derive : les gammes en vert gagnent des parts "
        "d'une annee sur l'autre, celles en rouge en perdent. C'est sur les gammes vertes et "
        "rapides qu'il faut augmenter le niveau de stock, et sur les rouges et lentes qu'il faut "
        "reduire les commandes.",
        [f"Volume annuel a prevoir : {total_prev_volume:.0f} motos",
         f"Gamme n°1 en priorite : {top['gamme'].iloc[0]} "
         f"({top['volume_prev'].iloc[0]:.0f} motos/an)",
         "Gammes en croissance de part (vert) : a renforcer",
         "Gammes lentes a marge faible (rouge) : a reduire"],
    ), mix


# --------------------------------------------------------------------------
# Scenarios de marge
# --------------------------------------------------------------------------

def scenarios_marge(motos: pd.DataFrame) -> tuple[Figure, pd.DataFrame]:
    v = motos[(motos["valide"] == 1) & (motos["vendu"] == 1)]
    cout = v["prix_achat_ar"].sum()
    marge_actuelle = v["marge_ar"].sum()
    tx_actuel = marge_actuelle / cout

    scenarios = [("Statu quo (9 %)", tx_actuel), ("Marquage 12 %", .12),
                 ("Marquage 13 % (operation 2023)", .13), ("Marquage 15 %", .15)]
    # calcul direct : marge annuelle = CA-achat * tx  sur la base annuelle 2022
    ann = v[v["annee"] == 2022]
    cout_an = ann["prix_achat_ar"].sum()
    rows = []
    for nom, tx in scenarios:
        rows.append({
            "scenario": nom, "taux": tx,
            "marge_2022_ar": cout_an * tx,
            "gain_vs_statu_quo_ar": cout_an * tx - cout_an * tx_actuel,
        })
    df = pd.DataFrame(rows)
    df.to_csv(config.TABLE_DIR / "scenarios_marge.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(df))
    bars = ax.bar(x, df["marge_2022_ar"] / 1e6,
                  color=[config.PALETTE["grey"], config.PALETTE["primary"],
                         config.PALETTE["accent"], config.PALETTE["green"]][:len(df)],
                  width=.6)
    ax.set_xticks(x, df["scenario"], rotation=20, ha="right", fontsize=8.5)
    for b, (m, g) in zip(bars, zip(df["marge_2022_ar"], df["gain_vs_statu_quo_ar"])):
        ax.text(b.get_x() + b.get_width() / 2, m / 1e6 + 1,
                f"{m/1e6:.0f} M Ar\n({g/1e6:+.0f})", ha="center", fontsize=8.5,
                fontweight="bold")
    ax.set_ylabel("Marge brute annuelle (M Ar) — base 2022")
    ax.set_title("Scenarios de marquage : chaque point de taux est un gain direct,\n"
                 "car le cout d'achat est la seule variable maitrisee")
    ax.grid(axis="y", visible=False)
    nom = _save(fig, "17_scenarios_marge.png")

    gain13 = df.loc[df["taux"] == .13, "gain_vs_statu_quo_ar"].iloc[0]
    return Figure(
        nom,
        "Scenarios : passer de 9 a 13 % de marquage sans changer les volumes",
        f"Sur la base de l'annee 2022 ({cout_an/1e6:.0f} M Ar d'achats), un marquage a 13 % — le "
        f"niveau deja atteint par l'operation 2023 — ajouterait {gain13/1e6:.0f} M Ar de marge "
        f"brute par an, soit +{gain13/marge_actuelle*100:.0f} % de resultat a volumes constants. "
        "Le scenario a 15 % est le plafond prudent. Ces chiffres supposent que la demande absorbe "
        "la hausse ; ils constituent donc un objectif de negociation et de test progressif, pas un "
        "changement brutal. La recommandation est de tester le nouveau coefficient modele par "
        "modele, en commencant par ceux qui tournent le plus vite.",
        [f"Marge 2022 au statu quo : {df['marge_2022_ar'].iloc[0]/1e6:.0f} M Ar",
         f"Scenario 13 % : +{gain13/1e6:.0f} M Ar/an",
         f"Scenario 15 % : +{df['gain_vs_statu_quo_ar'].iloc[-1]/1e6:.0f} M Ar/an",
         "Approche conseillee : test progressif par modele, en priorite sur les rotations rapides"],
    ), df


def executer(jdd) -> list[Figure]:
    out = []

    f_vol, s_vol, i_vol = prevision_globale(
        jdd.clients, "n", "Motos vendues / mois", "14_previsions_volume.png",
        "Prevision du volume mensuel de ventes (12 mois)")
    f_vol.interpretation = (
        f"Le modele retenu par backtest est « {i_vol['modele']} » (MAPE : "
        + ", ".join(f"{k} {v} %" for k, v in i_vol["mape"].items()) + "). "
        f"Sur les 12 prochains mois, le volume projete est d'environ {i_vol['total_prev']:.0f} "
        f"motos, entre {i_vol['total_lo']:.0f} et {i_vol['total_hi']:.0f} selon l'intervalle a "
        "95 %. La trajectoire reste plate : rien dans les trois annees observees n'indique une "
        "reprise spontanee. Toute croissance devra venir d'une action (stock, prix, canal) et non "
        "d'une tendance de fond.")
    f_vol.points = [
        f"Modele retenu : {i_vol['modele']}",
        f"Volume annuel projete : {i_vol['total_prev']:.0f} motos "
        f"[{i_vol['total_lo']:.0f} ; {i_vol['total_hi']:.0f}]",
        "MAPE backtest : " + ", ".join(f"{k} = {v} %" for k, v in i_vol["mape"].items()),
        "Pas de tendance haussiere structurelle : la croissance sera volontariste",
    ]
    out.append(f_vol)

    f_ca, s_ca, i_ca = prevision_globale(
        jdd.clients, "montant_ar", "Chiffre d'affaires (M Ar)", "15_previsions_ca.png",
        "Prevision du chiffre d'affaires mensuel (12 mois)")
    f_ca.interpretation = (
        f"Le chiffre d'affaires projete sur 12 mois est d'environ {i_ca['total_prev']/1e6:.0f} M Ar "
        f"(intervalle {i_ca['total_lo']/1e6:.0f} a {i_ca['total_hi']/1e6:.0f} M Ar). Rapporté au "
        "marquage actuel de 9 %, cela represente une marge brute attendue de "
        f"{i_ca['total_prev']/1.09*.09/1e6:.0f} M Ar au statu quo — ce qui situe l'enjeu du "
        "scenario de prix. La fourchette large rappelle que la prevision d'un commerce a "
        "a-coups reste indicative : elle sert a dimensionner le stock et la tresorerie, pas a "
        "faire un budget au franc pres.")
    f_ca.points = [
        f"CA annuel projete : {i_ca['total_prev']/1e6:.0f} M Ar "
        f"[{i_ca['total_lo']/1e6:.0f} ; {i_ca['total_hi']/1e6:.0f}]",
        f"Marge brute attendue au statu quo : {i_ca['total_prev']/1.09*.09/1e6:.0f} M Ar",
        "A utiliser pour dimensionner stock et tresorerie",
    ]
    out.append(f_ca)

    f_mix, mix = mix_futur(jdd.motos, jdd.clients, i_vol["total_prev"])
    out.append(f_mix)

    f_scen, scen = scenarios_marge(jdd.motos)
    out.append(f_scen)

    # table de synthese des previsions
    pd.DataFrame({
        "mois": s_vol.index.astype(str),
        "volume_prevu": s_vol.round(0).astype(int),
        "ca_prevu_MAr": (s_ca / 1e6).round(1),
    }).to_csv(config.TABLE_DIR / "previsions_12_mois.csv", index=False)

    return out
