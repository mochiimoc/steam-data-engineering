"""
ml/train.py  v2
---------------
features.parquet → 4-model kıyas (RF / LightGBM-reg / Voting / Stacking) + SHAP

Değişiklikler v1 → v2:
  - language_count KALDIRILDI (leakage şüphesi: publisher başarı proxy'si, çıkış-öncesi değil)
  - LightGBM regularize edildi (num_leaves↓, min_child_samples↑, reg_lambda)
  - RF baseline eklendi
  - VotingClassifier (soft, RF+LGBM) eklendi
  - StackingClassifier (RF+LGBM → LR meta) eklendi
  - Final model seçimi sayısal kritere göre otomatik

Çalıştır:
    python ml/train.py

Çıktılar:
    data/ml/model.pkl            — final seçilen pipeline
    data/ml/lgbm_pipeline.pkl    — SHAP için saf LightGBM pipeline
    data/ml/label_encoder.pkl
    data/ml/feature_schema.pkl   — kolon listesi (arayüz için)
    data/ml/cv_results.csv
    data/ml/comparison.png       — 4-model kıyas barplot
    data/ml/shap_summary.png
    data/ml/confusion.png
"""

from pathlib import Path
import json, pickle, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import (
    RandomForestClassifier, VotingClassifier, StackingClassifier
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
import lightgbm as lgb
import shap

warnings.filterwarnings("ignore")

# ── Sabitler ────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
FEAT_PATH = ROOT / "data" / "ml" / "features.parquet"
OUT       = ROOT / "data" / "ml"

TIER_ORDER  = ["nis", "saglam", "hit", "blockbuster"]
N_SPLITS    = 5
SEED        = 42

# v1 referans skoru (language_count'luydu) — rapor için sabit
V1_MACRO_F1 = 0.4047

# ── 1. Veri ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("ml/train.py  v2  — language_count KALDIRILDI (leakage)")
print("=" * 60)
print("\n1/7  Veri yükleniyor…")

df = pd.read_parquet(FEAT_PATH)
df = df[df["sales_tier"].isin(TIER_ORDER)].copy()
print(f"     {len(df):,} oyun, 4 tier")

df["genre"]          = df["genre"].fillna("Unknown")
df["release_season"] = df["release_season"].replace("None", "Unknown").fillna("Unknown")
tr_med = df["dev_track_record"].median()
df["dev_track_record"] = df["dev_track_record"].fillna(tr_med)

# ── Feature tanımı (language_count YOK) ─────────────────────────────────────
CAT_COLS = ["genre", "release_season"]
NUM_COLS = [                              # language_count ÇIKARILDI
    "initial_price",
    "platform_count",
    "dev_track_record",
    "dev_prior_game_count",
    "has_track_record",
]
TAG_COLS = [c for c in df.columns if c.startswith("tag_")]
ALL_COLS = NUM_COLS + CAT_COLS + TAG_COLS

print(f"     Features: {len(ALL_COLS)}  (num={len(NUM_COLS)}, cat={len(CAT_COLS)}, tag={len(TAG_COLS)})")
print(f"     NOT: language_count çıkarıldı (leakage — v1 Macro-F1={V1_MACRO_F1:.4f})")

X = df[ALL_COLS].copy()
le = LabelEncoder()
le.fit(TIER_ORDER)
y = le.transform(df["sales_tier"].values)

# Feature şemasını kaydet (arayüz için — kolon adı + sırası)
schema = {
    "num_cols": NUM_COLS,
    "cat_cols": CAT_COLS,
    "tag_cols": TAG_COLS,
    "all_cols": ALL_COLS,
    "tier_order": TIER_ORDER,
    "dev_track_record_fillna": float(tr_med),
}
with open(OUT / "feature_schema.pkl", "wb") as f:
    pickle.dump(schema, f)

# ── 2. Preprocessor ─────────────────────────────────────────────────────────
print("\n2/7  Preprocessor hazırlanıyor…")

ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32)

def make_prep():
    return ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32), CAT_COLS),
            ("num", "passthrough", NUM_COLS),
            ("tag", "passthrough", TAG_COLS),
        ],
        remainder="drop",
    )

# ── 3. Model tanımları ───────────────────────────────────────────────────────
print("3/7  Model tanımları…")

lgbm_params = dict(
    n_estimators=600,
    learning_rate=0.03,
    num_leaves=20,           # ↓ overfitting'i kıs
    min_child_samples=80,    # ↑
    reg_alpha=0.1,
    reg_lambda=1.0,
    class_weight="balanced",
    subsample=0.8,
    colsample_bytree=0.7,
    random_state=SEED,
    n_jobs=-1,
    verbose=-1,
)

rf_params = dict(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=10,
    class_weight="balanced",
    random_state=SEED,
    n_jobs=-1,
)

lgbm_clf = lgb.LGBMClassifier(**lgbm_params)
rf_clf   = RandomForestClassifier(**rf_params)

voting_clf = VotingClassifier(
    estimators=[("rf", RandomForestClassifier(**rf_params)),
                ("lgbm", lgb.LGBMClassifier(**lgbm_params))],
    voting="soft",
)

stacking_clf = StackingClassifier(
    estimators=[("rf",   RandomForestClassifier(**rf_params)),
                ("lgbm", lgb.LGBMClassifier(**lgbm_params))],
    final_estimator=LogisticRegression(
        max_iter=500, class_weight="balanced", random_state=SEED
    ),
    cv=3,
    n_jobs=1,
)

models = {
    "RF baseline":      Pipeline([("prep", make_prep()), ("clf", rf_clf)]),
    "LightGBM (reg)":   Pipeline([("prep", make_prep()), ("clf", lgbm_clf)]),
    "Voting (RF+LGBM)": Pipeline([("prep", make_prep()), ("clf", voting_clf)]),
    "Stacking":         Pipeline([("prep", make_prep()), ("clf", stacking_clf)]),
}

# ── 4. 5-fold CV kıyası ──────────────────────────────────────────────────────
print("4/7  5-fold stratified CV kıyası çalışıyor…")
print(f"     (Bu adım ~2–5 dk sürebilir)")

cv_splitter = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)

comparison = {}
for name, pipe in models.items():
    print(f"     > {name}...", end="", flush=True)
    res = cross_validate(
        pipe, X, y,
        cv=cv_splitter,
        scoring={"macro_f1": "f1_macro", "accuracy": "accuracy"},
        return_train_score=True,
        n_jobs=1,
    )
    comparison[name] = {
        "val_macro_f1_mean": res["test_macro_f1"].mean(),
        "val_macro_f1_std":  res["test_macro_f1"].std(),
        "val_accuracy_mean": res["test_accuracy"].mean(),
        "train_macro_f1_mean": res["train_macro_f1"].mean(),
    }
    print(f"  val Macro-F1={res['test_macro_f1'].mean():.4f} ± {res['test_macro_f1'].std():.4f}")

comp_df = pd.DataFrame(comparison).T
comp_df.to_csv(OUT / "cv_results.csv")

# ── 5. Kıyas tablosu & grafik ────────────────────────────────────────────────
print("\n5/7  Sonuçlar:")
print(f"\n  {'Model':<25} {'Val Macro-F1':>14} {'±':>6} {'Accuracy':>10} {'Train MF1':>11}")
print(f"  {'-'*70}")
print(f"  {'v1 LightGBM (w/ lang_cnt)':<25} {V1_MACRO_F1:>14.4f} {'(ref)':>6} {'—':>10} {'0.9822':>11}")
print(f"  {'-'*70}")
for name, row in comp_df.iterrows():
    print(f"  {name:<25} {row['val_macro_f1_mean']:>14.4f} {row['val_macro_f1_std']:>6.4f} "
          f"{row['val_accuracy_mean']:>10.4f} {row['train_macro_f1_mean']:>11.4f}")

# Barplot
fig, ax = plt.subplots(figsize=(9, 4))
names  = list(comp_df.index)
means  = comp_df["val_macro_f1_mean"].values
stds   = comp_df["val_macro_f1_std"].values
colors = ["#aec7e8", "#1f77b4", "#ffbb78", "#ff7f0e"]
bars   = ax.bar(names, means, yerr=stds, capsize=5, color=colors, edgecolor="white")
ax.axhline(V1_MACRO_F1, color="red", ls="--", lw=1.2, label=f"v1 ref (w/ lang_cnt) = {V1_MACRO_F1:.3f}")
ax.set_ylabel("Val Macro-F1")
ax.set_title("Model Kıyası — 5-fold Stratified CV\n(language_count kaldırıldı)")
ax.set_ylim(0, max(means) + 0.12)
ax.legend(fontsize=9)
for bar, m, s in zip(bars, means, stds):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + s + 0.01,
            f"{m:.3f}", ha="center", fontsize=9, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "comparison.png", dpi=120, bbox_inches="tight")
plt.close()
print(f"\n     Grafik: data/ml/comparison.png")

# ── 6. Final model seçimi ────────────────────────────────────────────────────
print("\n6/7  Final model seçimi…")

lgbm_score = comp_df.loc["LightGBM (reg)", "val_macro_f1_mean"]
best_name  = comp_df["val_macro_f1_mean"].idxmax()
best_score = comp_df.loc[best_name, "val_macro_f1_mean"]
gap        = best_score - lgbm_score

THRESHOLD = 0.01   # topluluk bu kadar geçmiyorsa LightGBM tercih et (SHAP yorumlanabilirliği)

if best_name == "LightGBM (reg)" or gap <= THRESHOLD:
    chosen_name = "LightGBM (reg)"
    reason = (f"LightGBM seçildi: en iyi topluluk ({best_name}) farkı "
              f"{gap:.4f} ≤ {THRESHOLD} — yorumlanabilirlik öncelikli")
else:
    chosen_name = best_name
    reason = f"{best_name} seçildi: LightGBM'i {gap:.4f} puan geçti (>{THRESHOLD} eşiği)"

print(f"     {reason}")

# Final seçilen pipeline (tüm veri)
final_pipe = Pipeline([("prep", make_prep()), ("clf", {
    "RF baseline":      RandomForestClassifier(**rf_params),
    "LightGBM (reg)":   lgb.LGBMClassifier(**lgbm_params),
    "Voting (RF+LGBM)": VotingClassifier(
        estimators=[("rf", RandomForestClassifier(**rf_params)),
                    ("lgbm", lgb.LGBMClassifier(**lgbm_params))],
        voting="soft"),
    "Stacking":         StackingClassifier(
        estimators=[("rf", RandomForestClassifier(**rf_params)),
                    ("lgbm", lgb.LGBMClassifier(**lgbm_params))],
        final_estimator=LogisticRegression(max_iter=500, class_weight="balanced", random_state=SEED),
        cv=3),
}[chosen_name])])

# SHAP için ayrı LightGBM pipeline (her zaman)
lgbm_pipe = Pipeline([("prep", make_prep()), ("clf", lgb.LGBMClassifier(**lgbm_params))])

print(f"     Tüm veri üzerinde eğitiliyor: {chosen_name}…")
final_pipe.fit(X, y)
print(f"     SHAP için LightGBM eğitiliyor…")
lgbm_pipe.fit(X, y)

# Confusion matrix
y_pred = final_pipe.predict(X)
cm = confusion_matrix(y, y_pred)
fig, ax = plt.subplots(figsize=(6, 5))
ConfusionMatrixDisplay(cm, display_labels=le.classes_).plot(ax=ax, colorbar=False, cmap="Blues")
ax.set_title(f"Confusion Matrix — {chosen_name} (full train)\n"
             f"Val Macro-F1: {comp_df.loc[chosen_name, 'val_macro_f1_mean']:.3f}")
plt.tight_layout()
plt.savefig(OUT / "confusion.png", dpi=120, bbox_inches="tight")
plt.close()

print("\n     Classification Report (full train — referans):")
print(classification_report(y, y_pred, target_names=le.classes_))

# ── 7. SHAP (LightGBM bileşeni üzerinde) ─────────────────────────────────────
print("7/7  SHAP değerleri hesaplanıyor…")

X_tf = lgbm_pipe.named_steps["prep"].transform(X)
ohe_cols = lgbm_pipe.named_steps["prep"].named_transformers_["cat"]\
               .get_feature_names_out(CAT_COLS).tolist()
feat_names = ohe_cols + NUM_COLS + TAG_COLS
X_shap_df  = pd.DataFrame(X_tf, columns=feat_names)

rng = np.random.default_rng(SEED)
idx = rng.choice(len(X_shap_df), size=min(1000, len(X_shap_df)), replace=False)
X_sample = X_shap_df.iloc[idx]

explainer  = shap.TreeExplainer(lgbm_pipe.named_steps["clf"])
sv         = explainer.shap_values(X_sample)

sv_arr = np.array(sv)
n_feats = len(feat_names)
if sv_arr.ndim == 3:
    # shape (n_samples, n_feats, n_classes): axis1==n_feats
    # shape (n_classes, n_samples, n_feats): axis0==n_classes (small)
    if sv_arr.shape[1] == n_feats:
        # (n_samples, n_feats, n_classes) → mean over classes axis
        mean_abs = np.abs(sv_arr).mean(axis=2)   # → (n_samples, n_feats)
    else:
        # (n_classes, n_samples, n_feats) → mean over classes axis
        mean_abs = np.abs(sv_arr).mean(axis=0)   # → (n_samples, n_feats)
elif isinstance(sv, list):
    mean_abs = np.mean([np.abs(s) for s in sv], axis=0)
else:
    mean_abs = np.abs(sv_arr)

# mean_abs: (n_samples, n_feats) → per-feature mean
shap_imp = pd.Series(mean_abs.mean(axis=0), index=feat_names).sort_values(ascending=False)

top25 = shap_imp.head(25)
fig, ax = plt.subplots(figsize=(9, 7))
ax.barh(top25.index[::-1], top25.values[::-1], color="#1f77b4")
ax.set_xlabel("Ortalama |SHAP| değeri")
ax.set_title("Top 25 Feature — SHAP Importance (LightGBM)\n"
             "language_count kaldırıldı, v2")
plt.tight_layout()
plt.savefig(OUT / "shap_summary.png", dpi=120, bbox_inches="tight")
plt.close()
shap_imp.to_csv(OUT / "shap_importance.csv", header=True)

print("\n     Top 10 feature (v2, language_count'suz):")
for feat, val in shap_imp.head(10).items():
    print(f"       {feat:<35} {val:.4f}")

# ── Kaydet ───────────────────────────────────────────────────────────────────
with open(OUT / "model.pkl",        "wb") as f: pickle.dump(final_pipe, f)
with open(OUT / "lgbm_pipeline.pkl","wb") as f: pickle.dump(lgbm_pipe,  f)
with open(OUT / "label_encoder.pkl","wb") as f: pickle.dump(le,          f)

# Seçim kararını JSON'a yaz
decision = {
    "chosen_model":  chosen_name,
    "reason":        reason,
    "v1_macro_f1":   V1_MACRO_F1,
    "v2_scores":     {k: round(v["val_macro_f1_mean"], 4) for k, v in comparison.items()},
    "threshold":     THRESHOLD,
}
with open(OUT / "model_decision.json", "w", encoding="utf-8") as f:
    json.dump(decision, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"KAYDEDILDI:")
print(f"  data/ml/model.pkl          — final: {chosen_name}")
print(f"  data/ml/lgbm_pipeline.pkl  — SHAP için LightGBM")
print(f"  data/ml/label_encoder.pkl")
print(f"  data/ml/feature_schema.pkl — kolon listesi (arayüz)")
print(f"  data/ml/model_decision.json")
print(f"  data/ml/comparison.png")
print(f"  data/ml/shap_summary.png")
print(f"  data/ml/confusion.png")
print(f"  data/ml/cv_results.csv")
print(f"\nSEÇİLEN MODEL: {chosen_name}")
print(f"NEDEN: {reason}")
print(f"{'='*60}")
