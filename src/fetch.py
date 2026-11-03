#!/usr/bin/env python3
"""Fetch ROCOG Functional Designation + Land Use Context Overlay from
Olmsted County's public ArcGIS service. Writes GeoJSON to /home/claude/rfp_data/.
Source: https://public.gis.olmstedcounty.gov/arcgis/rest/services/Transportation_Data/MapServer
"""
import json, time, urllib.parse, subprocess, os

BASE = ("https://public.gis.olmstedcounty.gov/arcgis/rest/services/"
        "Transportation_Data/MapServer")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

FIELDS5 = ("OBJECTID,FDES_ROCOG,FCLAS_FED,RD_SYSTEM,RD_AUTH,CTU_NAME_L,CTU_NAME_R,"
           "ST_NAME,ST_TYPE,MPH_POSTED,ROUTE_NUM,EFF_STATUS,MAP_LABEL")


def q(layer, params):
    url = f"{BASE}/{layer}/query?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            out = subprocess.run(
                ["curl", "-sS", "-L", "--max-time", "180",
                 "-A", "gis-data-client/1.0", url],
                capture_output=True, check=True).stdout
            return json.loads(out.decode())
        except Exception as e:
            if attempt == 3:
                raise
            print(f"   retry {attempt+1} after {e}")
            time.sleep(3)


def page_layer(layer, fields, outfile, chunk=1000):
    feats, offset = [], 0
    while True:
        d = q(layer, {
            "where": "1=1", "outFields": fields, "returnGeometry": "true",
            "outSR": "4326", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": chunk,
        })
        batch = d.get("features", [])
        feats.extend(batch)
        print(f"   layer {layer}: +{len(batch)} (total {len(feats)})")
        if len(batch) < chunk:
            break
        offset += chunk
        time.sleep(0.3)
    fc = {"type": "FeatureCollection", "features": feats}
    path = os.path.join(OUT, outfile)
    with open(path, "w") as f:
        json.dump(fc, f)
    print(f"   wrote {path}  features={len(feats)}  bytes={os.path.getsize(path)}")
    return len(feats)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("Layer 5 — ROCOG Functional Designation")
    n5 = page_layer(5, FIELDS5, "rocog_funcdes.geojson")
    print("Layer 6 — ROCOG Land Use Context Overlay")
    n6 = page_layer(6, "*", "rocog_landuse.geojson")   # named fields return 0 here
    print("Layer 8 — County Minimum Corridor Needs (ROW preservation)")
    n8 = page_layer(8, "OBJECTID,FDES_ROCOG,SURF_TYPE,RD_SYSTEM,CTU_NAME_L,"
                       "ST_NAME,ROUTE_NUM,MAP_LABEL", "rocog_row_needs.geojson")
    print(f"DONE  centerlines={n5}  landuse={n6}  row_needs={n8}")
