"""
ml/features.py
--------------
Gold warehouse → oyun başına tek satır ML feature tablosu.

Çalıştır:
    python ml/features.py

Çıktı:
    data/ml/features.parquet

Leakage kuralı: sadece çıkış-öncesi bilinen feature'lar.
Sandbox sütunlar (model'e girMEYECEK): owners_*, positive, negative,
positive_ratio, review_count ayrı grupla taşınır.
"""

from pathlib import Path
import duckdb
import pandas as pd
import numpy as np

# ── Ayarlar ─────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "data" / "gold" / "steam.duckdb"
OUT_PATH = Path(__file__).parent.parent / "data" / "ml" / "features.parquet"

TOP_N_TAGS = 40   # multi-hot için en sık N tag

TIER_BINS   = [0, 20_000, 100_000, 500_000, 2_000_000, float("inf")]
TIER_LABELS = ["flop", "nis", "saglam", "hit", "blockbuster"]
TIER_NUM    = {"flop": 0, "nis": 1, "saglam": 2, "hit": 3, "blockbuster": 4}


# ── 1. Ham veri: oyun başına tek satır ──────────────────────────────────────
def load_base(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    SELECT
        g.game_id,
        g.name,
        g.genre,
        g.release_date,
        g.is_free,
        g.language_count,
        g.platform_count,
        g.developer_id,
        f.initial_price,
        f.owners_low,
        f.owners_high,
        f.positive,
        f.negative
    FROM dim_game g
    JOIN (
        SELECT * FROM fact_game_snapshot
        QUALIFY row_number() OVER (PARTITION BY game_id ORDER BY date_id DESC) = 1
    ) f ON g.game_id = f.game_id
    """
    df = con.execute(q).df()
    df["release_date"] = pd.to_datetime(df["release_date"])
    return df


# ── 2. Tag multi-hot ─────────────────────────────────────────────────────────
def load_tags(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    SELECT b.game_id, t.tag_name
    FROM bridge_game_tag b
    JOIN dim_tag t ON t.tag_id = b.tag_id
    """
    return con.execute(q).df()


def build_tag_multihot(base: pd.DataFrame, tags: pd.DataFrame, n: int) -> pd.DataFrame:
    # En sık N tag'i bul (havuzdaki oyunlarla kesişim)
    game_ids = set(base["game_id"])
    tags_filtered = tags[tags["game_id"].isin(game_ids)]
    top_tags = (
        tags_filtered["tag_name"].value_counts().head(n).index.tolist()
    )
    # Pivot: oyun × tag → 1/0
    top_tag_df = tags_filtered[tags_filtered["tag_name"].isin(top_tags)]
    top_tag_df = top_tag_df.drop_duplicates(["game_id", "tag_name"])
    pivot = pd.crosstab(top_tag_df["game_id"], top_tag_df["tag_name"])
    pivot.columns = [f"tag_{c.replace(' ', '_').replace('/', '_')}" for c in pivot.columns]
    pivot = pivot.reindex(base["game_id"], fill_value=0).reset_index()
    pivot = pivot.rename(columns={"game_id": "game_id"})
    return pivot, top_tags


# ── 3. Target: sales_tier ────────────────────────────────────────────────────
def assign_tier(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["owners_mid"] = (df["owners_low"] + df["owners_high"]) / 2.0
    # owners_mid null/0 → at
    df = df[(df["owners_mid"].notna()) & (df["owners_mid"] > 0)].copy()
    df["sales_tier"] = pd.cut(
        df["owners_mid"],
        bins=TIER_BINS,
        labels=TIER_LABELS,
        right=False,
    ).astype(str)
    df["tier_num"] = df["sales_tier"].map(TIER_NUM).astype(float)
    return df


# ── 4. Release season ────────────────────────────────────────────────────────
def release_season(date_series: pd.Series) -> pd.Series:
    month = date_series.dt.month
    return pd.cut(
        month,
        bins=[0, 3, 6, 9, 12],
        labels=["kis", "ilkbahar", "yaz", "sonbahar"],
        right=True,
    ).astype(str).replace("nan", None)


# ── 5. Developer track record (leakage-safe) ─────────────────────────────────
def build_developer_track_record(df: pd.DataFrame) -> pd.DataFrame:
    """
    Her oyun için aynı developer'ın bu oyunun release_date'inden ÖNCE çıkmış
    oyunlarının ortalama tier_num'unu hesapla (leakage-safe self-join).
    """
    valid = df[df["release_date"].notna()][
        ["game_id", "developer_id", "release_date", "tier_num"]
    ].copy()

    # Self-join: sol = hedef oyun, sağ = aynı developer'ın diğer oyunları
    joined = valid.merge(
        valid[["game_id", "developer_id", "release_date", "tier_num"]],
        on="developer_id",
        suffixes=("", "_prior"),
    )
    # Leakage guard: sadece hedeften ÖNCE çıkan, farklı oyunlar
    prior = joined[
        (joined["release_date_prior"] < joined["release_date"]) &
        (joined["game_id_prior"] != joined["game_id"])
    ]

    agg = (
        prior.groupby("game_id")
        .agg(
            dev_track_record=("tier_num_prior", "mean"),
            dev_prior_game_count=("game_id_prior", "count"),
        )
        .reset_index()
    )
    agg["has_track_record"] = 1

    # Tüm oyunları kapsayacak şekilde merge; olmayan → 0 / NaN
    result = df[["game_id"]].merge(agg, on="game_id", how="left")
    result["has_track_record"] = result["has_track_record"].fillna(0).astype(int)
    result["dev_prior_game_count"] = result["dev_prior_game_count"].fillna(0).astype(int)
    # dev_track_record NaN kalır (bilinmiyor işareti)
    return result


# ── 6. Ana pipeline ──────────────────────────────────────────────────────────
def build_features() -> pd.DataFrame:
    print(f"DuckDB: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)

    print("1/5  Ham veri yükleniyor…")
    base = load_base(con)
    print(f"     {len(base):,} oyun")

    print("2/5  Tag multi-hot üretiliyor…")
    tags = load_tags(con)
    con.close()

    tag_pivot, top_tags = build_tag_multihot(base, tags, TOP_N_TAGS)
    print(f"     Top {TOP_N_TAGS} tag: {top_tags[:5]}…")

    print("3/5  Target (sales_tier) atanıyor…")
    base = assign_tier(base)
    print(f"     {len(base):,} oyun (owners_mid > 0 filtresi sonrası)")
    print(f"     Tier dağılımı:\n{base['sales_tier'].value_counts().sort_index()}")

    print("4/5  Developer track record hesaplanıyor (self-join, yavaş olabilir)…")
    track = build_developer_track_record(base)
    has_tr = track["has_track_record"].sum()
    print(f"     Track record var: {has_tr:,} / {len(track):,} oyun "
          f"({has_tr/len(track)*100:.1f}%)")

    print("5/5  Feature tablosu birleştiriliyor…")
    feat = base.merge(tag_pivot, on="game_id", how="left")
    feat = feat.merge(track, on="game_id", how="left")

    # Release season
    feat["release_season"] = release_season(feat["release_date"])

    # initial_price: ücretsiz oyunlar → 0
    feat["initial_price"] = feat["initial_price"].fillna(0.0)

    # positive_ratio sandbox
    feat["positive_ratio"] = np.where(
        (feat["positive"] + feat["negative"]) > 0,
        feat["positive"] / (feat["positive"] + feat["negative"]),
        np.nan,
    )

    # Kolon grupları
    feature_cols = (
        ["game_id", "name", "sales_tier", "tier_num"]          # kimlik + target
        + ["initial_price", "genre", "release_season",          # temel feature
           "language_count", "platform_count",
           "dev_track_record", "dev_prior_game_count", "has_track_record"]
        + [c for c in feat.columns if c.startswith("tag_")]     # multi-hot
    )
    sandbox_cols = ["owners_low", "owners_high", "owners_mid",  # leakage / sandbox
                    "positive", "negative", "positive_ratio"]
    meta_cols = ["release_date", "developer_id", "is_free"]

    out = feat[feature_cols + sandbox_cols + meta_cols].copy()

    print(f"\nFinal tablo: {out.shape[0]:,} satır × {out.shape[1]} kolon")
    print(f"  Feature kolon sayısı (tag dahil): {len(feature_cols)}")
    print(f"  Sandbox kolon sayısı: {len(sandbox_cols)}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nYazıldı: {OUT_PATH}")
    return out


if __name__ == "__main__":
    df = build_features()
    print("\nKolon listesi (ilk 20):")
    print(df.columns[:20].tolist())
    print("\nDtype'lar:")
    print(df.dtypes.value_counts())
