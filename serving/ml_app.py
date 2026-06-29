"""
serving/ml_app.py
-----------------
Steam Satış Tier Tahmin Arayüzü (Aşama 2 — language_count kaldırıldı)

Çalıştır:
    streamlit run serving/ml_app.py
"""

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import shap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Yollar ──────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
MODEL_PATH = ROOT / "data" / "ml" / "lgbm_pipeline.pkl"
LE_PATH    = ROOT / "data" / "ml" / "label_encoder.pkl"
SCHEMA_PATH= ROOT / "data" / "ml" / "feature_schema.pkl"
SHAP_PATH  = ROOT / "data" / "ml" / "shap_importance.csv"

TIER_COLORS = {
    "nis":         "#ff7f0e",
    "saglam":      "#2ca02c",
    "hit":         "#1f77b4",
    "blockbuster": "#9467bd",
}
TIER_TR = {
    "nis":         "Niş (20k–100k)",
    "saglam":      "Sağlam (100k–500k)",
    "hit":         "Hit (500k–2M)",
    "blockbuster": "Blockbuster (2M+)",
}

# ── Veri yükleme ─────────────────────────────────────────────────────────────
@st.cache_resource
def load_model():
    with open(MODEL_PATH, "rb") as f:  pipeline = pickle.load(f)
    with open(LE_PATH,    "rb") as f:  le       = pickle.load(f)
    with open(SCHEMA_PATH,"rb") as f:  schema   = pickle.load(f)
    return pipeline, le, schema

@st.cache_data
def load_shap_importance():
    df = pd.read_csv(SHAP_PATH, index_col=0)
    df.columns = ["importance"]
    return df.sort_values("importance", ascending=False)

@st.cache_data
def load_games_for_autocomplete():
    """Tag ve genre listelerini features.parquet'ten çek."""
    fp = ROOT / "data" / "ml" / "features.parquet"
    df = pd.read_parquet(fp, columns=["genre","name"])
    genres = sorted(df["genre"].dropna().str.split(", ").explode().unique().tolist())
    return genres

pipeline, le, schema = load_model()
shap_imp = load_shap_importance()

NUM_COLS  = schema["num_cols"]
CAT_COLS  = schema["cat_cols"]
TAG_COLS  = schema["tag_cols"]
ALL_COLS  = schema["all_cols"]
TIER_ORDER= schema["tier_order"]
TR_MEDIAN = schema["dev_track_record_fillna"]

TAG_NAMES = [c.replace("tag_", "").replace("_", " ") for c in TAG_COLS]
genres_list = load_games_for_autocomplete()


# ── Yardımcı: tahmin vektörü kur ─────────────────────────────────────────────
def build_input(
    initial_price: float,
    genre: str,
    release_season: str,
    platform_count: int,
    dev_track_record: float | None,
    dev_prior_game_count: int,
    has_track_record: int,
    selected_tags: list[str],
) -> pd.DataFrame:
    row = {}

    # Sayısal (language_count YOK)
    row["initial_price"]        = initial_price
    row["platform_count"]       = platform_count
    row["dev_track_record"]     = dev_track_record if dev_track_record is not None else TR_MEDIAN
    row["dev_prior_game_count"] = dev_prior_game_count
    row["has_track_record"]     = has_track_record

    # Kategorik
    row["genre"]          = genre or "Unknown"
    row["release_season"] = release_season

    # Tag multi-hot
    selected_set = set(selected_tags)
    for tag_col, tag_name in zip(TAG_COLS, TAG_NAMES):
        row[tag_col] = 1 if tag_name in selected_set else 0

    return pd.DataFrame([row])[ALL_COLS]


# ── SHAP tek tahmin ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def compute_shap_single(input_tuple):
    """input_tuple: dict→frozen için tuple. Cache uyumlu."""
    row_dict = dict(input_tuple)
    row_df   = pd.DataFrame([row_dict])[ALL_COLS]
    X_tf     = pipeline.named_steps["prep"].transform(row_df)

    ohe_cols = pipeline.named_steps["prep"].named_transformers_["cat"]\
                   .get_feature_names_out(CAT_COLS).tolist()
    feat_names = ohe_cols + NUM_COLS + TAG_COLS

    explainer  = shap.TreeExplainer(pipeline.named_steps["clf"])
    sv         = explainer.shap_values(X_tf)
    sv_arr     = np.array(sv)
    n_feats    = len(feat_names)

    if sv_arr.ndim == 3 and sv_arr.shape[1] == n_feats:
        # (1, n_feats, n_classes) — squeeze sample dim
        local_shap = sv_arr[0].mean(axis=1)   # (n_feats,) — mean over classes
    elif sv_arr.ndim == 3:
        local_shap = sv_arr.mean(axis=0)[0]
    else:
        local_shap = sv_arr[0]

    return pd.Series(local_shap, index=feat_names).sort_values(key=abs, ascending=False)


# ════════════════════════════════════════════════════════════════════════════
# ARAYÜZ
# ════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Steam Satış Tier Tahmini", layout="wide")
st.title("Steam Satış Tier Tahmini")
st.caption(
    "Çıkış-öncesi oyun özelliklerini gir → model satış tier'ını tahmin eder.  \n"
    "Model: LightGBM (reg) · 4 tier · Val Macro-F1: 0.38  \n"
    "⚠ Tahminler SteamSpy bant tahminine dayalı gürültülü target'tan eğitildi — kesin değil, yönlendirici."
)

# ── Sol / sağ panel ──────────────────────────────────────────────────────────
col_input, col_result = st.columns([2, 3])

with col_input:
    st.subheader("Oyun Özellikleri")

    initial_price = st.number_input(
        "Launch Fiyatı (USD) — ücretsizse 0",
        min_value=0.0, max_value=200.0, value=14.99, step=0.99,
    )

    genre = st.selectbox(
        "Birincil Tür",
        ["Unknown"] + genres_list,
        index=0,
    )

    release_season = st.selectbox(
        "Çıkış Mevsimi",
        ["kis", "ilkbahar", "yaz", "sonbahar"],
        format_func={"kis": "Kış", "ilkbahar": "İlkbahar",
                     "yaz": "Yaz", "sonbahar": "Sonbahar"}.get,
    )

    platform_count = st.slider("Platform Sayısı (PC=1, +Mac, +Linux)", 1, 3, 1)

    st.markdown("**Developer Geçmişi**")
    has_tr = st.checkbox("Bu developer'ın önceki oyunu var", value=False)
    if has_tr:
        dev_track_record_val = st.slider(
            "Önceki oyunların ort. tier (0=niş … 3=blockbuster)",
            0.0, 3.0, 2.0, 0.25,
        )
        dev_prior_count = st.number_input("Önceki oyun sayısı", 1, 50, 1, step=1)
    else:
        dev_track_record_val = None
        dev_prior_count      = 0

    st.markdown("**Oyun Etiketleri (top-40 tag)**")
    selected_tags = st.multiselect(
        "Tag seç (birden fazla olabilir)",
        options=TAG_NAMES,
        default=[],
    )

    predict_btn = st.button("Tahmin Et", type="primary", use_container_width=True)

# ── Sonuç paneli ──────────────────────────────────────────────────────────────
with col_result:
    if predict_btn:
        row_df = build_input(
            initial_price    = initial_price,
            genre            = genre,
            release_season   = release_season,
            platform_count   = platform_count,
            dev_track_record = dev_track_record_val,
            dev_prior_game_count = dev_prior_count,
            has_track_record = int(has_tr),
            selected_tags    = selected_tags,
        )

        proba   = pipeline.predict_proba(row_df)[0]
        pred_idx= int(proba.argmax())
        pred_tier = le.classes_[pred_idx]
        confidence= proba[pred_idx]

        # ── Tahmin kutusu
        color = TIER_COLORS.get(pred_tier, "#333")
        st.markdown(
            f"<div style='background:{color}22;border-left:6px solid {color};"
            f"padding:16px;border-radius:8px'>"
            f"<h2 style='margin:0;color:{color}'>{TIER_TR[pred_tier]}</h2>"
            f"<p style='margin:4px 0 0 0;font-size:1.1em'>Güven: <b>{confidence:.0%}</b></p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        # Tüm tier olasılıkları
        st.markdown("**Tier Olasılıkları**")
        prob_df = pd.DataFrame({
            "Tier": [TIER_TR[t] for t in le.classes_],
            "Olasılık": proba,
        }).sort_values("Olasılık", ascending=False)
        st.dataframe(
            prob_df.style.format({"Olasılık": "{:.1%}"}),
            use_container_width=True,
            hide_index=True,
        )

        # SHAP açıklaması
        st.markdown("**Bu Tahmin İçin En Etkili Özellikler (SHAP)**")
        with st.spinner("SHAP hesaplanıyor…"):
            row_tuple = tuple(sorted(row_df.iloc[0].to_dict().items()))
            try:
                local_shap = compute_shap_single(row_tuple)
                top10 = local_shap.head(10)
                fig, ax = plt.subplots(figsize=(6, 3.5))
                colors_bar = ["#d62728" if v > 0 else "#1f77b4" for v in top10.values]
                ax.barh(top10.index[::-1], top10.values[::-1], color=colors_bar[::-1])
                ax.axvline(0, color="gray", lw=0.8)
                ax.set_xlabel("SHAP değeri (+ = tier yukarı iter)")
                ax.set_title("Lokal SHAP — bu oyun")
                plt.tight_layout()
                st.pyplot(fig)
                plt.close()
            except Exception as e:
                st.warning(f"SHAP hesaplanamadı: {e}")

    else:
        st.info("Soldaki formu doldurup 'Tahmin Et' düğmesine bas.")

        # Global feature importance
        st.markdown("---")
        st.markdown("**Global Feature Önemi (SHAP — tüm veri)**")
        top15 = shap_imp.head(15)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.barh(top15.index[::-1], top15["importance"].values[::-1], color="#1f77b4")
        ax.set_xlabel("Ort |SHAP|")
        ax.set_title("Top 15 Feature (LightGBM v2, language_count kaldırıldı)")
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

        st.caption(
            "Not: language_count v1'de en güçlü feature'dı (SHAP=0.485) ama "
            "publisher başarı proxy'si olduğu için çıkarıldı (leakage şüphesi). "
            "Bu nedenle v2 Macro-F1 (0.38) v1'den (0.40) düşük — dürüst skor."
        )
