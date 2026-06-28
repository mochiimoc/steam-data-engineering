"""
silver.py — Bronze JSON -> Silver Parquet  (Steam Veri Platformu, Faz 2)

Bronze:  data/bronze/YYYY-MM-DD/*.json   (her dosya bir oyun: appid, fetched_at, steamspy{}, store{})
Silver:  data/silver/games_YYYY-MM-DD.parquet   (oyun basina 1 satir)
         data/silver/game_tags_YYYY-MM-DD.parquet   (uzun: game_id, tag_name, votes)

Kararlar:
- name -> SteamSpy
- sadece type=="game"; success:false ve dlc/demo/soundtrack elenir
- fiyat: Store price_overview varsa ondan, yoksa SteamSpy'a dus (price_source ile isaretlenir)
- birincil (ilk) developer
- developer_id / date_id URETILMEZ -> onlari dbt gold yapar; silver isim + snapshot_date tasir

Kullanim:
    python silver.py 2026-06-27      # belirli gun
    python silver.py                 # en yeni bronze klasoru
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

BRONZE = Path("data/bronze")
SILVER = Path("data/silver")


def to_int(x):
    try:
        return int(str(x).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def cents_to_usd(x):
    v = to_int(x)
    return round(v / 100, 2) if v is not None else None


def parse_owners(s):
    """'5,000,000 .. 10,000,000' -> (5000000, 10000000)"""
    if not s or ".." not in s:
        return (None, None)
    lo, hi = s.split("..", 1)
    clean = lambda x: to_int(x.strip().replace(",", "").replace(" ", ""))
    return (clean(lo), clean(hi))


def pick_price(steamspy, store_data):
    """(price, initial_price, discount_pct, source) — Store oncelik, yoksa SteamSpy."""
    po = store_data.get("price_overview")
    if po:
        return (cents_to_usd(po.get("final")), cents_to_usd(po.get("initial")),
                to_int(po.get("discount_percent")), "store")
    price = cents_to_usd(steamspy.get("price"))
    initial = cents_to_usd(steamspy.get("initialprice"))
    if price is None and initial is None:
        return (None, None, None, None)
    return (price, initial, to_int(steamspy.get("discount")), "steamspy")


def transform_game(obj, snapshot_date):
    store = obj.get("store") or {}
    if not store.get("success"):            # bolge kilidi / olmayan appid
        return None
    d = store.get("data") or {}
    if d.get("type") != "game":             # dlc / demo / music ele
        return None
    if (d.get("release_date") or {}).get("coming_soon"):   # cikmamis oyun ele
        return None

    ss = obj.get("steamspy") or {}
    appid = obj.get("appid") or ss.get("appid")

    lo, hi = parse_owners(ss.get("owners"))
    positive = to_int(ss.get("positive")) or 0
    negative = to_int(ss.get("negative")) or 0
    total = positive + negative
    ratio = round(positive / total, 4) if total else None

    langs = ss.get("languages") or ""
    lang_count = len([x for x in langs.split(",") if x.strip()]) or None

    plat_count = sum(1 for v in (d.get("platforms") or {}).values() if v)

    genres = d.get("genres") or []
    genre = ", ".join(g.get("description", "") for g in genres) or None

    devs = d.get("developers") or []
    developer = devs[0] if devs else ((ss.get("developer") or "").split(",")[0].strip() or None)
    pubs = d.get("publishers") or []
    publisher = pubs[0] if pubs else (ss.get("publisher") or None)

    rd = (d.get("release_date") or {}).get("date")
    release_date = pd.to_datetime(rd, format="%b %d, %Y", errors="coerce")

    price, initial_price, discount_pct, price_source = pick_price(ss, d)

    return {
        "game_id": appid,
        "snapshot_date": snapshot_date,
        "name": ss.get("name") or d.get("name"),     # name -> SteamSpy
        "type": d.get("type"),
        "release_date": release_date,
        "required_age": to_int(d.get("required_age")),
        "is_free": bool(d.get("is_free")),
        "price": price,
        "initial_price": initial_price,
        "discount_pct": discount_pct,
        "price_source": price_source,
        "owners_low": lo,
        "owners_high": hi,
        "positive": positive,
        "negative": negative,
        "positive_ratio": ratio,
        "language_count": lang_count,
        "platform_count": plat_count,
        "genre": genre,
        "developer_name": developer,
        "publisher_name": publisher,
        "ingested_at": obj.get("fetched_at"),
        "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def extract_tags(obj, snapshot_date):
    ss = obj.get("steamspy") or {}
    appid = obj.get("appid") or ss.get("appid")
    tags = ss.get("tags")
    if not isinstance(tags, dict):          # bos oyunlarda tags [] gelebilir
        return []
    return [{"game_id": appid, "snapshot_date": snapshot_date, "tag_name": k, "votes": v}
            for k, v in tags.items()]


def run(date_str):
    bronze_day = BRONZE / date_str
    if not bronze_day.is_dir():
        sys.exit(f"Bronze klasoru yok: {bronze_day}")

    games, tag_rows, skipped = [], [], 0
    files = sorted(bronze_day.glob("*.json"))
    for fp in files:
        try:
            obj = json.loads(fp.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            skipped += 1
            continue
        row = transform_game(obj, date_str)
        if row is None:
            skipped += 1
            continue
        games.append(row)
        tag_rows.extend(extract_tags(obj, date_str))   # tag sadece tutulan oyunlardan

    if not games:
        sys.exit("Hic gecerli oyun cikmadi.")

    games_df = pd.DataFrame(games)
    for c in ["owners_low", "owners_high", "positive", "negative", "required_age",
              "discount_pct", "language_count", "platform_count"]:
        games_df[c] = games_df[c].astype("Int64")
    games_df["release_date"] = pd.to_datetime(games_df["release_date"]).dt.date

    tags_df = pd.DataFrame(tag_rows, columns=["game_id", "snapshot_date", "tag_name", "votes"])
    if not tags_df.empty:
        tags_df["votes"] = tags_df["votes"].astype("Int64")

    SILVER.mkdir(parents=True, exist_ok=True)
    g_out = SILVER / f"games_{date_str}.parquet"
    t_out = SILVER / f"game_tags_{date_str}.parquet"
    games_df.to_parquet(g_out, index=False)
    tags_df.to_parquet(t_out, index=False)

    print(f"OK  {len(files)} dosya -> {len(games_df)} oyun, {len(tags_df)} tag satiri (atlanan {skipped})")
    print(f"    {g_out}")
    print(f"    {t_out}")
    print("    fiyat kaynagi:", games_df["price_source"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD (bossa en yeni bronze klasoru)")
    date_str = ap.parse_args().date
    if not date_str:
        subdirs = sorted(
            d.name for d in BRONZE.iterdir()
            if d.is_dir() and len(d.name) == 10 and d.name[4] == "-" and d.name[7] == "-"
        )
        if not subdirs:
            sys.exit(f"{BRONZE} altinda tarihli alt klasor bulunamadi.")
        date_str = subdirs[-1]
        print(f"En yeni bronze klasoru: {date_str}")
    run(date_str)