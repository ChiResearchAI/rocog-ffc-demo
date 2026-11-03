# ROCOG Future Functional Classification — Corridor Evaluation Engine

A working demonstration that runs a **scored, reproducible pass over the entire ROCOG roadway
network** and produces a ranked list of corridors warranting review in a functional classification
update — each with the criteria and values behind it.

Built by **ChiResearch Technologies, LLC** on Olmsted County's published GIS.

**[View the live demo →](https://chiresearchai.github.io/rocog-ffc-demo/)**

The page pairs each corridor's **current federal classification with its intended future ROCOG
designation**, shows what that designation already commits the County to on the ground, and lets a
reviewer **move the criterion weights and watch the ranking recompute** against all 1,835 corridors.

---

## What this is, and what it is not

**It is** a working example: real data, real geometry, a documented scoring method, and output a
planner could act on. 12,403 centerline segments, 2,188.8 centerline miles, 1,835 corridors scored.

**It is not** deployed production software, and it is not a ROCOG product. The criteria and weights
are ChiResearch's own proposal for discussion — **they are not adopted ROCOG policy**. Nothing here
recommends a classification change. It ranks where a planner should look, and shows why.

The whole point is the second half of that sentence. When a jurisdiction asks why its corridor was
or was not flagged, the answer is a criterion and a value, not a recollection.

---

## Three things the page does that the tools in this space do not

**1. Current and future classification on one screen.** The federal functional class governs funding
and design today; the ROCOG designation records intended future function. They are maintained as
separate maps. Here every corridor carries both, side by side, with its Maintain/Improve subclass —
so "what is it now, and what is it supposed to become" is one glance rather than two documents.

**2. What a reclassification actually changes.** Selecting a corridor shows the minimum access
spacing that governs it under Olmsted County Access Management Ordinance Ch. 1300, Table 2 — urban
and rural local street spacing, and driveway spacing at three speed bands. Reclassify the corridor
and every one of those figures moves. The right-of-way standard for the designation is shown beside
it. A classification is a land commitment, and the page says so in feet.

**3. Weights you can move, and a robustness test.** The ranking is a weighted sum, so the weights are
the argument. They are sliders, with preset scenarios, and the ranking recomputes in the browser.
Then the page samples **400 random weightings across the whole simplex** and reports, per corridor,
how often it holds the top 50 regardless of what anyone believes.

That last number is the one worth bringing to a technical committee. **Seven corridors hold the top
50 under 90% or more of sampled weightings; twenty hold it under 75%; none hold it under all of
them**, because uniform sampling includes weightings nobody would defend. Reported as a percentage
rather than a pass/fail badge, it turns a weighting dispute into agreement on the robust subset
before anyone argues about the rest.

---

## The problem it addresses

ROCOG's Future Functional Classification System records the *intended future function* of a corridor,
and member jurisdictions rely on that record when they review a plat, permit an access, or program a
project. Revisiting it means deciding, corridor by corridor, where the existing designation no longer
reflects intended future function.

Done by hand across 2,188 miles, that is a long sequence of individual judgements with no common
basis. Done this way, the judgement still belongs to the planner — but it starts from a ranked
candidate list instead of a blank map.

---

## How a corridor is scored

A **corridor** is a named route within one jurisdiction: the unit a local agency actually discusses.
Corridors under 0.10 miles are dropped as artifacts. Interchange ramps are excluded (see below).

| Criterion | Weight | What it measures |
|---|---|---|
| `c1_hierarchy_divergence` | 0.25 | Mileage-weighted gap between the ROCOG designation and the federal functional class carried on the same segments |
| `c2_context_fit` | 0.15 | Whether the designation sits outside the usual band for its ROCOG land use context |
| `c3_route_continuity` | 0.20 | How many different designations one named route carries within a jurisdiction |
| `c4_authority_fit` | 0.12 | Whether the designation is unusual for the road system holding it (Interstate, US, State, CSAH, CR, MSAS, City, Township, Private) |
| `c5_future_exposure` | 0.10 | Future (2050) corridors held by township or county authorities — least likely to hold access management controls |
| `c6_row_preservation_gap` | 0.18 | Corridors expected to carry an arterial or collector function with **no recorded minimum corridor need** — no right-of-way reserved against the standard their designation implies |

Each criterion returns 0–1; the composite is a weighted sum. **The weights are arguable and are meant
to be argued about** — they live in one dictionary at the top of `src/evaluate.py`.

---

## Why a classification is a land commitment, not a label

Olmsted County publishes a layer most functional classification work never touches:
**County Minimum Corridor Needs** (layer 8), the right-of-way preserved from centerline, keyed
directly to functional designation.

| Designation | Right-of-way preserved from centerline |
|---|---|
| Strategic Arterial | **125 ft** |
| Major Arterial | 65 ft |
| Secondary Arterial, Primary Collector, Local Collector | 60 ft |
| Other County Road, unpaved | 50 ft |

Widths are read from the layer's own symbology. The layer covers **532.5 miles** — effectively the
whole county road system.

Reclassify a corridor and you change how much land has to be protected along it. Which makes the
next two numbers the point of this whole exercise:

- **Not one segment designated 2050 Arterial carries a recorded minimum corridor need.** The layer
  holds no right-of-way standard for that designation at all.
- **14.1 of the 16.0 future-designated miles sit on township roads**, outside the county system the
  corridor-needs layer covers.

So the corridors ROCOG has identified as its future arterials are the ones with no right-of-way
reserved, held by the road authorities least likely to hold an access management ordinance. A single
platted driveway can foreclose one. That is what `c6_row_preservation_gap` measures, and it is why
four of the top thirteen ranked corridors are future corridors in Kalmar and New Haven Townships.

---

## What the run produces

```
corridors evaluated                1,835
corridors scoring above 0.30          27
corridors with a right-of-way gap      6
corridors containing future segments   9
centerline miles                 2,188.8
future-designated miles             16.0
county corridor-need miles         532.5
ramp miles excluded                 42.8
top-50 stable under both mappings  39/50
```

Outputs land in `out/`:

- `corridor_candidates.csv` — every corridor, every criterion value, composite score, and a
  plain-language reason string
- `sensitivity_rank_comparison.csv` — rank under both hierarchy correspondences
- `summary.json` — run metadata and weights

---

## The honest part: what this analysis cannot tell you

These are reported because they bear on how far the output should be trusted, and two of them are
design findings in their own right.

1. **The hierarchy correspondence is ours, not ROCOG's.** ROCOG's designation has nine tiers; the
   federal system has six. Comparing them requires mapping one onto the other, and **ROCOG has not
   published that correspondence.** The engine ships with two defensible mappings and reports both.
   Headline *mileage* figures move a lot between them — the share of network two or more levels apart
   is 19.2% under one and 8.4% under the other. **The ranking is considerably more stable: 38 of the
   top 50 corridors are the same either way.** Fixing the correspondence is a Task 1 decision, and it
   should be fixed before any count built on it is quoted.

2. **The land use overlay does not cover the network.** 124 segments totalling 41.2 centerline miles
   fall outside every polygon in the ROCOG Land Use Context Overlay, so `c2_context_fit` is silent on
   them. If land use is to be a central driver of the new system, completing the overlay is a
   prerequisite, not a detail.

3. **The planning area is larger than the data.** ROCOG's planning area includes the full city limits
   of Pine Island and Chatfield, *including the portions outside Olmsted County*. Both layers here are
   county-published and do not reach them.

4. **Ramps are geometry, not corridors.** Interchange ramps inherit the mainline ROCOG designation
   while carrying a Local federal class, so they read as enormous divergences. 42.8 miles of ramp are
   excluded from corridor scoring. (A narrower measure — segments designated NHS-Interstate *and*
   federally classed Local — comes to 25.1 miles and is all ramps on Hwy 52, I-90 and Simpson Road.
   The two figures count different things and are not interchangeable.)

5. **Right-of-way coverage is matched by name, not by geometry.** A corridor counts as having a
   recorded corridor need when layer 8 holds a segment with the same street name in the same
   jurisdiction. That is the unit layer 8 is drawn at, but it will miss a partial-length record and
   it cannot tell a recorded need from an *adequate* one. The criterion flags absence of a record,
   not insufficiency of a width.

6. **Two different "future corridor" mileages appear, and they are not interchangeable.** 16.0 miles
   carry a 2050 designation. The nine *corridors* containing those segments run 35.9 miles end to
   end, because a corridor is scored whole. Figures here say which one they mean.

7. **Centerline miles, not lane miles or travel.** No traffic volume, crash, freight or transit data
   is used. This measures how the network is *labelled*, not how it *performs*. A real evaluation adds
   those inputs; this demonstrates the method and the machinery.

8. **One figure deliberately excluded.** Every one of the 12,403 segments carries a non-null federal
   functional class, so "federal class coverage" computes to 100% in every tier. That is a property of
   how the field is populated, not a finding, and nothing here is inferred from it.

9. **A snapshot.** Data retrieved 2 November 2026. The county service is maintained continuously.

---

## Reproducing it

```bash
pip install geopandas shapely pyproj pandas

python src/fetch.py        # refresh the snapshot from Olmsted County's public ArcGIS
python src/evaluate.py     # score every corridor -> out/ and docs/candidates.json
python src/export_geo.py   # simplified geometry for the top 60 -> docs/corridors.geojson
```

A cached snapshot is committed in `data/`, so `evaluate.py` runs without network access.

---

## Data source

Olmsted County public ArcGIS, `Transportation_Data` MapServer:

- **Layer 5 — ROCOG Functional Designation**, 12,403 polyline segments, field `FDES_ROCOG`
- **Layer 6 — ROCOG Land Use Context Overlay**, 21 polygons, 9 context classes
- **Layer 8 — County Minimum Corridor Needs**, 1,588 segments, 532.5 miles of right-of-way
  preservation keyed to functional designation

Both projected to NAD83 / UTM 15N (EPSG:26915) for true length. Each segment takes the land use
context of the polygon containing its midpoint; a segment crossing a context boundary is assigned
wholly to one context, which is adequate at tier totals and should be split for corridor-level work.

Published by Olmsted County. This repository is **not** a ROCOG or Olmsted County publication.

---

## Licence

Code: MIT. The underlying GIS data is Olmsted County's and is subject to the County's own terms.

**ChiResearch Technologies, LLC** · Hyattsville, Maryland · wilfred@chiresearchai.com
