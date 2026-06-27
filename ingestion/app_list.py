import time 
from ingestion.api_client import _get

def get_app_list (n=1000):
    ids, page = [], 0
    while len(ids) < n:
        data = _get("https://steamspy.com/api.php",
                    {"request": "all", "page": page})
        if not data:
            break 
        ids.extend(int(a) for a in data.keys())
        page += 1
        if len (ids) < n:
            time.sleep(60)
    return ids[:n]