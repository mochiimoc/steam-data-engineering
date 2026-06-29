import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ingestion.api_client import steamspy, steamstore
from ingestion.app_list import get_app_list

BRONZE = Path("data/bronze")

def harvest(appids, delay=1.5, date_str=None):
    day = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = BRONZE / day
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, appid in enumerate(appids, 1):
        out = out_dir / f"{appid}.json"
        if out.exists():
            continue

        
        ss = steamspy(appid)
        st = steamstore(appid)
        record = {
            "appid" : appid,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "steamspy":ss,
            "store":st,
        }
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), 
                       encoding="utf-8")

        if i % 25 ==0:
            print(f"{i}/{len(appids)} -> {appid}")
        time.sleep(delay)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (varsayılan: bugün UTC)")
    args = ap.parse_args()
    appids = get_app_list(args.limit)
    print(f"{len(appids)} appid alındı, çekiliyor...")
    harvest(appids, date_str=args.date)
    print("bitti.")
