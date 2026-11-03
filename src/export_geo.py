#!/usr/bin/env python3
"""Export simplified geometry for the top-ranked corridors so docs/ can draw a map.
Geometry is simplified for display only; all analysis runs on full geometry."""
import json, os, sys
import geopandas as gpd
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)          # python3 -I drops the script dir from sys.path
from evaluate import load, corridorize

ROOT = os.path.dirname(HERE)
TOP_N = 150
TOLERANCE_M = 12          # display simplification, UTM metres


def main():
    cand = pd.read_csv(f"{ROOT}/out/corridor_candidates.csv")
    top = cand.head(TOP_N)
    keep = dict(zip(top["corridor"], top["rank"]))
    scores = dict(zip(top["corridor"], top["score"]))

    roads = corridorize(load())
    sel = roads[roads["corridor_id"].isin(keep) & ~roads["is_ramp"]].copy()

    diss = sel.dissolve(by="corridor_id", aggfunc={"len_mi": "sum"}).reset_index()
    diss["geometry"] = diss.geometry.simplify(TOLERANCE_M, preserve_topology=True)
    diss = diss.to_crs(4326)
    diss["rank"] = diss["corridor_id"].map(keep)
    diss["score"] = diss["corridor_id"].map(scores)
    diss["miles"] = diss["len_mi"].round(2)
    diss = diss[["corridor_id", "rank", "score", "miles", "geometry"]].sort_values("rank")

    path = f"{ROOT}/docs/corridors.geojson"
    diss.to_file(path, driver="GeoJSON")
    size = os.path.getsize(path)
    print(f"wrote {path}  corridors={len(diss)}  bytes={size:,}")
    if size > 3_000_000:
        print("WARNING: geojson is large for a static page; raise TOLERANCE_M")


if __name__ == "__main__":
    main()
