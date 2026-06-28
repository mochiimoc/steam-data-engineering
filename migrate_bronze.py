"""
Düz data/bronze/*.json dosyalarını tarihli alt klasöre taşır.
fetched_at[:10] == YYYY-MM-DD → data/bronze/<gün>/<appid>.json
"""
import json, shutil
from collections import defaultdict
from pathlib import Path

BRONZE = Path("data/bronze")

counts = defaultdict(int)
for fp in sorted(BRONZE.glob("*.json")):          # sadece düz dosyalar, alt klasörler hariç
    try:
        obj = json.loads(fp.read_text(encoding="utf-8-sig"))
        day = str(obj.get("fetched_at", ""))[:10]
        if len(day) != 10 or day[4] != "-" or day[7] != "-":
            day = "unknown"
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        day = "unknown"

    dest_dir = BRONZE / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(fp), str(dest_dir / fp.name))
    counts[day] += 1

print("Taşıma tamamlandı:")
for day, n in sorted(counts.items()):
    print(f"  {day}: {n} dosya")
