# Steam Veri Platformu

Steam oyun verisini çekip temizleyip warehouse'a oturtarak üç ürünü (Higher/Lower oyunu, pazar analiz paneli, ML satış tahmin arayüzü) besleyen uçtan uca batch data pipeline. İlk DE projesi — mimari ve dürüst metodolojiyi göstermek amacıyla yapıldı.

---

## Mimari

```
SteamSpy API  ──┐
Steam Store API ─┤──► Bronze ──► Silver ──► Gold ──► Serving
                │   (ham JSON) (Parquet) (DuckDB)  (Streamlit)
```

**Medallion katmanları:**

| Katman | Format | İçerik |
|--------|--------|--------|
| Bronze | `data/bronze/YYYY-MM-DD/{appid}.json` | SteamSpy + Store API ham yanıtları, tarihlendirilmiş |
| Silver | `data/silver/games_*.parquet` + `game_tags_*.parquet` | Temizlenmiş, filtrelenmiş (DLC/demo/coming-soon çıkarıldı), normalize edilmiş |
| Gold | DuckDB star schema | dbt modelleri: fact + dim + bridge + 3 analitik view |

**Gold — star schema:**

```
dim_developer ──┐
dim_date      ──┤──► fact_game_snapshot   bridge_game_tag ──► dim_tag
dim_game ───────┘    (grain: oyun+gün)    (oyun-tag ilişkisi, votes)
```

Boyutlar: `dim_game`, `dim_developer`, `dim_tag`, `dim_date`  
Fact: `fact_game_snapshot` (incremental, unique_key=game_id+date_id)  
Bridge: `bridge_game_tag` (çok-çok oyun↔tag)  
Analitik view'ler: `hidden_gems`, `tag_price_summary`, `developer_quality`

**Rakamlar (tek snapshot):** ~10k oyun · ~20k snapshot satırı · 447 benzersiz tag · 167k bridge kaydı

---

## Stack

| Araç | Kullanım |
|------|----------|
| Python (requests, pandas, pyarrow) | Ingestion + silver transform + ML |
| DuckDB | Lokal warehouse (dosya tabanlı) |
| dbt-duckdb | Gold modelleme, 22 data testi |
| Airflow (Docker Compose) | Orkestrasyon — manuel tetik, günlük otomatik çalışma yok |
| Streamlit | Üç arayüz |
| LightGBM + SHAP | ML model + açıklanabilirlik |

**Neden local + ücretsiz?** AWS/Snowflake yerine lokal araçlar bilinçli tercih: maliyet sıfır, bağımlılık yok, mimari kavramlar (medallion, star schema, incremental model) aynı. Portföy için "mimarinin nasıl düşünüldüğü" önemli, infra büyüklüğü değil.

---

## Üç Ürün

### 1. Higher/Lower Oyunu
`serving/higher_lower.py`

İki Steam oyunu göster, hangisi daha çok sattı tahmin et. Zincir mantığı: doğru bilince rakip yeni çapa olur, yanlışta seri biter. Sahip sayısı SteamSpy bant ortasından gösterilir (sahte kesin sayı değil).

![Higher/Lower ekran görüntüsü](docs/higher_lower.png)

### 2. Pazar Anlık Görünümü Paneli
`serving/market_snapshot.py`

~10k oyunun cross-sectional analizi: fiyat dağılımı, fiyat↔kalite, hidden gems, tag analizi, developer kalitesi, yıllara göre çıkan oyun sayısı.

![Pazar paneli ekran görüntüsü](docs/market_snapshot.png)

### 3. ML Satış Tier Tahmini
`serving/ml_app.py`

Oyun parametrelerini gir → LightGBM modeli satış tier'ı tahmin eder (niş / sağlam / hit / blockbuster) + SHAP ile bu tahmin için hangi feature'ın ne kadar katkısı olduğunu gösterir.

![ML arayüzü ekran görüntüsü](docs/ml_app.png)

---

## Nasıl Çalıştırılır

### Gereksinimler
- Docker Desktop (Airflow için)
- Python 3.12 + bağımlılıklar: `pip install -r requirements.txt`

### 1. Airflow'u başlat
```bash
docker compose up -d
# http://localhost:8080  (airflow / airflow)
```

### 2. Pipeline'ı tetikle (Airflow UI veya CLI)
```bash
# Airflow UI → DAGs → steam_pipeline → Trigger DAG
# ya da:
docker compose exec airflow-worker airflow dags trigger steam_pipeline
```

DAG adımları: `extract → silver_transform → dbt_run → dbt_test`

### 3. dbt'yi doğrudan çalıştır (isteğe bağlı)
```bash
cd dbt_steam
dbt run
dbt test    # 22/22 test geçmeli
```

### 4. Serving arayüzleri
```bash
# Higher/Lower oyunu
streamlit run serving/higher_lower.py        # → localhost:8501

# Pazar paneli
streamlit run serving/market_snapshot.py     # → localhost:8502

# ML tahmin arayüzü
streamlit run serving/ml_app.py              # → localhost:8503
```

### 5. ML pipeline (feature tablosu + model)
```bash
python ml/features.py    # data/ml/features.parquet üretir
python ml/train.py       # model eğitir, artifact'ları kaydeder
```

---

## Tasarım Kararları ve Dürüst Sınırlamalar

Bu bölüm projenin en önemli kısmı. Metodolojik dürüstlük portföyde teknik karmaşıklıktan daha değerli.

### Snapshot ≠ Trend

Tek bir tarihli snapshot çekildi. Panelde "fiyat 3 ayda nasıl değişti" gibi zaman-serisi soruları yanıtsız — veri yok, uydurulmadı. Panel adı bilinçli olarak "Pazar **Anlık** Görünümü". Tek meşru zaman ekseni oyunların `release_date`'i (çıkış yılına göre oyun sayısı ve medyan fiyat — bu zaten veride var).

### owners Belirsizliği

SteamSpy `owners` aralık olarak gelir (`"100,000 .. 200,000"`). Kesin sayı bilinmiyor. Tüm hesaplamalarda bant ortası `(owners_low + owners_high) / 2` kullanıldı; grafik eksenlerinde "tahmini sahip (bant ortası)" yazıldı. Tek bir kesin rakam varmış gibi sunulmadı.

### ML — Leakage Temizliği

Modelin senaryosu: **"oyun daha çıkmadan ne kadar satar?"** Bu yüzden yalnızca çıkış-öncesi bilinen feature'lar kullanıldı.

**Ana girdiden çıkarılanlar (satışın kopyası):**  
`owners`, `positive`, `negative`, `positive_ratio`, `review_count`, `ccu`, `metacritic` — bunlar satışla birlikte oluşan değerler, tahmin feature'ı olamaz.

**`developer_track_record` leakage guard:**  
Her oyun için, o oyunun release_date'inden **önce** çıkmış aynı developer oyunlarının ortalama tier'ı hesaplandı. Tüm geçmiş değil, sadece `< release_date` — geleceği sızdırmamak için.

**`language_count` çıkarıldı (sonradan fark edilen leakage şüphesi):**  
İlk modelde en güçlü feature'dı (SHAP ~0.49). Sonra anlaşıldı: bir oyun başarılı olduktan **sonra** çok dile çevriliyor, ya da büyük publisher'lar kaynakları önceden bildiği için çevirdi — saf çıkış-öncesi sinyal değil. Çıkarıldı, dürüst model buna göre raporlandı.

### Sınıf Dengesizliği ve Boş Tier

SteamSpy ~50k altındaki oyunları döndürmüyor → veri setinde "flop" tier'ı (< 20k sahip) **sıfır oyun**. Model 4 sınıfla eğitildi. Sınıf dengesizliği nedeniyle accuracy yerine **macro-F1** kullanıldı.

---

## Model Sonuçları

**5-fold stratified CV (macro-F1):**

| Model | Val Macro-F1 | ± |
|-------|-------------|---|
| v1 LightGBM (language_count **var**) | 0.405 | — |
| RF baseline | 0.297 | 0.008 |
| **LightGBM reg (language_count yok)** | **0.381** | 0.015 |
| Voting (RF + LightGBM) | 0.378 | 0.014 |
| Stacking | 0.297 | 0.009 |

v1 → v2 düşüşü (0.405 → 0.381): leakage şüpheli feature çıkarılınca beklenen sonuç. Dürüst skor bu.

**SHAP — v2 top feature'lar:**  
`tag_Multiplayer` · `initial_price` · `dev_track_record` · `platform_count` · `tag_Singleplayer` · `tag_Co-op`

Multiplayer/co-op tag'larının yüksek önemi verinin yapısını yansıtıyor: sosyal oyunlar daha geniş kitleye ulaşıyor.

---

## Klasör Yapısı

```
steamdataengineer/
├── ingestion/          # SteamSpy + Store API istemcisi, ham veri çekme
├── transform/          # silver.py — bronze → temiz Parquet
├── dbt_steam/          # Gold modelleme (11 model, 22 test)
│   └── models/
│       ├── staging/    # stg_games, stg_tags
│       ├── dims/       # dim_game, dim_developer, dim_tag, dim_date
│       ├── facts/      # fact_game_snapshot, bridge_game_tag
│       └── analytics/  # hidden_gems, tag_price_summary, developer_quality
├── dags/               # Airflow DAG (steam_pipeline)
├── ml/                 # Feature engineering + LightGBM eğitimi
│   ├── features.py     # Gold → features.parquet (leakage-safe)
│   └── train.py        # 4-model kıyas, SHAP, artifact kaydetme
├── serving/            # Streamlit arayüzleri
│   ├── higher_lower.py
│   ├── market_snapshot.py
│   └── ml_app.py
├── notebooks/          # Keşif (ml_eda.ipynb)
├── data/               # gitignore'da (bronze/silver/gold/ml)
└── docker-compose.yml  # Airflow
```

---

## İngilizce Özet

End-to-end batch data pipeline pulling ~10k Steam games from SteamSpy and Steam Store APIs through a medallion architecture (bronze JSON → silver Parquet → gold DuckDB star schema via dbt) into three Streamlit apps: a Higher/Lower guessing game, a market snapshot dashboard, and an ML sales-tier classifier (LightGBM + SHAP). Built local and free (DuckDB, Docker, no cloud). Key methodological choices: single snapshot reported honestly (no fake trends), SteamSpy band uncertainty surfaced in UI, strict leakage prevention in ML features (no post-launch signals; `language_count` dropped after SHAP revealed it as a success proxy). Val Macro-F1: 0.38 on 4-class tier prediction — low but honest.
