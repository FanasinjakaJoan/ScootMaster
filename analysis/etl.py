"""ETL ScootMaster : extraction, nettoyage, normalisation, chargement.

Problemes de qualite traites (tous detectes par exploration du classeur) :

1. La feuille ``DB_1,0`` empile sous les 662 transactions reelles un bloc de
   SYNTHESE HEBDOMADAIRE (145 lignes) puis un bloc de TOTAL GENERAL.  Si on
   les lit comme des transactions, le chiffre d'affaires est gonfle d'environ
   un facteur 2.  Le bloc est isole par motif ``^(semaine|semiane)\\s*\\d+``
   dans la colonne ``Date depart``.
2. Les prix sont exprimes en Francs Malgaches dans ``DB_1,0`` et en Ariary
   dans ``DB_ClientSM`` (ratio median 4,92 verifie par jointure sur n° de
   serie).  Tout est ramene en Ariary.
3. Les noms de modeles sont libres : 45 variantes brutes (majuscules,
   espaces de fin, couleurs, cylindrees) -> taxonomie canonique.
4. Dates et montants stockes en types mixtes (datetime / str / float),
   montants clients sous forme ``"3 800 000AR"``.
5. Libelles d'etat avec espaces de fin (``"VENDU "`` vs ``"VENDU"``).
6. Doublons de n° de serie.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

# --------------------------------------------------------------------------
# Helpers de parsing tolerants
# --------------------------------------------------------------------------

def _to_number(value) -> float:
    """Convertit une cellule heterogene en float. Accepte '3 800 000AR'."""
    if _manquant(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    txt = str(value).replace("\u00a0", " ")
    # on coupe au premier 'A'/'a' de 'Ar'/'ar' pour ne pas lire 'Ar' comme du texte
    head = re.split(r"[A-Za-z]", txt)[0] if re.search(r"[A-Za-z]", txt) else txt
    digits = re.sub(r"[^\d,\.]", "", head)
    if not digits:
        return np.nan
    digits = digits.replace(",", "")
    try:
        return float(digits)
    except ValueError:
        return np.nan


def _to_date(value) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


def _manquant(value) -> bool:
    """Detecte None, NaN, NaT et pd.NA sans exploser sur les tableaux."""
    return value is None or (np.isscalar(value) and pd.isna(value))


def _clean_text(value) -> str | None:
    """Upper + espaces compactes ; renvoie None si vide."""
    if _manquant(value):
        return None
    txt = re.sub(r"\s+", " ", str(value)).strip()
    txt = txt.strip("'\"* ")
    return txt.upper() if txt else None


# --------------------------------------------------------------------------
# Taxonomie des modeles
# --------------------------------------------------------------------------

def normaliser_modele(raw) -> str:
    """Ramene les 45 variantes brutes a un modele canonique."""
    txt = _clean_text(raw)
    if not txt:
        return "NON RENSEIGNE"
    # couleurs / mentions decoratives a ignorer
    for bruit in (" NOIR", " GRIS", " BLANC", " ORANGE", " ROUGE", " BLEU",
                  "(OLD)", "EX 219", " OLD"):
        txt = txt.replace(bruit, "")
    txt = txt.strip()

    kymco = txt.startswith("KYMCO") or txt.startswith("KYCMO")
    yamaha = txt.startswith("YAMAHA")
    pgo = txt.startswith("PGO")

    if kymco or (not yamaha and not pgo):
        if "MEGAFI" in txt:
            return "KYMCO G5 MEGAFI"
        if "RACING KING" in txt:
            return "KYMCO RACING KING"
        if "RACING" in txt:
            return "KYMCO RACING"
        if "G5" in txt or "C2 TYPE" in txt:
            return "KYMCO G5"
        if "G6" in txt:
            return "KYMCO G6"
        if "GP" in txt:
            return "KYMCO GP"
        if "JR" in txt:
            return "KYMCO JR"
        if "MANY" in txt:
            return "KYMCO MANY"
        if yamaha:
            pass
        elif kymco:
            return "KYMCO AUTRE"
    if yamaha:
        if "CYGNUS" in txt:
            return "YAMAHA CYGNUS"
        if "JOG" in txt:
            return "YAMAHA JOG"
        if "RS ZERO" in txt or txt.endswith(" RSZ") or " RSZ" in txt or txt.endswith(" RS"):
            return "YAMAHA RS ZERO"
        if "ZR" in txt or "GTR" in txt or "AERO" in txt:
            return "YAMAHA ZR/GTR"
        if "CUXI" in txt:
            return "YAMAHA CUXI"
        if "BWS" in txt:
            return "YAMAHA BWS"
        if "GLIDE" in txt:
            return "YAMAHA GLIDE"
        return "YAMAHA AUTRE"
    if pgo or "TIGRA" in txt:
        return "PGO TIGRA"
    return "AUTRE"


def marque_de(modele: str) -> str:
    if modele.startswith("KYMCO"):
        return "KYMCO"
    if modele.startswith("YAMAHA"):
        return "YAMAHA"
    if modele.startswith("PGO"):
        return "PGO"
    return "AUTRE"


def gamme_de(modele: str) -> str:
    """Gamme commerciale utilisee pour les matrices portefeuille."""
    if "MEGAFI" in modele:
        return "G5 MEGAFI"
    if "RACING KING" in modele:
        return "RACING KING"
    if "RACING" in modele:
        return "RACING"
    if "G5" in modele:
        return "G5"
    if "G6" in modele:
        return "G6"
    if "GP" in modele:
        return "GP"
    if "JR" in modele:
        return "JR"
    if "CYGNUS" in modele:
        return "CYGNUS"
    if "JOG" in modele:
        return "JOG"
    return "AUTRES"


# --------------------------------------------------------------------------
# Extraction des deux bases principales
# --------------------------------------------------------------------------

def _lire_brut(feuille: str, header: int) -> pd.DataFrame:
    df = pd.read_excel(config.SOURCE_XLSX, sheet_name=feuille, header=header)
    return df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]


def extraire_motos() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Renvoie (transactions_motos, synthese_hebdo) nettes et en Ariary."""
    raw = _lire_brut(config.SHEET_MOTOS, config.HEADER_ROW_MOTOS)
    raw = raw.rename(columns={c: str(c).strip() for c in raw.columns})

    motif = r"(?i)^(semiane|semaine)\s*\d+"
    est_synthese = raw["Date départ"].astype(str).str.strip().str.match(motif)
    idx_debut = int(np.argmax(est_synthese.values)) if est_synthese.any() else config.SUMMARY_BLOCK_START

    tx = raw.iloc[:idx_debut].copy()
    synth = raw.iloc[idx_debut:].copy()

    # ---- transactions -----------------------------------------------------
    tx = pd.DataFrame({
        "ligne_source": tx.index + config.HEADER_ROW_MOTOS + 2,  # ligne Excel
        "ref_interne": tx["N°"].map(lambda v: _clean_text(v)),
        "modele_brut": tx["Moto"].map(_clean_text),
        "numero_serie": tx["Numero de serie"].map(_clean_text),
        "date_arrivee": tx["Date d'arrivée"].map(_to_date),
        "date_depart": tx["Date départ"].map(_to_date),
        "prix_achat_ar": tx["Prix d'achat"].map(_to_number) / config.FMG_PER_AR,
        "prix_vente_ar": tx["Prix de vente"].map(_to_number) / config.FMG_PER_AR,
        "benefice_brut_ar": tx["Benefice"].map(_to_number) / config.FMG_PER_AR,
        "etat_brut": tx["Etat"].map(_clean_text),
        "semaine_brut": tx["SEMAINE"].map(_clean_text),
    })

    # Nettoyage derive
    tx["modele"] = tx["modele_brut"].map(normaliser_modele)
    tx["marque"] = tx["modele"].map(marque_de)
    tx["gamme"] = tx["modele"].map(gamme_de)
    tx["etat"] = tx["etat_brut"].replace(
        {"MIODINA": "EN STOCK", "KOTLETTE": "EN STOCK", "": None,
         "<= B BRUT": None, "VENDUE": "VENDU"}
    )
    tx.loc[tx["etat"].isin(["EN STOCK", "RESERVATION", None]), "etat"] = \
        tx["etat"].fillna("EN STOCK")
    tx["vendu"] = (tx["etat"] == "VENDU").astype(int)

    tx["duree_stock_j"] = (tx["date_depart"] - tx["date_arrivee"]).dt.days
    tx.loc[tx["duree_stock_j"] < 0, "duree_stock_j"] = np.nan

    tx["marge_ar"] = tx["prix_vente_ar"] - tx["prix_achat_ar"]
    tx["taux_marge"] = np.where(tx["prix_achat_ar"] > 0,
                                tx["marge_ar"] / tx["prix_achat_ar"], np.nan)
    tx["annee"] = tx["date_arrivee"].dt.year
    tx["mois"] = tx["date_arrivee"].dt.to_period("M").astype(str)

    # Anomalies : prix unitaires incoherents (blocs cumules residuels)
    aberrant = (tx[["prix_achat_ar", "prix_vente_ar"]] > config.PRIX_UNIT_MAX_AR).any(axis=1)
    tx["prix_aberrant"] = aberrant.astype(int)
    tx["valide"] = (~aberrant & tx["date_arrivee"].notna()).astype(int)

    # Doublons de n° de serie -> on conserve la premiere occurrence
    serie = tx["numero_serie"]
    tx["doublon_serie"] = serie.notna() & serie.duplicated(keep="first")

    # ---- synthese hebdomadaire -------------------------------------------
    synth = pd.DataFrame({
        "semaine_label": synth["Date départ"].map(_clean_text),
        "nb_motos": synth["Date d'arrivée"].map(_to_number),
        "total_achat_ar": synth["Prix d'achat"].map(_to_number) / config.FMG_PER_AR,
        "total_vente_ar": synth["Prix de vente"].map(_to_number) / config.FMG_PER_AR,
    }).dropna(subset=["semaine_label"])
    synth["semaine"] = pd.to_numeric(
        synth["semaine_label"].str.extract(r"(\d+)")[0], errors="coerce")
    synth = synth.dropna(subset=["semaine"]).sort_values("semaine")
    synth["marge_ar"] = synth["total_vente_ar"] - synth["total_achat_ar"]

    return tx, synth


def extraire_clients() -> pd.DataFrame:
    raw = _lire_brut(config.SHEET_CLIENTS, config.HEADER_ROW_CLIENTS)
    raw = raw.rename(columns={c: str(c).strip() for c in raw.columns})
    # compte les montants saisis sous forme de texte ("3 800 000AR")
    n_montants_texte = int(raw["Montant en Ar"].map(
        lambda v: isinstance(v, str) and bool(re.search(r"\d", v))).sum())

    df = pd.DataFrame({
        "ligne_source": raw.index + config.HEADER_ROW_CLIENTS + 2,
        "n_moto": raw["N° Moto"].map(lambda v: _clean_text(v)),
        "n_moteur": raw["N° Moteur"].map(_clean_text),
        "n_facture": raw["N° Facture"].map(lambda v: _clean_text(v)),
        "n_bl": raw["N°B.L"].map(lambda v: _clean_text(v)),
        "modele_brut": raw["Marque moto"].map(_clean_text),
        "nom": raw["Nom"].map(_clean_text),
        "prenom": raw["Prenom"].map(lambda v: re.sub(r"\s+", " ", str(v)).strip()
                                    if pd.notna(v) else None),
        "cin": raw["N° CIN"].map(lambda v: _clean_text(v)),
        "adresse": raw["Adresse"].map(lambda v: re.sub(r"\s+", " ", str(v)).strip()
                                      if pd.notna(v) else None),
        "telephone": raw["Telephone"].map(lambda v: _clean_text(v)),
        "canal_brut": raw["Type"].map(_clean_text),
        "date_achat": raw["Date de l'achat"].map(_to_date),
        "montant_ar": raw["Montant en Ar"].map(_to_number),
    })

    df["modele"] = df["modele_brut"].map(normaliser_modele)
    df["marque"] = df["modele"].map(marque_de)
    df["gamme"] = df["modele"].map(gamme_de)

    # ---- canal de distribution -------------------------------------------
    canal = df["canal_brut"].fillna("")
    df["canal"] = np.where(canal.str.contains("(?i)ext|vendu par"), "AGENT / APPORTEUR",
                    np.where(canal.str.contains("(?i)pisera"), "AGENT / APPORTEUR",
                    np.where(canal.str.contains("(?i)police"), "INSTITUTION",
                    np.where(canal.str.contains("(?i)appel"), "PROSPECT A RELANCER",
                             "DIRECT (MAGASIN)"))))
    df["apporteur"] = canal.map(_apporteur)
    # l'apporteur n'a de sens que pour les ventes en canal indirect
    df.loc[df["canal"] != "AGENT / APPORTEUR", "apporteur"] = None

    # ---- geographie (quartiers d'Antananarivo) ---------------------------
    df["quartier"] = df["adresse"].map(_extraire_quartier)
    df["zone"] = [_zone_geographique(a, q) for a, q in zip(df["adresse"], df["quartier"])]

    df["annee"] = df["date_achat"].dt.year
    df["mois"] = df["date_achat"].dt.to_period("M").astype(str)
    df["valide"] = (df["date_achat"].notna() & df["montant_ar"].notna()).astype(int)

    serie = df["n_moteur"]
    df["doublon_moteur"] = serie.notna() & serie.duplicated(keep="first")
    df.attrs["n_montants_texte"] = n_montants_texte
    return df


def _apporteur(txt):
    """Extrait le nom de l'apporteur d'affaires depuis la colonne 'Type'."""
    if _manquant(txt):
        return None
    s = str(txt)
    if not s.strip() or s.strip() == "<NA>":
        return None
    s = re.sub(r"(?i)acheteur\s+ext[ée]rieur", "", s)
    s = re.sub(r"(?i)(vendu\s+par|\bpar\b)", "", s)
    s = re.sub(r"^[:\-\s]+", "", s).strip(" :\u2013-")
    s = re.sub(r"\s+", " ", s).upper()
    return s or None


# --------------------------------------------------------------------------
# Geographie : parseur structurel d'adresses
# --------------------------------------------------------------------------
# Format dominant observe : "Lot <code-ilot> <numero> [Bis|Ter] <QUARTIER> [- Ville]".
# Le quartier est donc le dernier toponyme significatif. On retire d'abord les
# suffixes de ville, on coupe sur le separateur '-', puis on prend le dernier
# token alphabetique. Les villes de province sont reconnues explicitement.

_MARQUEURS_VILLE = re.compile(
    r"(?i)\b(tana|antananarivo|renivohitra|\d{1,2}(er|e)?\s*arrondissement)\b")

_VILLES_PROVINCE = [
    "MORONDAVA", "AMBOSITRA", "AMBATONDRAZAKA", "FENERIVE", "TOAMASINA",
    "TAMATAVE", "MAHAJANGA", "ANTSIRABE", "FIANARANTSOA", "TOLIARA",
    "TULEAR", "DIEGO", "ANTSIRANA", "NOSY", "MANAKARA", "MORAMANGA",
    "MANANJARY", "SAMBAVA", "ANTALAHA", "BRICKAVILLE", "AMBANJA",
    "MAINTIRANO", "AMBALAVAO", "MIDONGY", "MANAMPILOTSY", "MAROVOAY",
    "AMBATOBOENY", "MAEVATANANA", "MANDRITSARA", "MIARINARIVO",
    "AMBATOLAMPY", "ANTANIFOTSY", "AMBODIRAFIA", "MANANARA", "MAROANTSETRA",
    "SOANIERANA", "VOHIBINANY", "ANALAMBE", "AMBODITAVIA", "VATOMANDRY",
    "AMBALAMANASOA", "TOLAGNARO", "FORT DAUPHIN", "AMBILABE", "BETALA",
]

_MOT_VALIDE = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]{2,}$")

# Tokens qui ne sont jamais un quartier (points cardinaux, codes d'ilot).
_TOKENS_BRUIT = {
    "EST", "OUEST", "SUD", "NORD", "LOT", "ANDREFANA", "AVARATRA", "ATSIMO",
    "ATSINANANA", "BIS", "TER", "FKT", "CITE", "BAT", "TANA", "ANTANANARIVO",
}
_CODE_ILOT = re.compile(
    r"(?i)^(lo?t|l[oe]?t?|[ivx]{1,5}[a-z]?|[a-z]{1,4}\d{1,3}|\d+[a-z]?|bis|ter|"
    r"fkt|cite|bat|bloc|immeuble|residence|annexe|sud|nord|est|ouest|andrefana|"
    r"avaratra|atsimo|atsinana)$")


def _extraire_quartier(adresse):
    """Renvoie le toponyme (quartier ou ville) d'une adresse malgache."""
    if _manquant(adresse) or not str(adresse).strip():
        return None
    txt = re.sub(r"\s+", " ", str(adresse)).strip()
    txt = _MARQUEURS_VILLE.sub(" ", txt)
    # on ne garde que la partie avant un eventuel separateur de ville
    txt = re.split(r"\s[\-/]\s", txt)[0]
    tokens = [t for t in re.split(r"[\s,]+", txt) if t]
    # on retire les codes d'ilot et numeros en tete
    while tokens and (_CODE_ILOT.match(tokens[0]) or tokens[0].isdigit()):
        tokens.pop(0)
    # le quartier = dernier token significatif (hors points cardinaux et codes)
    for t in reversed(tokens):
        if _MOT_VALIDE.match(t) and not t.isdigit() and t.upper() not in _TOKENS_BRUIT:
            return t.upper()
    return None


def _zone_geographique(adresse, quartier):
    """Classe grossierement : province vs Antananarivo/alentours."""
    if _manquant(adresse) and _manquant(quartier):
        return "NON RENSEIGNE"
    txt = f"{adresse or ''} {quartier or ''}".upper()
    for v in _VILLES_PROVINCE:
        if re.search(rf"\b{re.escape(v)}\b", txt):
            return "PROVINCE"
    return "ANTANANARIVO & ALENTOURS"


# --------------------------------------------------------------------------
# Enrichissements croises
# --------------------------------------------------------------------------

def joindre_motos_clients(tx: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    """Jointure sur le n° de serie moteur pour recuperer client + quartier."""
    cle = "numero_serie"
    gauche = tx[tx["valide"] == 1].copy()
    droit = cl[["n_moteur", "nom", "prenom", "quartier", "telephone",
                "canal", "apporteur", "montant_ar", "date_achat"]] \
        .rename(columns={"n_moteur": cle, "montant_ar": "montant_client_ar",
                         "date_achat": "date_achat_client"}) \
        .dropna(subset=[cle]).drop_duplicates(subset=[cle], keep="first")
    out = gauche.merge(droit, on=cle, how="left")
    out["client_identifie"] = out["nom"].notna().astype(int)
    return out


# --------------------------------------------------------------------------
# Chargement complet + journal de qualite
# --------------------------------------------------------------------------

@dataclass
class JeuDeDonnees:
    motos: pd.DataFrame
    clients: pd.DataFrame
    synthese: pd.DataFrame
    fusion: pd.DataFrame
    qualite: pd.DataFrame = field(default_factory=pd.DataFrame)


def construire_journal_qualite(tx: pd.DataFrame, cl: pd.DataFrame,
                               synth: pd.DataFrame,
                               raw_motos_n: int) -> pd.DataFrame:
    lignes = [
        ("DB_1,0", "Lignes brutes lues", raw_motos_n, "",
         "En-tete en ligne 9"),
        ("DB_1,0", "Lignes de synthese hebdo isolees", len(synth), "exclues des transactions",
         "Motif 'Semaine N' en colonne Date depart"),
        ("DB_1,0", "Transactions conservees", len(tx), "",
         "Bloc lignes 10 a 671"),
        ("DB_1,0", "Transactions a prix aberrant", int(tx["prix_aberrant"].sum()),
         "flaggees, exclues des agregats",
         f"Prix unitaire > {config.PRIX_UNIT_MAX_AR:,} Ar"),
        ("DB_1,0", "Transactions exploitables", int(tx["valide"].sum()), "",
         "Date d'arrivee valide et prix coherent"),
        ("DB_1,0", "Doublons de n° de serie", int(tx["doublon_serie"].sum()),
         "conserves, signales", "Doublons detectes sur numero_serie"),
        ("DB_1,0", "Date d'arrivee manquante", int(tx["date_arrivee"].isna().sum()),
         "", "Cellule vide ou texte"),
        ("DB_1,0", "Date de depart manquante", int(tx["date_depart"].isna().sum()),
         "", "Moto non encore vendue ('none')"),
        ("DB_1,0", "Duree de stock negative corrigee",
         int(((tx["date_depart"] - tx["date_arrivee"]).dt.days < 0).sum()),
         "mise a NaN", "Saisie inversee arrivee/depart"),
        ("DB_1,0", "Modeles bruts normalises", int(tx["modele_brut"].nunique()),
         f"-> {tx['modele'].nunique()} modeles canoniques",
         "Taxonomie reglee par mots-cles"),
        ("DB_ClientSM", "Lignes lues", len(cl), "", "En-tete en ligne 5"),
        ("DB_ClientSM", "Lignes exploitables", int(cl["valide"].sum()), "",
         "Date + montant presents"),
        ("DB_ClientSM", "Montants saisis sous forme de texte",
         int(cl.attrs.get("n_montants_texte", 0)),
         "convertis en numerique", "Format '3 800 000AR' parse"),
        ("DB_ClientSM", "Doublons de n° de moteur", int(cl["doublon_moteur"].sum()),
         "conserves, signales", "Doublons sur n_moteur"),
        ("DB_ClientSM", "Clients sans telephone",
         int(cl["telephone"].isna().sum()), "action : collecte",
         "Bloque la relance commerciale"),
        ("DB_ClientSM", "Clients sans adresse exploitable",
         int(cl["quartier"].isna().sum()), "action : geocodage",
         "Quartier non reconnu"),
        ("DB_ClientSM", "Ventes via agent/apporteur",
         int((cl["canal"] == "AGENT / APPORTEUR").sum()), "",
         "Colonne Type renseignee"),
    ]
    return pd.DataFrame(lignes, columns=["source", "indicateur", "valeur",
                                         "traitement", "commentaire"])


def charger() -> JeuDeDonnees:
    raw_motos = _lire_brut(config.SHEET_MOTOS, config.HEADER_ROW_MOTOS)
    tx, synth = extraire_motos()
    cl = extraire_clients()
    fusion = joindre_motos_clients(tx, cl)
    qualite = construire_journal_qualite(tx, cl, synth, len(raw_motos))
    return JeuDeDonnees(motos=tx, clients=cl, synthese=synth, fusion=fusion,
                        qualite=qualite)


def persister(jdd: JeuDeDonnees) -> None:
    jdd.motos.to_csv(config.DATA_DIR / "transactions_motos.csv", index=False)
    jdd.clients.to_csv(config.DATA_DIR / "clients.csv", index=False)
    jdd.synthese.to_csv(config.DATA_DIR / "synthese_hebdo.csv", index=False)
    jdd.fusion.to_csv(config.DATA_DIR / "transactions_enrichies.csv", index=False)
    jdd.qualite.to_csv(config.TABLE_DIR / "journal_qualite.csv", index=False)


if __name__ == "__main__":
    jdd = charger()
    persister(jdd)
    print(jdd.qualite.to_string(index=False))
    print("\nTransactions exploitables :", int(jdd.motos["valide"].sum()))
    print("Clients exploitables      :", int(jdd.clients["valide"].sum()))
