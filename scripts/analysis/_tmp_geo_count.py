from pathlib import Path

import json, re, collections
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

GEO_RE = re.compile(r"-g(\d+)-")

with open(ROOT / "data/processed/london_reviews.json", encoding="utf-8") as f:
    data = json.load(f)

geo_counts = collections.Counter()
for rec in data:
    m = GEO_RE.search(rec.get("hotel_url", ""))
    if m:
        geo_counts[m.group(1)] += 1

gs = pd.read_csv(ROOT / "reports/eda/all/geo_stats.csv", dtype={"geo_id": str})
name_map = dict(zip(gs["geo_id"], gs["location_name"]))

print(f"고유 geo_id 수: {len(geo_counts)}\n")
print(f"{'geo_id':<12} {'리뷰 수':>10}  지역명")
print("-" * 65)
for geo_id, cnt in geo_counts.most_common():
    name = name_map.get(geo_id, "(unknown)")
    print(f"{geo_id:<12} {cnt:>10,}  {name}")
