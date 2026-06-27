import json
import time
from pathlib import Path

from ingestion.api_client import steamspy, steamstore
from ingestion.app_list import get_app_list

BRONZE = Path("data/bronze")
BRONZE.mkdir(parents=True, exist_ok=True)

def harvest(appids, delay=1.5):
    for i, appid in enumerate(appids, 1):
        out = BRONZE / f"{appid}.json"
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
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2))

        if i % 25 ==0:
            print(f"{i}/{len(appids)} -> {appid}")
        time.sleep(delay)

if __name__ == "__main__":
    appids = get_app_list(20)
    print(f"{len(appids)} appid alındı, çekiliyor...")
    harvest(appids)
    print("bitti.")  
