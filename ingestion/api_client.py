import requests 
import time 

def _get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(10 * (i + 1))
                continue 
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries -1:
                print(f" ! hata {e}")
                return None 
            time.sleep(2 * (i + 1))

def steamspy(appid):
    return _get("https://steamspy.com/api.php",
                {"request":"appdetails","appid":appid})

def steamstore(appid, cc="us"):
    j = _get("https://store.steampowered.com/api/appdetails",
             {"appids": appid, "cc": cc, "l": "en"})
    return j.get(str(appid)) if j else None