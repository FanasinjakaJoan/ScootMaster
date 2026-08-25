# ScootMaster

Négoce de motos (KYMCO / YAMAHA / PGO) à Antananarivo. Ce dépôt contient le fichier de
données brut `Scoot_Master (1).xlsx` et un pipeline complet de science des données qui en
extrait tendances, segments de clients, choix de produits et prévisions, avec des
représentations graphiques interprétées et un plan d'action chiffré.

## Contenu

- `Scoot_Master (1).xlsx` — source : base motos (achats/ventes), base clients, pièces,
  prospects, flux de caisse.
- `analysis/` — pipeline Python (pandas, matplotlib, scikit-learn, statsmodels) :
  - `etl.py` — extraction, nettoyage, normalisation (devises FMG→Ariary, modèles, adresses,
    séparation du bloc de synthèse hebdomadaire) ;
  - `eda.py` — qualité, tendances, saisonnalité, portefeuille, marges, rotation, géographie,
    benchmark ;
  - `segmentation.py` — paliers de valeur clients + modèle de propension au réachat ;
  - `forecast.py` — prévisions 12 mois (Holt-Winters / tendance / naïf, backtest), mix produit
    futur, scénarios de marge ;
  - `report.py` — génération du rapport (Markdown + HTML) et du classeur décisionnel ;
  - `dashboard.py` — tableau de bord interactif Plotly (survol, zoom, filtres) ;
  - `run_all.py` — orchestration.
- `output/` — livrables générés (ignorés par Git, reproductibles) :
  - `rapport_data_scootmaster.html` / `.md` — rapport complet illustré ;
  - `figures/` — 17 graphiques ;
  - `tables/` — tableaux de synthèse ;
  - `ScootMaster_analyse_decisionnelle.xlsx` — classeur décisionnel ;
  - `data/` — jeux nettoyés.

## Reproduire l'analyse

```bash
pip install pandas numpy openpyxl matplotlib seaborn scikit-learn scipy statsmodels xlsxwriter
python3 -m analysis.run_all
```

Le rapport principal s'ouvre avec `output/rapport_data_scootmaster.html`.

## Principaux constats (voir rapport pour le détail)

- Le CA s'est stabilisé sur un palier bas (~950-980 M Ar/an) depuis 2021, sans croissance.
- Concentration forte : KYMCO RACING + G5 ≈ 74 % des volumes.
- Politique de prix = marquage fixe ~9 % ; l'opération 2023 prouve que 13 % est atteignable.
- Taux de réachat ~7 % : la valeur se joue au premier achat et chez un petit noyau de fidèles.
- Levier n°1 : relever le coefficient de marquage (+17 M Ar/an à 13 %, volumes constants).
