#!/usr/bin/env python3
"""
ROCOG Future Functional Classification — corridor evaluation engine.

Runs a scored, reproducible pass over the whole network and emits a ranked list of
corridors that warrant review in a functional classification update. The point of the
engine is that every candidate carries a criterion and a value, not a recollection:
if a reviewer disagrees, they disagree with a weight or a threshold they can see.

Criteria are deliberately shallow and legible. Each is computed from a published
field, each scores 0-1, and the composite is a weighted sum. Weights live in
WEIGHTS and are meant to be argued about.

Data: Olmsted County public ArcGIS, Transportation_Data MapServer, layers 5 and 6.
Run `src/fetch.py` to refresh the cached snapshot in data/.
"""
from __future__ import annotations
import json
import os
import geopandas as gpd
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, OUT, DOCS = f"{ROOT}/data", f"{ROOT}/out", f"{ROOT}/docs"
UTM15N, M_PER_MI = 26915, 1609.344

# ---------------------------------------------------------------- classifications
FDES = {10: "NHS-Interstate", 15: "NHS-TH (M)", 16: "NHS-TH (I)",
        20: "Strategic Arterial (M)", 21: "Strategic Arterial (I)",
        30: "Major Arterial (M)", 31: "Major Arterial (I)",
        40: "Secondary Arterial (M)", 41: "Secondary Arterial (I)",
        50: "Primary Collector (M)", 51: "Primary Collector (I)",
        60: "Local Collector (E)", 61: "Local Collector (F)",
        70: "Commercial - Industrial Access", 90: "Other Local Street",
        91: "Other Local Road", 92: "Private Street",
        100: "2050 Arterial", 101: "2050 Collector"}

# Rank on a common 1-6 scale so ROCOG's nine tiers and the six federal classes can be
# compared like for like. THIS CORRESPONDENCE IS AN ANALYTICAL CHOICE, NOT ROCOG'S.
# Task 1 of the solicitation is where it should actually be fixed. See README.
FDES_RANK = {10: 1, 15: 1, 16: 1, 20: 2, 21: 2, 30: 2, 31: 2, 40: 3, 41: 3,
             50: 4, 51: 4, 60: 5, 61: 5, 70: 6, 90: 6, 91: 6, 92: 6}
# Alternative correspondence, used for the sensitivity run.
FDES_RANK_ALT = {10: 1, 15: 1, 16: 1, 20: 2, 21: 2, 30: 3, 31: 3, 40: 4, 41: 4,
                 50: 4, 51: 4, 60: 5, 61: 5, 70: 6, 90: 6, 91: 6, 92: 6}
FED = {1: "Interstate", 2: "Prin art - other fwy/expwy", 3: "Prin art - other",
       4: "Minor arterial", 5: "Major collector", 6: "Minor collector", 7: "Local"}
FED_RANK = {1: 1, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}

FUTURE = {100, 101}

# Olmsted County Access Management Ordinance, Chapter 1300, Table 2 — minimum spacing
# of access connections, keyed to ROCOG road classification. Verified against the
# ordinance PDF (508C, 2 May 2018, p.17). This is what a reclassification actually
# changes on the ground: urban local street / rural local street / driveway at <35,
# 35-45 and >45 mph, in feet.
ORD1300_TABLE2 = {
    "Strategic Arterial":        (1320, 2640, 660, 880, 1000),
    "Regional Major Arterial":   (880, 2640, 480, 660, 800),
    "Urban Major Arterial":      (660, None, 275, 375, 500),
    "Regional Secondary Arterial": (660, 1320, 250, 480, 660),
    "Urban Secondary Arterial":  (480, None, 175, 275, 330),
    "Regional Primary Collector": (480, 660, 150, 330, 480),
    "Urban Primary Collector":   (330, None, 125, 200, 275),
    "Local Collector":           (330, 660, 60, None, None),
}

# ROCOG designation -> the ordinance row it is governed by. Arterial rows split
# regional/urban, which the designation code does not carry, so the rural/urban land use
# context decides. Collector rows likewise.
ORD_ROW_BASE = {20: "Strategic Arterial", 21: "Strategic Arterial",
                30: "Major Arterial", 31: "Major Arterial",
                40: "Secondary Arterial", 41: "Secondary Arterial",
                50: "Primary Collector", 51: "Primary Collector",
                60: "Local Collector", 61: "Local Collector"}
URBAN_CONTEXTS = {"Rochester CBD", "Rochester Core", "Rochester Urban",
                  "Rochester Urban Edge", "Small City Core", "Small City Urban"}


def ordinance_row(fd, context):
    """Which Chapter 1300 Table 2 row governs access on this corridor."""
    base = ORD_ROW_BASE.get(fd)
    if base is None:
        return None
    if base == "Strategic Arterial" or base == "Local Collector":
        return base
    prefix = "Urban" if context in URBAN_CONTEXTS else "Regional"
    return f"{prefix} {base}"

# Land use context -> the band of hierarchy ranks that is unremarkable there.
# Outside the band is not an error; it is a reason to look.
CONTEXT_BAND = {
    "Rochester CBD":        (2, 6), "Rochester Core":       (1, 6),
    "Rochester Urban":      (1, 6), "Rochester Urban Edge": (1, 6),
    "Suburban":             (1, 6), "Small City Core":      (3, 6),
    "Small City Urban":     (3, 6), "Small City Urban Edge": (2, 6),
    "Rural":                (1, 6),
}
# Road system -> the band of hierarchy ranks that system normally carries.
SYSTEM_BAND = {
    "I": (1, 1), "US": (1, 2), "STATE": (1, 3), "CSAH": (2, 4), "CR": (3, 5),
    "MSAS": (2, 5), "CITY": (4, 6), "TWP": (5, 6), "PVT": (6, 6),
}

WEIGHTS = {
    "c1_hierarchy_divergence": 0.25,
    "c2_context_fit":          0.15,
    "c3_route_continuity":     0.20,
    "c4_authority_fit":        0.12,
    "c5_future_exposure":      0.10,
    "c6_row_preservation_gap": 0.18,
}

# Olmsted County's minimum corridor need (right-of-way preserved from centerline) keyed
# to functional designation, read off layer 8's own symbology labels. This is the
# concrete consequence of a classification: a Strategic Arterial reserves 125 feet.
ROW_STANDARD_FT = {20: 125, 21: 125, 30: 65, 31: 65, 40: 60, 41: 60,
                   50: 60, 51: 60, 60: 60, 101: 60, 90: 60}


def row_requirement(fd, surface):
    if fd in (90, 91):
        return 60 if surface == "Paved" else 50
    return ROW_STANDARD_FT.get(fd)


def band_penalty(rank, band):
    """0 inside the band, scaled by distance outside it, capped at 1."""
    if band is None or pd.isna(rank):
        return 0.0
    lo, hi = band
    if lo <= rank <= hi:
        return 0.0
    d = (lo - rank) if rank < lo else (rank - hi)
    return min(abs(d) / 3.0, 1.0)


def load_row_needs():
    """County Minimum Corridor Needs, layer 8. Covers the county road system only."""
    import os
    path = f"{DATA}/rocog_row_needs.geojson"
    if not os.path.exists(path):
        return None
    row = gpd.read_file(path).to_crs(UTM15N)
    row["fd"] = pd.to_numeric(row["FDES_ROCOG"], errors="coerce")
    row["len_mi"] = row.geometry.length / M_PER_MI
    row["req_ft"] = [row_requirement(f, s)
                     for f, s in zip(row["fd"], row.get("SURF_TYPE", pd.Series(dtype=object)))]
    return row


def load():
    roads = gpd.read_file(f"{DATA}/rocog_funcdes.geojson").to_crs(UTM15N)
    lu = gpd.read_file(f"{DATA}/rocog_landuse.geojson").to_crs(UTM15N)
    roads["len_mi"] = roads.geometry.length / M_PER_MI
    roads["fd"] = pd.to_numeric(roads["FDES_ROCOG"], errors="coerce")
    roads["ff"] = pd.to_numeric(roads["FCLAS_FED"], errors="coerce")
    roads["fd_label"] = roads["fd"].map(FDES)
    roads["ff_label"] = roads["ff"].map(FED)

    mids = roads.geometry.interpolate(0.5, normalized=True)
    mg = gpd.GeoDataFrame({"i": roads.index},
                          geometry=gpd.GeoSeries(mids, crs=roads.crs))
    j = gpd.sjoin(mg, lu[["Name", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    roads["context"] = j["Name"].values

    # Ramps carry the mainline designation but a Local federal class. They are
    # geometry, not corridors, and counting them as corridors inflates everything.
    label = roads["MAP_LABEL"].fillna("").astype(str).str.lower()
    roads["is_ramp"] = label.str.startswith("ramp")
    return roads


def corridorize(roads):
    """Group segments into corridors. A corridor is a named route within one
    jurisdiction — the unit a local agency actually discusses."""
    name = (roads["ROUTE_NUM"].fillna("").astype(str).str.strip()
            .where(lambda s: s != "", roads["ST_NAME"].fillna("").astype(str).str.strip()))
    roads["corridor_name"] = name.replace("", "(unnamed)")
    roads["jurisdiction"] = roads["CTU_NAME_L"].fillna("(unknown)")
    roads["corridor_id"] = roads["corridor_name"] + " · " + roads["jurisdiction"]
    return roads


def tag_row_coverage(roads):
    """Flag segments that fall on a corridor carrying a recorded minimum corridor need.
    Matched on road name within jurisdiction, which is the unit layer 8 is drawn at."""
    row = load_row_needs()
    if row is None:
        roads["row_recorded"] = False
        return roads
    key = (row["ST_NAME"].fillna("").astype(str).str.strip().str.upper() + "|" +
           row["CTU_NAME_L"].fillna("").astype(str).str.strip().str.upper())
    have = set(k for k in key if k.strip("|"))
    rk = (roads["ST_NAME"].fillna("").astype(str).str.strip().str.upper() + "|" +
          roads["CTU_NAME_L"].fillna("").astype(str).str.strip().str.upper())
    roads["row_recorded"] = rk.isin(have)
    return roads


def evaluate(roads, rank_map=FDES_RANK):
    r = roads[~roads["is_ramp"]].copy()
    r["fd_rank"] = r["fd"].map(rank_map)
    r["ff_rank"] = r["ff"].map(FED_RANK)

    rows = []
    for cid, g in r.groupby("corridor_id"):
        miles = float(g["len_mi"].sum())
        if miles < 0.10:                      # below this, a "corridor" is an artifact
            continue
        fds = g["fd"].dropna()
        if fds.empty:
            continue
        dom = fds.mode().iloc[0]
        dom_rank = rank_map.get(dom)
        is_future = bool(set(fds.unique()) & FUTURE)

        # C1 — hierarchy divergence against the federal class, mileage-weighted
        comp = g.dropna(subset=["fd_rank", "ff_rank"])
        if len(comp):
            d = (comp["ff_rank"] - comp["fd_rank"]).abs()
            c1 = float((d * comp["len_mi"]).sum() / comp["len_mi"].sum() / 3.0)
            c1 = min(c1, 1.0)
            signed = float(((comp["ff_rank"] - comp["fd_rank"]) * comp["len_mi"]).sum()
                           / comp["len_mi"].sum())
        else:
            c1, signed = 0.0, 0.0

        # C2 — fit between designation and land use context
        c2vals = [band_penalty(rank_map.get(fd), CONTEXT_BAND.get(ctx))
                  for fd, ctx in zip(g["fd"], g["context"])]
        c2 = float(pd.Series(c2vals, dtype=float).fillna(0).mean()) if c2vals else 0.0

        # C3 — continuity: a corridor carrying several designations is a break
        n_designations = int(fds.nunique())
        c3 = min((n_designations - 1) / 3.0, 1.0)

        # C4 — designation against the road authority that holds it
        c4vals = [band_penalty(rank_map.get(fd), SYSTEM_BAND.get(sys))
                  for fd, sys in zip(g["fd"], g["RD_SYSTEM"])]
        c4 = float(pd.Series(c4vals, dtype=float).fillna(0).mean()) if c4vals else 0.0

        # C5 — a future corridor held by an authority unlikely to have access management
        sys_set = set(g["RD_SYSTEM"].dropna().unique())
        c5 = 1.0 if (is_future and sys_set & {"TWP", "CR"}) else (0.5 if is_future else 0.0)

        # C6 — right-of-way preservation gap. A classification is a land commitment:
        # the County reserves up to 125 ft from centerline for a Strategic Arterial.
        # A corridor expected to carry that function with no recorded corridor need is
        # one platted driveway away from being foreclosed.
        recorded = bool(g["row_recorded"].any())
        on_county = bool(sys_set & {"CSAH", "CR"})
        if is_future and not recorded:
            c6 = 1.0
        elif (dom_rank is not None and dom_rank <= 5) and on_county and not recorded:
            c6 = 0.6
        else:
            c6 = 0.0

        score = (WEIGHTS["c1_hierarchy_divergence"] * c1
                 + WEIGHTS["c2_context_fit"] * c2
                 + WEIGHTS["c3_route_continuity"] * c3
                 + WEIGHTS["c4_authority_fit"] * c4
                 + WEIGHTS["c5_future_exposure"] * c5
                 + WEIGHTS["c6_row_preservation_gap"] * c6)

        ctx_mode = g["context"].dropna()
        ctx_dom = ctx_mode.mode().iloc[0] if len(ctx_mode) else None
        ffs = g["ff"].dropna()
        cur_fed = FED.get(ffs.mode().iloc[0]) if len(ffs) else None
        dom_label = FDES.get(dom, "")
        mi = ("Improve" if dom_label.endswith("(I)")
              else "Maintain" if dom_label.endswith("(M)") else None)
        ord_row = ordinance_row(dom, ctx_dom)
        rows.append({
            "corridor": cid,
            "corridor_name": g["corridor_name"].iloc[0],
            "jurisdiction": g["jurisdiction"].iloc[0],
            "miles": round(miles, 2),
            "segments": int(len(g)),
            "designation": FDES.get(dom, "(none)"),
            "road_systems": ", ".join(sorted(x for x in sys_set if x)),
            "context": ctx_dom or "(outside overlay)",
            "current_federal_class": cur_fed,
            "subclass": mi,
            "ordinance_row": ord_row,
            "access_spacing": ORD1300_TABLE2.get(ord_row),
            "n_designations": n_designations,
            "fed_minus_rocog": round(signed, 2),
            "c1_hierarchy_divergence": round(c1, 3),
            "c2_context_fit": round(c2, 3),
            "c3_route_continuity": round(c3, 3),
            "c4_authority_fit": round(c4, 3),
            "c5_future_exposure": round(c5, 3),
            "c6_row_preservation_gap": round(c6, 3),
            "row_recorded": recorded,
            "row_required_ft": ROW_STANDARD_FT.get(dom),
            "score": round(score, 4),
            "future_corridor": is_future,
        })

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df


def reason(row):
    bits = []
    if row["c1_hierarchy_divergence"] >= 0.33:
        d = row["fed_minus_rocog"]
        bits.append(f"ROCOG ranks it {'higher' if d > 0 else 'lower'} than the federal "
                    f"class by {abs(d):.1f} levels on average")
    if row["c3_route_continuity"] > 0:
        bits.append(f"carries {row['n_designations']} different designations along one route")
    if row["c2_context_fit"] >= 0.33:
        bits.append(f"designation sits outside the usual band for {row['context']} context")
    if row["c4_authority_fit"] >= 0.33:
        bits.append(f"designation is unusual for the {row['road_systems']} system")
    if row["c5_future_exposure"] >= 1.0:
        bits.append("future corridor held by a township or county road authority")
    if row.get("c6_row_preservation_gap", 0) >= 0.6:
        req = row.get("row_required_ft")
        has_std = req is not None and not pd.isna(req)
        bits.append("no recorded minimum corridor need" +
                    (f" against a {int(req)} ft standard" if has_std else
                     " and no right-of-way standard exists for this designation"))
    return "; ".join(bits) if bits else "no single criterion dominates"


def main():
    os.makedirs(OUT, exist_ok=True)
    roads = tag_row_coverage(corridorize(load()))
    total_mi = float(roads["len_mi"].sum())
    ramp_mi = float(roads.loc[roads["is_ramp"], "len_mi"].sum())

    df = evaluate(roads)
    df["why"] = df.apply(reason, axis=1)
    df.to_csv(f"{OUT}/corridor_candidates.csv", index=False)

    alt = evaluate(roads, FDES_RANK_ALT)[["corridor", "rank", "score"]].rename(
        columns={"rank": "rank_alt", "score": "score_alt"})
    merged = df[["corridor", "rank", "score"]].merge(alt, on="corridor", how="inner")
    top50 = set(merged.nsmallest(50, "rank")["corridor"])
    top50_alt = set(merged.nsmallest(50, "rank_alt")["corridor"])
    overlap = len(top50 & top50_alt)
    merged.to_csv(f"{OUT}/sensitivity_rank_comparison.csv", index=False)
    # carry the alternative-mapping rank onto every row so the page can show movement
    df = df.merge(alt, on="corridor", how="left")
    df["rank_delta"] = (df["rank_alt"] - df["rank"]).fillna(0).astype(int)

    summary = {
        "generated_from": ("Olmsted County public ArcGIS, Transportation_Data "
                           "MapServer, layers 5 (ROCOG Functional Designation), "
                           "6 (Land Use Context Overlay) and 8 (County Minimum "
                           "Corridor Needs)"),
        "segments": int(len(roads)),
        "total_centerline_miles": round(total_mi, 1),
        "ramp_miles_excluded": round(ramp_mi, 1),
        "corridors_evaluated": int(len(df)),
        "corridors_scoring_above_0_30": int((df["score"] > 0.30).sum()),
        "future_corridors": int(df["future_corridor"].sum()),
        "future_corridor_miles_whole": round(
            float(df.loc[df["future_corridor"], "miles"].sum()), 1),
        "future_designated_miles": round(float(
            roads.loc[roads["fd"].isin(FUTURE) & ~roads["is_ramp"], "len_mi"].sum()), 1),
        "row_needs_miles": round(float(
            (load_row_needs()["len_mi"].sum()) if load_row_needs() is not None else 0), 1),
        "row_gap_corridors": int((df["c6_row_preservation_gap"] > 0).sum()),
        "weights": WEIGHTS,
        "sensitivity_top50_overlap": overlap,
        "sensitivity_note": (f"{overlap} of the top 50 corridors are the same under both "
                             "hierarchy correspondences; the ranking is more stable than "
                             "the headline mileage figures it is built from."),
    }
    with open(f"{OUT}/summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    cols = ["rank", "corridor", "corridor_name", "jurisdiction", "miles", "designation",
            "road_systems", "context", "n_designations", "fed_minus_rocog",
            "c1_hierarchy_divergence", "c2_context_fit", "c3_route_continuity",
            "c4_authority_fit", "c5_future_exposure", "c6_row_preservation_gap",
            "row_recorded", "row_required_ft", "current_federal_class", "subclass",
            "ordinance_row", "access_spacing", "score", "future_corridor",
            "rank_alt", "rank_delta", "why"]
    # NaN is not valid JSON and JSON.parse rejects it outright, so the page would load
    # nothing at all. Convert every missing value to null before writing, and refuse to
    # write a file that still contains one.
    payload = {"summary": summary, "weights": WEIGHTS,
               "rows": df[cols].astype(object).where(pd.notna(df[cols]), None)
                               .to_dict(orient="records")}
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text, "non-JSON literal in payload"
    with open(f"{DOCS}/candidates.json", "w") as f:
        f.write(text)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(json.dumps(summary, indent=2))
    print("\nTOP 15 CANDIDATE CORRIDORS\n")
    print(df.head(15)[["rank", "corridor_name", "jurisdiction", "miles",
                       "designation", "score", "why"]].to_string(index=False))


if __name__ == "__main__":
    main()
