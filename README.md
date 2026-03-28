# Eagle API — Birlesik Futbol Tahmin Motoru

7 kaynak, Poisson dagılımı, odds hareketi analizi ve seri tespiti ile futbol tahmin motoru.

Bee (football-analysis-api) fork'u uzerine gelistirildi. Falcon ve Predator algoritmalarının en iyi ozellikleri Bee'nin analiz pipeline'ına entegre edildi.

## Sunucu Bilgileri

| Bilgi | Deger |
|-------|-------|
| Sunucu | AWAXX (147.93.94.92) |
| Port | 8098 |
| Servis | `systemctl start/stop/restart eagle-api` |
| Dizin | `/root/eagle-api` |
| Python | 3.12+ |
| Framework | Flask + Gunicorn (gevent) |
| Cache | Redis DB 5 |
| GitHub | https://github.com/YDX64/eagle-api |

## Guncelleme (GitHub Sync)

```bash
# Tek komut — GitHub'dan cekip restart eder:
bash /root/eagle-api/update.sh

# Manuel adımlar:
cd /root/eagle-api
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --quiet
systemctl restart eagle-api
```

## Ilk Kurulum (Sifirdan)

```bash
cd /root
git clone https://github.com/YDX64/eagle-api.git
cd eagle-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p logs data

# .env olustur (asagidaki ornege bak)
cp .env.example .env
nano .env

# Systemd servisi kur
cat > /etc/systemd/system/eagle-api.service << 'EOF'
[Unit]
Description=Eagle API - Unified Football Prediction Engine
After=network.target redis.service

[Service]
Type=forking
User=root
WorkingDirectory=/root/eagle-api
Environment=FLASK_ENV=production
ExecStart=/root/eagle-api/venv/bin/gunicorn -w 2 -k gevent --bind 0.0.0.0:8098 --timeout 120 --daemon --pid /root/eagle-api/gunicorn.pid app:app
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/bin/kill -TERM $MAINPID
PIDFile=/root/eagle-api/gunicorn.pid
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable eagle-api
systemctl start eagle-api

# Kontrol
curl http://127.0.0.1:8098/api/v1/health
```

## Ortam Degiskenleri (.env)

```bash
FLASK_ENV=production
SECRET_KEY=<random-secret>
API_SECRET_KEY=<api-key>
JWT_SECRET_KEY=<jwt-key>

# Cache
CACHE_TYPE=redis
CACHE_REDIS_HOST=localhost
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=5

# Data Sources
PRIMARY_DATA_SOURCE=https://www.nowgoal.com
FALLBACK_DATA_SOURCES=https://live5.nowgoal26.com,https://www.goaloo.com
LEAGUE_DATA_SOURCE=https://football.nowgoal26.com

# Eagle: Dis API Baglantilari
EAGLE_FALCON_URL=http://127.0.0.1:8092
EAGLE_PREDATOR_URL=http://127.0.0.1:8090
EAGLE_FALCON_KEY=<falcon-api-key>
EAGLE_PREDATOR_KEY=<predator-api-key>
EAGLE_FALCON_TIMEOUT=45
EAGLE_PREDATOR_TIMEOUT=30
EAGLE_FALCON_CONCURRENT=3
EAGLE_FALCON_DELAY=0.3
EAGLE_MATCH_THRESHOLD=0.80

# Opsiyonel: Predator V2
EAGLE_PREDATOR_V2_URL=
EAGLE_PREDATOR_V2_KEY=
```

## 7 Tahmin Kaynagi

| # | Kaynak | Modul | Aciklama |
|---|--------|-------|----------|
| 1 | **H2H Analysis** | `analysis/h2h.py` | Gecmis karsilasma istatistikleri |
| 2 | **Team Performance** | `analysis/team_performance.py` | Son 20 mac performans metrikleri |
| 3 | **Correct Score** | `analysis/correct_score.py` | Skor oranlarından turetilmis olasıliklar |
| 4 | **Odds Analysis** | `analysis/odds_analysis.py` | Bahis oranlarından piyasa yuzdesi |
| 5 | **Poisson Model** | `analysis/poisson_model.py` | **YENi** — Matematiksel gol dagılımı |
| 6 | **Odds Movement** | `analysis/odds_movement.py` | **YENi** — Acılıs→kapanıs hareket sinyalleri |
| 7 | **Streak Detector** | `analysis/streak_detector.py` | **YENi** — Seri/trend tespiti |

### Kaynak 5: Poisson Model (YENi)

Poisson dagılımı ile gol olasılıkları hesaplar:

```
P(X=k) = (lambda^k * e^(-lambda)) / k!

home_lambda = (home_attack / league_avg) * (away_defense / league_avg) * league_avg
away_lambda = (away_attack / league_avg) * (home_defense / league_avg) * league_avg

P(Over 2.5)  = 1 - SUM[P(h)*P(a)] for h+a < 3
P(BTTS)      = 1 - P(h=0) - P(a=0) + P(h=0,a=0)
P(Home Win)  = SUM[P(h)*P(a)] for h > a
```

**Cikarir**: 1x2, Over/Under (1.5, 2.5, 3.5), BTTS, HT 1x2, HT Goals, Expected Goals (xG)

### Kaynak 6: Odds Movement (YENi)

Bahiscilerin acılıs→kapanıs oran degisikliklerinden sinyal cikarir:

- **Goal Line hareketi**: Kac bahisci goal line'ı yukseltti/dusurdu → Over/Under sinyali
- **Asian Handicap hareketi**: AH hangi yone kaydi → MS sinyali
- **1x2 oran dususleri**: Hangi tarafin oranı en cok dustu → Para akisi sinyali
- **HT oranları**: Ilk yarı icin ayni analiz

### Kaynak 7: Streak Detector (YENi)

Son 10 macta tekrarlayan oruntuleri tespit eder:

| Seri | Esik | Ornek |
|------|------|-------|
| Over 2.5 | ≥%80 | Her iki takımın son 10 macının 8+'ında 3+ gol |
| BTTS | ≥%75 | Her iki takım son 10 macın 7.5+'ında gol atmis |
| HT Gol | ≥%80 | Son 10 macın 8+'ında ilk yarı gol var |
| MS Home | ≥%70 WR | Ev sahibi son 10'da 7+ galibiyet |
| H2H Over | ≥%80 | Kafa kafaya son 10'da 8+ mac over |

## Final Predictions Agirliklari

### 1x2 (Mac Sonucu) — 7 kaynak

| Kaynak | Agirlik |
|--------|---------|
| Team Performance | %25 |
| Odds Analysis | %25 |
| H2H | %20 |
| Correct Score | %10 |
| **Poisson** | **%15** |
| **Odds Movement** | **%10** |
| **Streaks** | **%5** |

### Goal Lines (Over/Under) — 6 kaynak

| Kaynak | Agirlik |
|--------|---------|
| Team Performance | %30 |
| H2H | %20 |
| Correct Score | %15 |
| **Poisson** | **%20** |
| **Odds Movement** | **%15** |
| **Streaks** | **%5** |

### BTTS (Karsilikli Gol) — 5 kaynak

| Kaynak | Agirlik |
|--------|---------|
| Team Performance | %30 |
| H2H | %25 |
| Correct Score | %15 |
| **Poisson** | **%20** |
| **Streaks** | **%5** |

### HT (Ilk Yari) — 4 kaynak

| Kaynak | Agirlik |
|--------|---------|
| Team Performance | %40 |
| H2H | %30 |
| **Poisson HT** | **%15** |
| **Odds Movement HT** | **%10** |

> Agirliklar dinamik normalize edilir. Bir kaynak veri saglayamazsa agirligi diger kaynaklara dagitilir.

## API Endpointleri

### Mac Verileri (Bee uyumlu)

| Endpoint | Metod | Aciklama |
|----------|-------|----------|
| `/api/v1/match/{id}` | GET | Mac detaylari + Eagle analizi |
| `/api/v1/match/{id}/h2h` | GET | H2H verileri |
| `/api/v1/match/{id}/odds` | GET | Oran analizi |
| `/api/v1/matches/today` | GET | Bugunun maclari |
| `/api/v1/matches/date/{date}` | GET | Tarihe gore maclar |
| `/api/v1/matches/live` | GET | Canli maclar |
| `/api/v1/matches/live/{id}` | GET | Canli mac detayi |

### Eagle Spesifik

| Endpoint | Metod | Aciklama |
|----------|-------|----------|
| `/api/v1/eagle/match/{id}` | GET | Eagle birlesik tahmin (4 kaynak) |
| `/api/v1/eagle/matches/{date}` | GET | Tarih bazli Eagle tahminleri |
| `/api/v1/eagle/best/{date}` | GET | En iyi tahminler (filtre) |
| `/api/v1/eagle/banko/{date}` | GET | BANKO tahminler |
| `/api/v1/eagle/status` | GET | Motor durumu ve kaynak bilgisi |

### Saglik & Izleme

| Endpoint | Metod | Aciklama |
|----------|-------|----------|
| `/api/v1/health` | GET | Saglik kontrolu |
| `/api/v1/health/detailed` | GET | Detayli saglik |
| `/api/v1/cache/stats` | GET | Cache istatistikleri |
| `/api/v1/sources/health` | GET | Veri kaynagi sagligi |

## Mimari

```
Eagle API (Port 8098)
├── Flask App + Gunicorn/gevent
├── Routes
│   ├── matches.py ............. Mac listesi + detay
│   ├── live.py ................ Canli maclar
│   ├── eagle.py ............... Eagle birlesik tahmin endpoint'leri
│   ├── leagues.py ............. Lig verileri
│   └── health.py .............. Saglik kontrolleri
├── Analysis Pipeline (7 kaynak, paralel)
│   ├── h2h.py ................. H2H istatistikleri
│   ├── team_performance.py .... Takim performans metrikleri
│   ├── correct_score.py ....... Skor oranları turevi
│   ├── odds_analysis.py ....... Piyasa oran analizi
│   ├── poisson_model.py ....... [EAGLE] Poisson gol modeli
│   ├── odds_movement.py ....... [EAGLE] Oran hareketi sinyalleri
│   ├── streak_detector.py ..... [EAGLE] Seri/trend tespiti
│   └── final_predictions.py ... 7 kaynagi birlestirir
├── Eagle Module (dis API entegrasyonu)
│   ├── config.py .............. Falcon/Predator URL ve agirliklar
│   ├── collector.py ........... Falcon/Predator veri cekme
│   └── combiner.py ............ Ensemble birlestirme stratejisi
├── Infra
│   ├── http_client.py ......... Multi-source failover HTTP client
│   ├── cache_utils.py ......... Redis + stale-while-revalidate
│   ├── source_manager.py ...... Veri kaynagi saglik takibi
│   └── security.py ............ Auth + rate limiting
└── External APIs
    ├── Falcon (127.0.0.1:8092) ... AI tahmin motoru
    └── Predator (127.0.0.1:8090) . Istatistiksel analiz
```

## Loglama

```bash
# Uygulama loglari
tail -f /root/eagle-api/logs/app.log

# Gunicorn loglari
tail -f /root/eagle-api/logs/gunicorn_error.log
tail -f /root/eagle-api/logs/gunicorn_access.log

# Systemd loglari
journalctl -u eagle-api -f
```

## Sorun Giderme

### API yanit vermiyor
```bash
systemctl status eagle-api
journalctl -u eagle-api -n 50
# Restart
systemctl restart eagle-api
```

### Redis cache temizleme
```bash
redis-cli -n 5 FLUSHDB
```

### Poisson/Odds Movement calismiyor
Analiz ciktisinda `_eagle_sources` alanini kontrol et:
```bash
curl -s -H "X-API-Key: <key>" http://127.0.0.1:8098/api/v1/match/2922237 \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['data']['analysis']['final_predictions']['_eagle_sources']; print(json.dumps(d, indent=2))"
```

### Falcon/Predator baglantisi
```bash
curl -s -H "X-API-Key: <key>" http://127.0.0.1:8098/api/v1/eagle/status \
  | python3 -m json.tool
```

## Lisans

Ozel yazilim — AWA Stats
