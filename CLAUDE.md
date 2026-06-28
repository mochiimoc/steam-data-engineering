CLAUDE.md — Steam Veri Platformu

Bu dosya projenin bağlamı. Kod yazmadan önce buradaki kararlara ve kurallara uy. Mimari/şema kararları kesinleşmiştir, kendi başına değiştirme — değişiklik gerekiyorsa önce söyle.

Proje nedir

Geniş bir Steam oyun verisini bir kez çekip temizleyip warehouse'a oturtan bir batch data pipeline. Aynı gold katmanı üç ürünü besler:


Higher/Lower oyunu — iki oyun göster, hangisi daha çok sattı (=yüksek owners) tahmin et.
Analiz/keşif paneli — hidden gems, fiyat trendi, tarihi dip, developer kalitesi.
ML satış-tahmini — oyun parametreleri girilince satış tier'ı tahmin eder (asıl vitrin).


Üç ayrı proje değil — bir omurganın üç ucu. Domain: Steam oyunları geneli (cozy zorunlu filtre değil).

Stack

Python (requests, pandas, pyarrow) · DuckDB (warehouse) · dbt-duckdb (modelleme) · Airflow (Docker Compose, orchestration) · Metabase/Streamlit (serving). Local + ücretsiz, AWS yok. Windows + venv.

Repo yapısı

data/{bronze,silver,gold}/   # gitignore'da (commit etme)
ingestion/                   # Python çekme/temizleme scriptleri
dbt_steam/                   # dbt projesi (star schema)
dags/                        # Airflow DAG'ları
serving/                     # oyun + panel + ML arayüzleri
notebooks/                   # keşif

Mimari (medallion)

SteamSpy + Store (+ops. ITAD) → bronze (ham JSON, data/bronze/YYYY-MM-DD/) → silver (temiz Parquet) → gold (DuckDB star schema + view) → serving. Airflow günlük tetikler.

Tek-patron-kaynak kuralı (çakışmayı kes)

AlanKaynakprice, discount, initial_priceStore (price_overview)owners (aralık), positive, negative, tags+votesSteamSpygenre, release_date, platforms, metacriticStorelanguages (→ sayıya)SteamSpy

Star schema


fact_game_snapshot (grain: oyun+gün) — game_id, date_id, price, discount_pct, initial_price, owners_low, owners_high, positive, negative
dim_game — game_id(PK), appid, name, release_date, type, required_age, is_free, language_count, platform_count, genre, developer_id(FK)
dim_developer — developer_id, developer_name, publisher_name
dim_tag — tag_id, tag_name · bridge_game_tag — game_id, tag_id, votes
dim_date — date_id, year, month, day, week, season


Güncelleme mantığı (KRİTİK)


fact = append-only / incremental. Her gün aynı oyunun YENİ satırı eklenir, eski ezilmez (geçmiş = trend + tarihi dip). dbt materialized='incremental', unique_key=(game_id, date_id) → aynı gün iki kez çalışınca mükerrer satır OLMASIN.
dim'ler = upsert. Yeni varlık gelince ekle, varsa dokunma.
Snapshot stratejisi: günlük snapshot → dar takip listesi; tüm katalog → haftalık tazeleme.


ML spec


Tip: sınıflandırma (regresyon değil). Target = sales_tier (owners orta değerinden): flop <20k / niş 20–100k / sağlam 100k–500k / hit 500k–2M / blockbuster 2M+.
Birim: bir oyun = bir satır (snapshot geçmişi tek satıra indirilir; target = en güncel tier).
Ana feature'lar (çıkış-öncesi karar değişkenleri): initial_price (launch, indirimsiz), genre, top-N tag multi-hot (N≈30-50), release_season, language_count, platform_count, developer_track_record (o developer'ın bu oyundan ÖNCE çıkmış oyunlarının ort. tier'ı).
⚠ Leakage muhafızı: developer_track_record SADECE hedef oyunun çıkışından önceki oyunları saymalı. Tüm geçmişi katma — geleceği sızdırır.
Ana girdiden ÇIKAR (satışın kopyası → opsiyonel sandbox): review_count, positive_ratio, ccu, metacritic, owners.
Model: ağaç tabanlı (RandomForest/XGBoost) + SHAP. Çıktı = tier + güven, kesin sayı değil.


Kurallar / tuzaklar


Commit etme: venv/, data/, *.duckdb, .env. API key varsa .env'e koy, koda yazma.
Fiyat kuruş cinsinden gelir (final: 1499 = $14.99) → 100'e böl.
Tek para birimi: cc=us (USD). TL'yi sadece arayüzde göster.
owners aralık gelir ("20,000,000 .. 50,000,000") → low/high'a parse et.
success: false appid'leri atla (DLC/demo/bölge kilidi, oyun değil).
Rate limit: istekler arası time.sleep (yoksa ban).
ALMA (şişirir, analize yaramaz): detailed_description, about_the_game, screenshots, movies, görseller, *_requirements.
CCU ana feature değil.


Prensip

Warehouse zengin, ML tablosu yalın. Ham veride hiçbir şey kaybetme (köprü + votes + snapshot geçmişi); ML'e girerken sadeleştir (top-N multi-hot, tek satır, çıkış-öncesi feature).

Durum


✅ Faz 0 (ortam, venv, GitHub repo) · ✅ Faz 1 bronze (veri çekiliyor, tarihli ham JSON yazılıyor)
⏭ Sıra: Faz 2 — silver (bronze JSON → temiz Parquet; owners parse, fiyat/100, positive_ratio, lineage ingested_at/processed_at).


Çalışma tarzı

Proje sahibi yön/karar tarafını ayrı yürütüyor; burada implementasyon bekleniyor. Mimari/şema kararlarını değiştirmeden uygula; bir şey belirsizse veya bir karara takılırsan kod yazmadan önce sor.