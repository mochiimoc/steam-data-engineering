"""Generates notebooks/ml_eda.ipynb — run once."""
import json
from pathlib import Path

def code(src):
    return {"cell_type": "code", "source": src, "metadata": {}, "outputs": [], "execution_count": None}

def md(src):
    return {"cell_type": "markdown", "source": src, "metadata": {}}


SETUP = """\
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

df = pd.read_parquet("../data/ml/features.parquet")
print(f"Satir: {len(df):,}  Kolon: {df.shape[1]}")
df.head(3)
"""

TIER = """\
tier_order = ["flop", "nis", "saglam", "hit", "blockbuster"]
tier_counts = df["sales_tier"].value_counts().reindex(tier_order, fill_value=0)
tier_pct    = (tier_counts / tier_counts.sum() * 100).round(1)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
colors = ["#d62728","#ff7f0e","#2ca02c","#1f77b4","#9467bd"]
axes[0].bar(tier_order, tier_counts.values, color=colors)
axes[0].set_title("Tier Dagilimi - Oyun Sayisi")
axes[0].set_ylabel("Oyun Sayisi")
for i, (c, p) in enumerate(zip(tier_counts.values, tier_pct.values)):
    axes[0].text(i, c + 50, f"{c:,}\\n({p}%)", ha="center", fontsize=9)

present = [t for t in tier_order if tier_counts[t] > 0]
axes[1].pie([tier_counts[t] for t in present], labels=present, autopct="%1.1f%%")
axes[1].set_title("Tier Oranlari")
plt.tight_layout()
plt.savefig("../data/ml/eda_tier_dist.png", dpi=120, bbox_inches="tight")
plt.show()
print(tier_counts.to_string())
print(f"\\nMax/min sinif orani: {tier_counts.max() / tier_counts[tier_counts>0].min():.1f}x")
"""

MISSING = """\
print("=== Eksik Veri ===")
items = {
    "release_date null":     df["release_date"].isna().sum(),
    "release_season None":   (df["release_season"] == "None").sum(),
    "dev_track_record null": df["dev_track_record"].isna().sum(),
    "has_track_record=1":    int(df["has_track_record"].sum()),
    "has_track_record=0":    int((df["has_track_record"]==0).sum()),
}
for k, v in items.items():
    print(f"  {k:<30} {v:>5,}  ({v/len(df)*100:.1f}%)")

cols_check = ["dev_track_record","release_date","initial_price","genre","language_count","platform_count"]
null_pcts = [df[c].isna().mean()*100 for c in cols_check]
fig, ax = plt.subplots(figsize=(8,3))
bars = ax.barh(cols_check, null_pcts, color="#d62728")
ax.set_xlabel("Eksik %")
ax.set_title("Feature Bazinda Eksik Veri Orani")
for bar, pct in zip(bars, null_pcts):
    ax.text(max(pct+0.3, 0.3), bar.get_y()+bar.get_height()/2, f"{pct:.1f}%", va="center")
plt.tight_layout()
plt.savefig("../data/ml/eda_missing.png", dpi=120, bbox_inches="tight")
plt.show()
"""

BOXPLOT = """\
tier_present = [t for t in ["nis","saglam","hit","blockbuster"] if t in df["sales_tier"].values]
feats = ["initial_price", "language_count", "platform_count", "dev_track_record"]
fig, axes = plt.subplots(1, 4, figsize=(18, 5))
for ax, feat in zip(axes, feats):
    data = [df[df["sales_tier"]==t][feat].dropna().values for t in tier_present]
    ax.boxplot(data, tick_labels=tier_present, showfliers=False)
    ax.set_title(feat)
    if feat == "initial_price":
        ax.set_ylim(0, 60)
plt.suptitle("Feature Dagilimi per Tier (fliers gizlendi)")
plt.tight_layout()
plt.savefig("../data/ml/eda_feature_boxplots.png", dpi=120, bbox_inches="tight")
plt.show()
"""

TAGS = """\
tag_cols = [c for c in df.columns if c.startswith("tag_")]
tag_avg = {}
for col in tag_cols:
    mask = df[col] == 1
    if mask.sum() > 50:
        name = col.replace("tag_", "").replace("_", " ")
        tag_avg[name] = df.loc[mask, "tier_num"].mean()

ts = pd.Series(tag_avg).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(10, 8))
colors = ["#2ca02c" if v>=2.3 else ("#ff7f0e" if v>=2.0 else "#d62728") for v in ts.values]
ax.barh(ts.index, ts.values, color=colors)
ax.axvline(df["tier_num"].mean(), color="gray", ls="--",
           label=f"Genel ort {df['tier_num'].mean():.2f}")
ax.set_xlabel("Ort Tier Num (0=flop..4=blockbuster)")
ax.set_title("Tag bazinda ortalama satis tier")
ax.legend()
plt.tight_layout()
plt.savefig("../data/ml/eda_tag_tier.png", dpi=120, bbox_inches="tight")
plt.show()
print("Yuksek tier tagler (>2.3):", ts[ts>2.3].index.tolist())
print("Dusuk tier tagler (<2.0):",  ts[ts<2.0].index.tolist())
"""

TRACK_REC = """\
tr = df[df["has_track_record"]==1]["dev_track_record"]
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].hist(tr, bins=20, color="#1f77b4", edgecolor="white")
axes[0].set_xlabel("dev_track_record")
axes[0].set_title(f"Developer Track Record Dagilimi (n={len(tr):,})")

tier_present = [t for t in ["nis","saglam","hit","blockbuster"] if t in df["sales_tier"].values]
grp = df.groupby(["has_track_record","sales_tier"]).size().unstack(fill_value=0)
grp_pct = grp.div(grp.sum(axis=1), axis=0) * 100
grp_pct.index = ["TR Yok","TR Var"]
grp_pct[tier_present].plot(kind="bar", ax=axes[1], colormap="tab10")
axes[1].set_title("Track Record Durumuna Gore Tier Orani")
axes[1].set_ylabel("%")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("../data/ml/eda_track_record.png", dpi=120, bbox_inches="tight")
plt.show()
print(f"TR var  - ort tier: {df[df['has_track_record']==1]['tier_num'].mean():.2f}")
print(f"TR yok  - ort tier: {df[df['has_track_record']==0]['tier_num'].mean():.2f}")
"""

SUMMARY = """\
print("=== features.parquet Ozeti ===")
print(f"Satir: {len(df):,}")
print(f"Toplam kolon: {df.shape[1]}")
tag_count = len([c for c in df.columns if c.startswith("tag_")])
print(f"  Tag multi-hot kolonlar: {tag_count}")
print(f"  Temel feature'lar: initial_price, genre, release_season, "
      f"language_count, platform_count, dev_track_record, dev_prior_game_count, has_track_record")
print(f"  Sandbox (modele girmesin): owners_*, positive, negative, positive_ratio")
print()
tier_order = ["flop","nis","saglam","hit","blockbuster"]
print("Tier dagilimi (final):")
print(df["sales_tier"].value_counts().reindex(tier_order, fill_value=0).to_string())
"""

nb = {
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "cells": [
        md("# Steam ML — EDA: Feature Tablosu Kesfi\n\n"
           "Kaynak: `data/ml/features.parquet`  \nModel YOK — sadece dagilim ve sinyal kesfi."),
        code(SETUP),
        md("## 1. Tier Dagilimi (en kritik)\n"
           "SteamSpy yanliligi: veri tabani 50k+ sahipli oyunlari kapsıyor → flop bos beklenir."),
        code(TIER),
        md("## 2. Feature Kapsama — Eksik Veri"),
        code(MISSING),
        md("## 3. Kaba Sinyal Kontrolu\n"
           "Box plot: initial_price, language_count, platform_count, dev_track_record vs tier.  \n"
           "Gorme hedefi: bu degiskenler tier'lari ayiriyor mu?"),
        code(BOXPLOT),
        md("## 4. Top Tag — Tier Iliskisi"),
        code(TAGS),
        md("## 5. Developer Track Record Dagilimi"),
        code(TRACK_REC),
        md("## 6. Final Tablo Ozeti"),
        code(SUMMARY),
        md("## Asama 2 Notlari\n\n"
           "- **Sinif dengesizligi**: `saglam` ~%67. Stratified split + class_weight=balanced "
           "ya da SMOTE onerilir.\n"
           "- **flop sinifi bos**: SteamSpy veri 50k altini kapsamiyor. "
           "4-sinif sisteme gecilebilir (flop'u dusur).\n"
           "- **dev_track_record**: ~%35 kapsama — `has_track_record` bayragi modele feature olmali.\n"
           "- **Encoding**: genre + release_season kategorik → one-hot ya da LightGBM native cat.\n"
           "- **Metrik**: Macro-F1 (accuracy aldatici). Ek: confusion matrix + SHAP."),
    ],
}

out = Path("notebooks/ml_eda.ipynb")
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("Yazildi:", out)
