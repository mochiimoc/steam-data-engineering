import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
from pathlib import Path

# ── config ──────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "data" / "gold" / "steam.duckdb"
MIN_REVIEWS = 50   # hidden gems & kalite sıralamalarında minimum yorum sayısı
MIN_DEV_GAMES = 3  # developer kalitesi için minimum oyun sayısı

st.set_page_config(page_title="Steam Pazar Anlık Görünümü", layout="wide")


# ── veri yükleme ─────────────────────────────────────────────────────────────
def _con():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data
def load_games() -> pd.DataFrame:
    """dim_game + en güncel fact snapshot — oyun başına tek satır."""
    q = """
    SELECT
        g.game_id,
        g.name,
        g.genre,
        g.release_date,
        g.is_free,
        g.language_count,
        g.platform_count,
        f.price,
        f.owners_low,
        f.owners_high,
        f.positive,
        f.negative,
        CASE WHEN (f.positive + f.negative) > 0
             THEN f.positive * 1.0 / (f.positive + f.negative)
             ELSE NULL END AS positive_ratio
    FROM dim_game g
    JOIN (
        SELECT * FROM fact_game_snapshot
        QUALIFY row_number() OVER (PARTITION BY game_id ORDER BY date_id DESC) = 1
    ) f ON g.game_id = f.game_id
    WHERE f.owners_high IS NOT NULL
    """
    con = _con()
    df = con.execute(q).df()
    con.close()
    df["owners_mid"] = (df["owners_low"] + df["owners_high"]) / 2
    df["total_reviews"] = df["positive"] + df["negative"]
    return df


@st.cache_data
def load_hidden_gems() -> pd.DataFrame:
    con = _con()
    df = con.execute("SELECT * FROM hidden_gems").df()
    con.close()
    if "owners_low" in df.columns:
        df["owners_mid"] = (df["owners_low"] + df["owners_high"]) / 2
    else:
        df["owners_mid"] = df["owners_high"] / 2
    df["total_reviews"] = df["positive"] + df["negative"]
    return df[df["total_reviews"] >= MIN_REVIEWS].reset_index(drop=True)


@st.cache_data
def load_tag_summary() -> pd.DataFrame:
    con = _con()
    df = con.execute("SELECT * FROM tag_price_summary ORDER BY game_count DESC").df()
    con.close()
    return df


@st.cache_data
def load_developer_quality() -> pd.DataFrame:
    con = _con()
    df = con.execute("SELECT * FROM developer_quality").df()
    con.close()
    return df[df["game_count"] >= MIN_DEV_GAMES].sort_values(
        "avg_positive_ratio", ascending=False
    ).reset_index(drop=True)


@st.cache_data
def load_tags_for_games() -> pd.DataFrame:
    """bridge + tag adı + oyun adı, fiyat, puan için."""
    q = """
    SELECT
        b.game_id,
        g.name,
        g.genre,
        g.is_free,
        f.price,
        CASE WHEN (f.positive + f.negative) > 0
             THEN f.positive * 1.0 / (f.positive + f.negative)
             ELSE NULL END AS positive_ratio,
        f.positive,
        f.negative,
        t.tag_name,
        b.votes,
        (f.owners_low + f.owners_high) / 2 AS owners_mid
    FROM bridge_game_tag b
    JOIN dim_tag t ON t.tag_id = b.tag_id
    JOIN dim_game g ON g.game_id = b.game_id
    JOIN (
        SELECT * FROM fact_game_snapshot
        QUALIFY row_number() OVER (PARTITION BY game_id ORDER BY date_id DESC) = 1
    ) f ON f.game_id = b.game_id
    """
    con = _con()
    df = con.execute(q).df()
    con.close()
    return df


games = load_games()
hidden = load_hidden_gems()
tag_summary = load_tag_summary()
devq = load_developer_quality()
tags_games = load_tags_for_games()

# ── header ────────────────────────────────────────────────────────────────────
st.title("Steam Pazar Anlık Görünümü")
st.caption(
    f"~{len(games):,} oyunun tek-snapshot analizi. "
    "Zaman-serisi trendi yok — yalnızca çekim tarihi itibarıyla cross-sectional veri."
)

tabs = st.tabs([
    "📊 Genel", "💲 Fiyat Dağılımı", "⭐ Fiyat ↔ Kalite",
    "💎 Hidden Gems", "🏷️ Tag Analizi", "🏭 Developer Kalitesi", "📅 Yıllara Göre"
])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — GENEL
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Genel Bakış")
    paid = games[(~games["is_free"]) & (games["price"] > 0)]
    free_pct = games["is_free"].mean() * 100

    top_genres = (
        games["genre"]
        .dropna()
        .str.split(", ")
        .explode()
        .value_counts()
        .head(5)
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Oyun", f"{len(games):,}")
    c2.metric("Medyan Fiyat (ücretli)", f"${paid['price'].median():.2f}")
    c3.metric("Ücretsiz Oyun Oranı", f"{free_pct:.1f}%")
    c4.metric("Benzersiz Tür", f"{games['genre'].dropna().nunique():,}")

    st.markdown("#### En Kalabalık 5 Tür (oyun başına ilk tür)")
    first_genre = (
        games["genre"].dropna().str.split(", ").str[0].value_counts().head(5)
    )
    st.bar_chart(first_genre)

    st.markdown("#### Platform Dağılımı")
    plat = games["platform_count"].value_counts().sort_index()
    st.bar_chart(plat)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — FİYAT DAĞILIMI
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Fiyat Dağılımı (ücretli oyunlar, price > 0)")
    st.caption("Ücretsiz oyunlar bu grafikten çıkarıldı. Aşırı uçlar için %95 percentile kırpması uygulandı.")

    genre_opts = ["Tümü"] + sorted(
        games["genre"].dropna().str.split(", ").explode().unique().tolist()
    )
    sel_genre = st.selectbox("Tür filtresi", genre_opts, key="price_genre")

    paid = games[(~games["is_free"]) & (games["price"] > 0)].copy()
    if sel_genre != "Tümü":
        paid = paid[paid["genre"].fillna("").str.contains(sel_genre, regex=False)]

    p95 = paid["price"].quantile(0.95)
    paid_clip = paid[paid["price"] <= p95]

    median_price = paid_clip["price"].median()
    fig = px.histogram(
        paid_clip, x="price", nbins=40,
        labels={"price": "Fiyat (USD)"},
        title=f"Fiyat Dağılımı — {sel_genre} ({len(paid_clip):,} oyun)"
    )
    fig.add_vline(x=median_price, line_dash="dash", line_color="orange",
                  annotation_text=f"Medyan ${median_price:.2f}", annotation_position="top right")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Not: ${p95:.2f} üzerindeki aşırı uçlar (%5) grafik dışında. Ücretsiz oyun oranı: {free_pct:.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — FİYAT ↔ KALİTE
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Fiyat Bandı ↔ Ortalama Puan")
    st.caption(f"Min {MIN_REVIEWS} yorumlu ücretli oyunlar. Ücretsizler ayrı gösterildi.")

    scored = games[
        (games["total_reviews"] >= MIN_REVIEWS) &
        (~games["is_free"]) &
        (games["price"] > 0)
    ].copy()

    bins = [0, 5, 10, 20, 30, 50, 999]
    labels = ["$0–5", "$5–10", "$10–20", "$20–30", "$30–50", "$50+"]
    scored["price_band"] = pd.cut(scored["price"], bins=bins, labels=labels)

    band_stats = (
        scored.groupby("price_band", observed=True)["positive_ratio"]
        .agg(["mean", "count"])
        .reset_index()
    )
    band_stats.columns = ["Fiyat Bandı", "Ort. Puan Oranı", "Oyun Sayısı"]

    fig2 = px.bar(
        band_stats, x="Fiyat Bandı", y="Ort. Puan Oranı",
        text="Oyun Sayısı",
        color="Ort. Puan Oranı", color_continuous_scale="RdYlGn",
        range_y=[0, 1],
        title="Fiyat Bandına Göre Ortalama Pozitif Yorum Oranı"
    )
    fig2.update_traces(texttemplate="%{text} oyun", textposition="outside")
    st.plotly_chart(fig2, use_container_width=True)

    # Free vs paid comparison
    free_ratio = games[games["is_free"] & (games["total_reviews"] >= MIN_REVIEWS)]["positive_ratio"].mean()
    paid_ratio = scored["positive_ratio"].mean()
    c1, c2 = st.columns(2)
    c1.metric("Ücretli — Ort. Puan Oranı", f"{paid_ratio:.1%}")
    c2.metric("Ücretsiz — Ort. Puan Oranı", f"{free_ratio:.1%}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — HIDDEN GEMS
# ═══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Hidden Gems")
    st.caption(
        f"Yüksek puan / düşük sahip sayısı. Min {MIN_REVIEWS} yorum filtresi uygulandı. "
        "Sahip sayısı SteamSpy bant ortası tahminidir."
    )

    sort_col = st.selectbox("Sırala", ["positive_ratio", "owners_high"], key="gem_sort")
    asc = sort_col == "owners_high"
    show_n = st.slider("Gösterilecek oyun sayısı", 5, 30, 15)

    gem_df = hidden.sort_values(sort_col, ascending=asc).head(show_n)

    for _, row in gem_df.iterrows():
        appid = int(row["game_id"])
        img_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
        col_img, col_info = st.columns([2, 5])
        with col_img:
            try:
                st.image(img_url, use_container_width=True)
            except Exception:
                st.write(row["name"])
        with col_info:
            owners_str = f"{row['owners_high']/1_000_000:.1f}M" if row["owners_high"] >= 1_000_000 else f"{row['owners_high']/1_000:.0f}K"
            st.markdown(f"**{row['name']}** — {row['genre']}")
            st.markdown(
                f"Puan: **{row['positive_ratio']:.0%}** &nbsp;|&nbsp; "
                f"Yorumlar: {int(row['positive'])}👍 / {int(row['negative'])}👎 &nbsp;|&nbsp; "
                f"Tahmini sahip (bant üst): ≤{owners_str}"
            )
        st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5 — TAG ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Tag Analizi")

    top_tags = tag_summary["tag_name"].head(100).tolist()
    sel_tag = st.selectbox("Tag seç", top_tags, key="tag_sel")

    tag_row = tag_summary[tag_summary["tag_name"] == sel_tag]
    if not tag_row.empty:
        r = tag_row.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Oyun Sayısı", f"{int(r['game_count']):,}")
        c2.metric("Medyan Fiyat", f"${r['median_price']:.2f}")
        c3.metric("Ort. Fiyat", f"${r['avg_price']:.2f}")
        c4.metric("Fiyat Aralığı", f"${r['min_price']:.2f} – ${r['max_price']:.2f}")

    # Bu tag'e sahip oyunların puan dağılımı
    tag_games = tags_games[tags_games["tag_name"] == sel_tag].copy()
    scored_tag = tag_games[
        (tag_games["positive"] + tag_games["negative"] >= MIN_REVIEWS)
    ]
    if not scored_tag.empty:
        st.markdown(f"**{sel_tag}** tag'li oyunların puan dağılımı ({len(scored_tag):,} oyun, min {MIN_REVIEWS} yorum)")
        fig3 = px.histogram(
            scored_tag, x="positive_ratio", nbins=20,
            labels={"positive_ratio": "Pozitif Yorum Oranı"},
            range_x=[0, 1]
        )
        st.plotly_chart(fig3, use_container_width=True)

    # Top 20 oyun bu tag'de
    top_tag_games = (
        tag_games[tag_games["positive"] + tag_games["negative"] >= MIN_REVIEWS]
        .sort_values("positive_ratio", ascending=False)
        .drop_duplicates("game_id")
        .head(20)[["name", "genre", "price", "positive_ratio", "owners_mid"]]
    )
    top_tag_games.columns = ["Oyun", "Tür", "Fiyat ($)", "Puan Oranı", "Tahmini Sahip (bant ortası)"]
    top_tag_games["Fiyat ($)"] = top_tag_games["Fiyat ($)"].round(2)
    top_tag_games["Puan Oranı"] = (top_tag_games["Puan Oranı"] * 100).round(1).astype(str) + "%"
    top_tag_games["Tahmini Sahip (bant ortası)"] = top_tag_games["Tahmini Sahip (bant ortası)"].apply(
        lambda x: f"{x/1_000_000:.1f}M" if x >= 1_000_000 else f"{x/1_000:.0f}K"
    )
    st.dataframe(top_tag_games, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 6 — DEVELOPER KALİTESİ
# ═══════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Developer Kalitesi")
    st.caption(
        f"Min {MIN_DEV_GAMES} oyunlu developerlar. "
        f"Oyunların ortalama pozitif yorum oranına göre sıralı. "
        f"Min {MIN_REVIEWS} yorum filtresi view'de uygulanmamış olabilir — küçük örneklemlere dikkat."
    )

    top_n = st.slider("Gösterilecek developer sayısı", 5, 50, 20, key="dev_n")
    show_df = devq.head(top_n)[["developer_name", "game_count", "avg_positive_ratio", "min_positive_ratio", "max_positive_ratio"]].copy()
    show_df.columns = ["Developer", "Oyun Sayısı", "Ort. Puan", "Min Puan", "Max Puan"]
    for col in ["Ort. Puan", "Min Puan", "Max Puan"]:
        show_df[col] = (show_df[col] * 100).round(1).astype(str) + "%"

    st.dataframe(show_df, use_container_width=True)

    fig4 = px.bar(
        devq.head(top_n).sort_values("avg_positive_ratio"),
        x="avg_positive_ratio", y="developer_name",
        orientation="h",
        labels={"avg_positive_ratio": "Ort. Puan Oranı", "developer_name": "Developer"},
        title=f"En Tutarlı {top_n} Developer",
        color="game_count", color_continuous_scale="Blues"
    )
    fig4.update_layout(height=max(400, top_n * 22), yaxis_title="")
    st.plotly_chart(fig4, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 7 — YILLARA GÖRE
# ═══════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Yıllara Göre Çıkan Oyunlar")
    st.caption(
        "Kaynak: oyunların release_date'i — bu zaman bilgisi veride mevcut. "
        "Fiyat snapshot değişimi değil, o yılda çıkan oyunların medyan launch fiyatı."
    )

    yearly = games[games["release_date"].notna()].copy()
    yearly["year"] = pd.to_datetime(yearly["release_date"]).dt.year
    yearly = yearly[(yearly["year"] >= 2000) & (yearly["year"] <= 2025)]

    year_count = yearly.groupby("year").size().reset_index(name="Oyun Sayısı")
    year_price = (
        yearly[(~yearly["is_free"]) & (yearly["price"] > 0)]
        .groupby("year")["price"]
        .median()
        .reset_index(name="Medyan Fiyat ($)")
    )
    year_df = year_count.merge(year_price, on="year", how="left")
    year_df = year_df.rename(columns={"year": "Yıl"})

    col_a, col_b = st.columns(2)
    with col_a:
        fig5 = px.bar(year_df, x="Yıl", y="Oyun Sayısı", title="Yıllık Çıkan Oyun Sayısı")
        st.plotly_chart(fig5, use_container_width=True)
    with col_b:
        fig6 = px.line(
            year_df.dropna(subset=["Medyan Fiyat ($)"]),
            x="Yıl", y="Medyan Fiyat ($)",
            title="Çıkış Yılına Göre Medyan Fiyat (ücretli oyunlar)",
            markers=True
        )
        st.plotly_chart(fig6, use_container_width=True)

    st.caption(
        "Not: 2025 verileri yıl henüz tamamlanmadığından kısmi görünür. "
        "Bu grafik snapshot değişimi değil, çıkış yılı bazlı statik kesit analizi."
    )
