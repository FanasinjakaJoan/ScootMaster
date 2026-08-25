"""Orchestration du pipeline : ETL -> EDA -> segmentation -> prevision -> rapport.

Usage :  python3 -m analysis.run_all
"""
from __future__ import annotations

from . import etl, eda, segmentation, forecast, report


def main() -> None:
    print("== ETL ==")
    jdd = etl.charger()
    etl.persister(jdd)

    print("== EDA ==")
    figs_eda, _tables = eda.executer(jdd)

    print("== SEGMENTATION ==")
    figs_seg = segmentation.executer(jdd)

    print("== PREVISIONS ==")
    figs_fc = forecast.executer(jdd)

    figs = figs_eda + figs_seg + figs_fc

    print("== RAPPORT ==")
    out = report.construire(jdd, figs)
    xlsx = report.classeur(jdd)

    print("\nFIGURES :", len(figs))
    print("RAPPORT MD   :", out["md"])
    print("RAPPORT HTML :", out["html"])
    print("CLASSEUR     :", xlsx)


if __name__ == "__main__":
    main()
