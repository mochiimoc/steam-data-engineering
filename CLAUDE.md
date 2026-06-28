CLAUDE.md — Steam Veri Platformu

Bu dosya projenin bağlamı. Kod yazmadan önce buradaki kararlara ve kurallara uy. Mimari/şema kararları kesinleşmiştir, kendi başına değiştirme — değişiklik gerekiyorsa önce söyle.

Proje nedir

Geniş bir Steam oyun verisini bir kez çekip temizleyip warehouse'a oturtan bir batch data pipeline. Aynı gold katmanı üç ürünü besler:


Higher/Lower oyunu — iki oyun göster, hangisi daha çok sattı (= yüksek owners) tahmin et.
Analiz/keşif paneli — hidden gems, fiyat trendi, developer kalitesi.
ML satış-tahmini — oyun parametreleri girilince satış tier'ı tahmin eder (asıl vitrin).


Üç ayrı proje değil — bir omurganın üç ucu. Domain: Steam oyunları geneli (cozy zorunlu filtre değil). Bu bir öğrenme + portföy projesi; production değil. Hedef: mimari ve mantık çalışsın, "isteyen klonlar inceler" — 7/24 ayakta servis değil.

Stack

Python (requests, pandas, pyarrow) · DuckDB (warehouse) · dbt-duckdb (modelleme) · Airflow (Docker Compose, orchestration) · Metabase/Streamlit (serving). Local + ücretsiz, AWS yok. Windows + venv + WSL2/Docker.

Repo yapısı

data/{bronze,silver,gold}/   # gitignore'da (commit etme)
ingestion/                   # Python çekme + silver.py
dbt_steam/                   # dbt projesi (star schema) — KURULDU
  models/staging/            # stg_games, stg_tags
  models/dims/               # dim_game, dim_developer, dim_tag, dim_date + schema.yml
  models/facts/              # fact_game_snapshot, bridge_game_tag + schema.yml
  models/analytics/          # hidden_gems, tag_price_summary, developer_quality
dags/                        # Airflow DAG'ları
serving/                     # oyun + panel + ML arayüzleri
notebooks/                   # keşif

Mimari (medallion)

SteamSpy + Store (+ops. ITAD) → bronze (ham JSON, data/bronze/YYYY-MM-DD/{appid}.json) → silver (temiz Parquet) → gold (DuckDB star schema + view) → serving. Airflow orkestre eder (gerçekte günlük schedule değil, manuel tetik yeterli).

Veri kaynağı kuralı (çakışmayı kes)

AlanKaynakprice, discount, initial_priceStore (price_overview); yoksa SteamSpy'a düşowners (aralık), positive, negative, tags+votesSteamSpygenre, release_date, platforms, metacriticStorelanguages (→ sayıya)SteamSpynameSteamSpy (temiz, ™'siz)developer/publisherStore dizisi, birincil (ilk) developer

⚠ Fiyat istisnası: Store price_overview yoksa (bedava/EA Play/bölge kilitli oyunlar) SteamSpy fiyatına düşülür. Hangisinden geldiği price_source kolonunda işaretlenir.

Star schema


fact_game_snapshot (grain: oyun+gün) — game_id, date_id, price, discount_pct, initial_price, owners_low, owners_high, positive, negative
dim_game — game_id(PK), appid, name, release_date, type, required_age, is_free, language_count, platform_count, genre, developer_id(FK)
dim_developer — developer_id, developer_name, publisher_name
dim_tag — tag_id, tag_name · bridge_game_tag — game_id, tag_id, votes
dim_date — date_id, year, month, day, week, season


Surrogate key'ler (developer_id, tag_id, date_id) dbt'de dbt_utils.generate_surrogate_key ile üretilir; fact/dim_game isimleri join'leyerek ID'ye bağlar. date_id = yyyymmdd formatı.

Güncelleme mantığı


fact = incremental. materialized='incremental', unique_key=(game_id, date_id) → her gün aynı oyunun yeni satırı eklenir, aynı gün iki kez çalışınca mükerrer OLMAZ. (Tek snapshot çekildiyse oyun başına tek satır olur, sorun değil.)
dim'ler = tek satıra indirilmiş tablolar. Silver çok-günlü satır içerir → qualify row_number() over (partition by <key> order by snapshot_date desc) = 1 ile en güncel snapshot'a daraltılır. dim_tag = distinct tag_name. dim_developer = isimden dedupe.
bridge = oyun+tag başına tek satır, votes en güncel snapshot'tan.


Silver detayları (silver.py — KURULDU)

data/bronze/YYYY-MM-DD/ okur, iki parquet yazar: games_*.parquet (oyun başına 1 satır) + game_tags_*.parquet (uzun: game_id, tag_name, votes). snapshot_date klasör adından gelir. encoding="utf-8-sig". Eler: success:false, type!="game" (dlc/demo/soundtrack), coming_soon:true. Türetir: owners parse (low/high), fiyat/100 + fallback, positive_ratio, language_count, platform_count, lineage (ingested_at = fetched_at, processed_at = now).

Gold detayları (dbt_steam — KURULDU)

11 model + 22 data testi (dbt run + dbt test yeşil). Staging silver parquet'leri glob'la birleştirir (read_parquet('...*.parquet', union_by_name=true)). Testler: unique/not_null (PK'lar), relationships (FK bütünlüğü), accepted_values (type), unique_combination (bridge).

ML spec (Faz 4 — SIRADA, asıl vitrin)


Tip: sınıflandırma (regresyon değil). Target = sales_tier (owners orta değerinden): flop <20k / niş 20–100k / sağlam 100k–500k / hit 500k–2M / blockbuster 2M+.
Birim: bir oyun = bir satır (snapshot geçmişi tek satıra inilir; target = en güncel tier).
Ana feature'lar (çıkış-öncesi karar değişkenleri): initial_price (launch, indirimsiz), genre, top-N tag multi-hot (N≈30-50), release_season, language_count, platform_count, developer_track_record (o developer'ın bu oyundan ÖNCE çıkmış oyunlarının ort. tier'ı).
⚠ Leakage muhafızı: developer_track_record SADECE hedef oyunun çıkışından önceki oyunları saymalı. Tüm geçmişi katma — geleceği sızdırır.
⚠ Ana girdiden ÇIKAR (satışın kopyası → opsiyonel sandbox): owners, review_count, positive_ratio, ccu, metacritic. Bunlar feature olursa model sahte yüksek accuracy verir.
Model: ağaç tabanlı (RandomForest/XGBoost) + SHAP. Çıktı = tier + güven, kesin sayı değil.
Feature tablosu Python script'inde üretilecek (gold DuckDB'den oku → pandas'ta multi-hot + leakage guard). Multi-hot ve track_record SQL'de çetrefil; Python daha uygun.


Kurallar / tuzaklar


Commit etme: venv/, data/, *.duckdb, .env. API key varsa .env'e, koda yazma.
Fiyat kuruş cinsinden gelir (1499 = $14.99) → 100'e böl. Tek para birimi cc=us (USD); TL sadece arayüzde.
owners aralık gelir ("20,000,000 .. 50,000,000") → low/high'a parse et.
success:false appid'leri atla (DLC/demo/bölge kilidi).
Rate limit: istekler arası time.sleep (yoksa ban).
ALMA (şişirir, analize yaramaz): detailed_description, about_the_game, screenshots, movies, görseller, *_requirements, achievements, categories, ratings.
CCU ana feature değil.


Prensip

Warehouse zengin, ML tablosu yalın. Ham veride hiçbir şey kaybetme (köprü + votes + snapshot geçmişi); ML'e girerken sadeleştir (top-N multi-hot, tek satır, çıkış-öncesi feature).

Durum


✅ Faz 0 (ortam, venv, GitHub repo, Docker/WSL2)
✅ Faz 1 bronze (~10k oyun, tarihli ham JSON)
✅ Faz 2 silver (silver.py → temiz Parquet)
✅ Faz 3 gold (dbt star schema + view'ler, 22/22 test yeşil, fact incremental)
⏭ Sıra: Faz 4 — ML feature tablosu + model (Python; leakage guard + satış-kopyası kolonları çıkar)


Çalışma tarzı

Proje sahibi yön/karar tarafını ayrı yürütüyor. Mimari/şema kararlarını değiştirmeden uygula; bir şey belirsizse veya bir karara takılırsan kod yazmadan önce sor. Sade tut — bu bir öğrenme projesi, fazla mühendislik gerekmez.