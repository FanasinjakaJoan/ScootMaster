"""Configuration centrale du pipeline d'analyse ScootMaster.

Toutes les constantes metier, les chemins et la palette graphique sont
centralises ici pour que les modules d'analyse restent declaratifs.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_XLSX = REPO_ROOT / "Scoot_Master (1).xlsx"

OUTPUT_DIR = REPO_ROOT / "output"
DATA_DIR = OUTPUT_DIR / "data"
FIG_DIR = OUTPUT_DIR / "figures"
TABLE_DIR = OUTPUT_DIR / "tables"

for _d in (OUTPUT_DIR, DATA_DIR, FIG_DIR, TABLE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Feuille source / geometrie du classeur
# --------------------------------------------------------------------------
SHEET_MOTOS = "DB_1,0"          # base transactions motos (achat + vente)
SHEET_CLIENTS = "DB_ClientSM"   # base clients (vente, identite, montant en Ar)
SHEET_PIECES_STOCK = "DB_Pièces_SM"
SHEET_PIECES_VENTES = "Ventes pieces"
SHEET_PRIX_ACHAT = "prix pieces refa hanao achat"
SHEET_PROSPECTS = "Liste prospects"
SHEET_DOUBLE_C = "Double_C"

HEADER_ROW_MOTOS = 8    # en-tete en ligne 9 (0-based -> 8)
HEADER_ROW_CLIENTS = 4  # en-tete en ligne 5 (0-based -> 4)

# Indice (0-based, apres lecture avec header) de la premiere ligne du
# bloc de SYNTHESE HEBDOMADAIRE empile sous les transactions dans DB_1,0.
# Verifie empiriquement : la colonne 'Date depart' y contient "Semaine N".
SUMMARY_BLOCK_START = 662

# --------------------------------------------------------------------------
# Regles metier
# --------------------------------------------------------------------------
# 1 Ariary = 5 Francs Malgaches (FMG). Ratio verifie par jointure sur le
# numero de serie entre DB_1,0 (FMG) et DB_ClientSM (Ariary) : mediane 4,92,
# ecart interquartile [4,67 ; 5,00] sur 785 motos appariees.
FMG_PER_AR = 5.0

# Devise de restitution choisie pour tout le rapport.
CURRENCY = "Ar"

# Seuil au-dela duquel un prix unitaire moto est traite comme valeur aberrante.
# Justification : le prix unitaire reel culmine a ~40 M FMG (8 M Ar) sur la
# periode ; au-dela on trouve uniquement des blocs de totaux cumules.
PRIX_UNIT_MAX_AR = 12_000_000

# Fenetre de prevision
HORIZON_MOIS = 12

# --------------------------------------------------------------------------
# Graphisme
# --------------------------------------------------------------------------
FIG_DPI = 135
PALETTE = {
    "primary": "#1f4e79",
    "accent": "#e8833a",
    "green": "#2e8b57",
    "red": "#c0392b",
    "grey": "#7f8c8d",
    "violet": "#7d3c98",
    "teal": "#148f77",
    "light": "#d6e4f0",
}
SEQ = ["#1f4e79", "#e8833a", "#2e8b57", "#7d3c98", "#c0392b", "#148f77",
       "#b7950b", "#5d6d7e", "#af601a", "#1a5276"]
