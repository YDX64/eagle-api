# Golsinyali API - Canlı Maç Endpoint'leri Dokümantasyonu

Bu dokümantasyon, Golsinyali API'nin tüm canlı maç endpoint'lerini, gerçek zamanlı veri kaynaklarını, istek/yanıt yapılarını ve cache stratejilerini detaylı şekilde açıklamaktadır.

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Dış API Veri Kaynakları](#2-dış-api-veri-kaynakları)
3. [Canlı Maç Endpoint'leri](#3-canlı-maç-endpointleri)
4. [Veri Yapıları ve Mapping'ler](#4-veri-yapıları-ve-mappingler)
5. [Örnek Dış API URL'leri](#5-örnek-dış-api-urlleri)
6. [Hata Kodları](#6-hata-kodları)
7. [Cache Stratejisi](#7-cache-stratejisi)
8. [Parser Detayları](#8-parser-detayları)

---

## 1. Genel Bakış

### Mimari Akış

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT REQUEST                                    │
│                       GET /api/v1/matches/live                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLASK ROUTE HANDLER                                  │
│                            routes/live.py                                    │
│                                                                              │
│  1. Query parametrelerini parse et (include_stats, include_odds, etc.)      │
│  2. Cache key oluştur: "live_all_true_true_false"                           │
│  3. In-memory cache kontrol et (30 saniye TTL)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
            [CACHE HIT]                      [CACHE MISS]
                    │                               │
                    ▼                               ▼
┌──────────────────────────┐    ┌────────────────────────────────────────────┐
│   Return cached data     │    │       PARALLEL FETCH FROM EXTERNAL APIs     │
│   (Instant response)     │    │                                            │
└──────────────────────────┘    │  ThreadPoolExecutor ile paralel fetch:     │
                                │  ┌────────────────────────────────────┐    │
                                │  │ Thread 1: bf_en-idn.js (matches)   │    │
                                │  │ Thread 2: detail.js (stats+events) │    │
                                │  │ Thread 3: runOddsData_8.txt (odds) │    │
                                │  │ Thread 4: sbCorner.js (corners)    │    │
                                │  └────────────────────────────────────┘    │
                                └────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL DATA SOURCES                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ https://live3.nowgoal26.com/gf/data/bf_en-idn.js                    │   │
│  │ Canlı maç listesi, skorlar, takım bilgileri                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ https://live3.nowgoal26.com/gf/data/detail.js                       │   │
│  │ Teknik istatistikler (şut, korner, pas, vb.) + maç olayları         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ https://live3.nowgoal26.com/gf/data/odds/en/runOddsData_8.txt       │   │
│  │ Bet365 canlı oranları (Asya Handikap, 1X2, Alt/Üst, vb.)           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ https://live3.nowgoal26.com/gf/data/sbCorner.js                     │   │
│  │ Korner istatistikleri ve korner oranları                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PARSER LAYER                                       │
│                         live_parsers.py                                      │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LiveMatchParser    → A[], B[], C[] dizilerini parse eder            │   │
│  │ LiveStatsParser    → tc[] dizisini parse eder (teknik istatistikler)│   │
│  │ LiveEventsParser   → rq[] dizisini parse eder (maç olayları)        │   │
│  │ LiveOddsParser     → !-separated text'i parse eder (oranlar)        │   │
│  │ CornerStatsParser  → sCornerData[] dizisini parse eder              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  LiveDataParser.enrich_matches_with_stats():                                │
│    - Maçları stats, odds, corners ile zenginleştirir                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JSON RESPONSE                                        │
│                                                                              │
│  {                                                                           │
│    "success": true,                                                         │
│    "data": {                                                                │
│      "matches": [...],                                                      │
│      "meta": { "total_matches": 76, "live_count": 12 }                     │
│    },                                                                       │
│    "timestamp": "2024-12-27T10:30:00.000Z"                                 │
│  }                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Canlı Veri Akışı Özellikleri

| Özellik | Değer |
|---------|-------|
| Güncelleme Sıklığı | Her 30 saniyede bir (kaynak) |
| Cache TTL | 30 saniye (maçlar, stats, corners) |
| Odds Cache TTL | 15 saniye (oranlar daha sık değişir) |
| Paralel Fetch | 4 thread (matches, stats, odds, corners) |
| Timeout | 15 saniye (paralel fetch toplamı) |

---

## 2. Dış API Veri Kaynakları

### 2.1 Endpoint Listesi

| Endpoint Key | URL | İçerik | Format |
|--------------|-----|--------|--------|
| `matches` | `/gf/data/bf_en-idn.js` | Canlı maç listesi | JavaScript (A[], B[], C[]) |
| `stats` | `/gf/data/detail.js` | Teknik istatistikler + olaylar | JavaScript (tc[], rq[]) |
| `odds` | `/gf/data/odds/en/runOddsData_8.txt` | Bet365 canlı oranları | Text (! ve $ separated) |
| `corners` | `/gf/data/sbCorner.js` | Korner istatistikleri | JavaScript (sCornerData[]) |
| `changes` | `/gf/data/change_en.xml` | Gerçek zamanlı skor değişiklikleri | XML |

### 2.2 Base URL Konfigürasyonu

```python
# config.py'den
PRIMARY_DATA_SOURCE = "https://live3.nowgoal26.com"

# Dinamik endpoint oluşturma (live_utils.py)
def get_live_endpoints():
    base_url = current_config.PRIMARY_DATA_SOURCE.rstrip('/')
    return {
        'matches': f'{base_url}/gf/data/bf_en-idn.js',
        'stats': f'{base_url}/gf/data/detail.js',
        'odds': f'{base_url}/gf/data/odds/en/runOddsData_8.txt',
        'corners': f'{base_url}/gf/data/sbCorner.js',
        'changes': f'{base_url}/gf/data/change_en.xml',
    }
```

---

## 3. Canlı Maç Endpoint'leri

### 3.1 GET /api/v1/matches/live

**Açıklama:** Tüm canlı maçları gerçek zamanlı istatistikler ve oranlarla birlikte getirir.

#### Request

```http
GET /api/v1/matches/live HTTP/1.1
Host: localhost:8000

# Tüm seçeneklerle:
GET /api/v1/matches/live?include_stats=true&include_odds=true&include_corners=true&only_live=true&league_id=36
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `include_stats` | boolean | Hayır | `true` | Teknik istatistikleri dahil et |
| `include_odds` | boolean | Hayır | `true` | Canlı oranları dahil et |
| `include_corners` | boolean | Hayır | `false` | Korner istatistiklerini dahil et |
| `league_id` | integer | Hayır | - | Lig ID'sine göre filtrele |
| `only_live` | boolean | Hayır | `false` | Sadece devam eden maçları getir |

#### Dış API İstekleri (Paralel)

**1. Maç Listesi (bf_en-idn.js):**
```
URL: https://live3.nowgoal26.com/gf/data/bf_en-idn.js
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: */*
```

**2. Teknik İstatistikler (detail.js):**
```
URL: https://live3.nowgoal26.com/gf/data/detail.js
Method: GET
```

**3. Canlı Oranlar (runOddsData_8.txt):**
```
URL: https://live3.nowgoal26.com/gf/data/odds/en/runOddsData_8.txt
Method: GET
```

**4. Korner İstatistikleri (sbCorner.js):** (opsiyonel)
```
URL: https://live3.nowgoal26.com/gf/data/sbCorner.js
Method: GET
```

#### Dış API Ham Response - bf_en-idn.js

```javascript
lastCreateTime_bfIndex="2024-12-27 15:30:00";
var matchcount=76;

// A[index] = Maç verisi dizisi
// Format: [match_id, league_id, home_team_id, away_team_id, 'home_team', 'away_team',
//          'match_time', 'start_time', state, home_score, away_score, ht_home, ht_away,
//          home_red, away_red, ...]

A[0]=[2882312,36,19,18,'Arsenal','Chelsea','2024-12-27 16:00','2024-12-27 16:00',3,2,1,1,0,0,0,...];
A[1]=[2882313,36,15,17,'Liverpool','Man City','2024-12-27 18:30','2024-12-27 18:30',0,0,0,0,0,0,0,...];
A[2]=[2882314,37,101,102,'Barcelona','Real Madrid','2024-12-27 21:00','2024-12-27 21:00',1,1,1,0,0,0,0,...];
// ... daha fazla maç

// B[league_id] = Lig bilgisi dizisi
// Format: [league_id, 'short_name', 'full_name', country_id]
B[36]=[36,'ENG PR','Premier League',1];
B[37]=[37,'SPA D1','La Liga',5];
B[745]=[745,'TUR D1','Super Lig',55];

// C[country_id] = Ülke bilgisi dizisi
// Format: [country_id, 'country_name']
C[1]=[1,'England'];
C[5]=[5,'Spain'];
C[55]=[55,'Turkey'];
```

#### Dış API Ham Response - detail.js

```javascript
// tc[index] = Teknik istatistikler
// Format: tc[index]="match_id^stat_id,home_val,away_val;stat_id,home_val,away_val;..."

tc[0]="2882312^3,15,12;4,6,4;5,8,10;6,7,4;14,58,42;43,45,38;44,12,8";
tc[1]="2882314^3,18,14;4,8,5;5,6,9;6,5,6;14,62,38;43,52,41;44,15,11";

// rq[index] = Maç olayları
// Format: rq[index]="match_id^is_home^event_type^minute^player_name^player_id^team_id^other"

rq[0]="2882312^1^1^23^Saka B.^12345^19^0";           // Arsenal gol, 23'
rq[1]="2882312^1^1^67^Havertz K.^12346^19^0";       // Arsenal gol, 67'
rq[2]="2882312^0^1^45^Palmer C.^12347^18^0";        // Chelsea gol, 45'
rq[3]="2882312^1^5^34^Rice D.^12348^19^0";          // Sarı kart, 34'
rq[4]="2882314^1^1^15^Lewandowski R.^23456^101^0";  // Barcelona gol, 15'
rq[5]="2882314^0^1^28^Vinicius Jr.^23457^102^0";    // Real Madrid gol, 28'
```

#### Dış API Ham Response - runOddsData_8.txt

```
match_id!AH_data!1X2_data!OU_data!BTTS_data!DC_data!HT_data$next_match...

2882312!1.02,-0.5,0.88!2.10,3.40,3.20!1.85,2.5,1.95!1.72,2.10!1.35,1.60,2.25!2.50,3.20,2.80$2882313!0.95,0.25,0.95!1.65,4.00,4.50!2.05,3.5,1.75!1.90,1.90!1.20,1.85,3.00!1.85,3.50,3.80$2882314!0.98,-0.25,0.92!2.40,3.30,2.80!1.90,2.5,1.90!1.75,2.05!1.40,1.55,2.40!2.60,3.10,2.70

Açıklama:
- match_id: Maç ID
- AH_data: home,line,away (Asya Handikap) + opening değerleri
- 1X2_data: home,draw,away (Maç Sonucu) + opening değerleri
- OU_data: over,line,under (Alt/Üst) + opening değerleri
- BTTS_data: yes,no (Karşılıklı Gol)
- DC_data: home_draw,home_away,draw_away (Çifte Şans)
- HT_data: home,draw,away (İlk Yarı Sonucu)
```

#### Dış API Ham Response - sbCorner.js

```javascript
// sCornerData[match_id] = "basic_info^odds_data^stats_data^events"

sCornerData[2882312]="^1.85,9.5,1.95,0.92,-1.5,0.98^3,2,7,4^";
sCornerData[2882314]="^1.90,10.5,1.90,0.95,-2.5,0.95^4,3,5,6^";

Açıklama (stats_data):
- home_first_half: Ev sahibi ilk yarı korner
- away_first_half: Deplasman ilk yarı korner
- home_total: Ev sahibi toplam korner
- away_total: Deplasman toplam korner

Açıklama (odds_data):
- over,line,under: Korner Alt/Üst
- home,handicap,away: Korner Handikap
```

#### Response

```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "index": 0,
        "match_id": 2882312,
        "league_id": 36,
        "home_team_id": 19,
        "away_team_id": 18,
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "match_time": "2024-12-27 16:00",
        "start_time": "2024-12-27 16:00",
        "state": 3,
        "status": "second_half",
        "is_live": true,
        "home_score": 2,
        "away_score": 1,
        "ht_home_score": 1,
        "ht_away_score": 0,
        "minute": 67,
        "half": 2,
        "home_red_cards": 0,
        "away_red_cards": 0,
        "stats": {
          "shots": {"home": 15, "away": 12},
          "shots_on_target": {"home": 6, "away": 4},
          "fouls": {"home": 8, "away": 10},
          "corners": {"home": 7, "away": 4},
          "possession": {"home": 58, "away": 42},
          "attacks": {"home": 45, "away": 38},
          "dangerous_attacks": {"home": 12, "away": 8}
        },
        "odds": {
          "asian_handicap": {
            "home": 1.02,
            "line": -0.5,
            "away": 0.88,
            "opening_home": null,
            "opening_line": null,
            "opening_away": null
          },
          "match_result": {
            "home": 2.10,
            "draw": 3.40,
            "away": 3.20,
            "opening_home": null,
            "opening_draw": null,
            "opening_away": null
          },
          "over_under": {
            "over": 1.85,
            "line": 2.5,
            "under": 1.95,
            "opening_over": null,
            "opening_line": null,
            "opening_under": null
          },
          "btts": {
            "yes": 1.72,
            "no": 2.10
          },
          "double_chance": {
            "home_draw": 1.35,
            "home_away": 1.60,
            "draw_away": 2.25
          },
          "half_time": {
            "home": 2.50,
            "draw": 3.20,
            "away": 2.80
          }
        },
        "corners": {
          "odds": {
            "over": 1.85,
            "line": 9.5,
            "under": 1.95,
            "home": 0.92,
            "handicap": -1.5,
            "away": 0.98
          },
          "stats": {
            "home_first_half": 3,
            "away_first_half": 2,
            "home_total": 7,
            "away_total": 4
          },
          "total": {"home": 7, "away": 4},
          "first_half": {"home": 3, "away": 2}
        }
      },
      {
        "index": 1,
        "match_id": 2882313,
        "league_id": 36,
        "home_team": "Liverpool",
        "away_team": "Man City",
        "status": "not_started",
        "is_live": false,
        "home_score": null,
        "away_score": null
      }
    ],
    "leagues": {
      "36": {
        "league_id": 36,
        "short_name": "ENG PR",
        "name": "Premier League",
        "country_id": 1
      },
      "37": {
        "league_id": 37,
        "short_name": "SPA D1",
        "name": "La Liga",
        "country_id": 5
      }
    },
    "meta": {
      "total_matches": 76,
      "live_count": 12,
      "last_update": "2024-12-27 15:30:00",
      "cache_ttl": 30
    }
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Type | In-Memory (Thread-safe) |
| Cache Key | `live_all_{include_stats}_{include_odds}_{include_corners}` |
| TTL | 30 saniye |

---

### 3.2 GET /api/v1/matches/live/{match_id}

**Açıklama:** Belirli bir maçın detaylı canlı verisini getirir.

#### Request

```http
GET /api/v1/matches/live/2882312 HTTP/1.1
Host: localhost:8000
```

#### Path Parametreleri

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `match_id` | integer | Evet | Maç ID'si |

#### İşlem Akışı

```
1. Cache kontrol: "live_match_{match_id}"
2. Cache miss ise:
   a. fetch_live_data_cached() ile tüm canlı veriyi çek
   b. matches listesinden match_id'yi bul
   c. events ekle (varsa)
   d. league bilgisi ekle
   e. Cache'e kaydet (30s TTL)
3. Return match data
```

#### Response

```json
{
  "success": true,
  "data": {
    "index": 0,
    "match_id": 2882312,
    "league_id": 36,
    "home_team_id": 19,
    "away_team_id": 18,
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "match_time": "2024-12-27 16:00",
    "start_time": "2024-12-27 16:00",
    "state": 3,
    "status": "second_half",
    "is_live": true,
    "home_score": 2,
    "away_score": 1,
    "ht_home_score": 1,
    "ht_away_score": 0,
    "minute": 67,
    "half": 2,
    "home_red_cards": 0,
    "away_red_cards": 0,
    "stats": {
      "shots": {"home": 15, "away": 12},
      "shots_on_target": {"home": 6, "away": 4},
      "fouls": {"home": 8, "away": 10},
      "corners": {"home": 7, "away": 4},
      "possession": {"home": 58, "away": 42},
      "attacks": {"home": 45, "away": 38},
      "dangerous_attacks": {"home": 12, "away": 8}
    },
    "odds": {
      "asian_handicap": {"home": 1.02, "line": -0.5, "away": 0.88},
      "match_result": {"home": 2.10, "draw": 3.40, "away": 3.20},
      "over_under": {"over": 1.85, "line": 2.5, "under": 1.95},
      "btts": {"yes": 1.72, "no": 2.10},
      "double_chance": {"home_draw": 1.35, "home_away": 1.60, "draw_away": 2.25}
    },
    "corners": {
      "total": {"home": 7, "away": 4},
      "first_half": {"home": 3, "away": 2},
      "odds": {"over": 1.85, "line": 9.5, "under": 1.95}
    },
    "events": [
      {
        "is_home": true,
        "type_id": 1,
        "type": "goal",
        "minute": 23,
        "player": "Saka B."
      },
      {
        "is_home": false,
        "type_id": 1,
        "type": "goal",
        "minute": 45,
        "player": "Palmer C."
      },
      {
        "is_home": true,
        "type_id": 5,
        "type": "yellow_card",
        "minute": 34,
        "player": "Rice D."
      },
      {
        "is_home": true,
        "type_id": 1,
        "type": "goal",
        "minute": 67,
        "player": "Havertz K."
      }
    ],
    "league": {
      "league_id": 36,
      "short_name": "ENG PR",
      "name": "Premier League",
      "country_id": 1
    }
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `live_match_{match_id}` |
| TTL | 30 saniye |

---

### 3.3 GET /api/v1/matches/live/{match_id}/stats

**Açıklama:** Belirli bir maçın teknik istatistiklerini getirir.

#### Request

```http
GET /api/v1/matches/live/2882312/stats HTTP/1.1
Host: localhost:8000
```

#### Dış API İsteği

```
URL: https://live3.nowgoal26.com/gf/data/detail.js
Method: GET
```

#### Dış API Ham Response (detail.js - tc[] kısmı)

```javascript
// tc[index]="match_id^stat_entries"
// stat_entry format: stat_id,home_value,away_value

tc[0]="2882312^3,15,12;4,6,4;5,8,10;6,7,4;8,12,9;9,2,3;14,58,42;15,8,12;16,3,5;19,18,15;20,8,6;21,45,38;24,12,8;34,9,8;37,3,2;38,22,18;39,8,6;40,18,22;41,412,356;42,86,82;43,45,38;44,12,8;45,3,2;46,55,45";
```

#### Stat ID Mapping (TECH_STATS_MAP)

| Stat ID | İsim | Açıklama |
|---------|------|----------|
| 3 | `shots` | Toplam şut |
| 4 | `shots_on_target` | İsabetli şut |
| 5 | `fouls` | Faul |
| 6 | `corners` | Korner |
| 8 | `free_kicks` | Serbest vuruş |
| 9 | `offsides` | Ofsayt |
| 14 | `possession` | Top hakimiyeti % |
| 15 | `aerials` | Hava topları |
| 16 | `saves` | Kaleci kurtarışı |
| 19 | `successful_tackles` | Başarılı müdahale |
| 20 | `interceptions` | Top kapma |
| 21 | `long_passes` | Uzun pas |
| 24 | `crosses` | Orta |
| 34 | `shots_off_target` | İsabetsiz şut |
| 37 | `blocked` | Bloke edilen şut |
| 38 | `tackles` | Toplam müdahale |
| 39 | `dribbles` | Başarılı çalım |
| 40 | `throw_ins` | Taç atışı |
| 41 | `total_passes` | Toplam pas |
| 42 | `pass_success` | Pas başarı oranı % |
| 43 | `attacks` | Toplam atak |
| 44 | `dangerous_attacks` | Tehlikeli atak |
| 45 | `corners_ht` | İlk yarı korner |
| 46 | `possession_ht` | İlk yarı top hakimiyeti % |

#### Response

```json
{
  "success": true,
  "data": {
    "match_id": 2882312,
    "stats": {
      "shots": {"home": 15, "away": 12},
      "shots_on_target": {"home": 6, "away": 4},
      "shots_off_target": {"home": 9, "away": 8},
      "blocked": {"home": 3, "away": 2},
      "fouls": {"home": 8, "away": 10},
      "corners": {"home": 7, "away": 4},
      "corners_ht": {"home": 3, "away": 2},
      "free_kicks": {"home": 12, "away": 9},
      "offsides": {"home": 2, "away": 3},
      "possession": {"home": 58, "away": 42},
      "possession_ht": {"home": 55, "away": 45},
      "aerials": {"home": 8, "away": 12},
      "saves": {"home": 3, "away": 5},
      "successful_tackles": {"home": 18, "away": 15},
      "interceptions": {"home": 8, "away": 6},
      "long_passes": {"home": 45, "away": 38},
      "crosses": {"home": 12, "away": 8},
      "tackles": {"home": 22, "away": 18},
      "dribbles": {"home": 8, "away": 6},
      "throw_ins": {"home": 18, "away": 22},
      "total_passes": {"home": 412, "away": 356},
      "pass_success": {"home": 86, "away": 82},
      "attacks": {"home": 45, "away": 38},
      "dangerous_attacks": {"home": 12, "away": 8}
    },
    "cache_ttl": 30
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `live_stats_{match_id}` |
| TTL | 30 saniye |

---

### 3.4 GET /api/v1/matches/live/{match_id}/odds

**Açıklama:** Belirli bir maçın Bet365 canlı oranlarını getirir.

#### Request

```http
GET /api/v1/matches/live/2882312/odds HTTP/1.1
Host: localhost:8000
```

#### Dış API İsteği

```
URL: https://live3.nowgoal26.com/gf/data/odds/en/runOddsData_8.txt
Method: GET
```

#### Dış API Ham Response (runOddsData_8.txt)

```
2882312!1.02,-0.5,0.88,1.05,-0.25,0.85!2.10,3.40,3.20,2.20,3.30,3.10!1.85,2.5,1.95,1.90,2.5,1.90!1.72,2.10!1.35,1.60,2.25!2.50,3.20,2.80$next_match...
```

#### Oran Grupları Açıklama

| Grup | Format | İçerik |
|------|--------|--------|
| 1 (AH) | `home,line,away,op_home,op_line,op_away` | Asya Handikap (canlı + açılış) |
| 2 (1X2) | `home,draw,away,op_home,op_draw,op_away` | Maç Sonucu (canlı + açılış) |
| 3 (O/U) | `over,line,under,op_over,op_line,op_under` | Alt/Üst (canlı + açılış) |
| 4 (BTTS) | `yes,no` | Karşılıklı Gol |
| 5 (DC) | `home_draw,home_away,draw_away` | Çifte Şans |
| 6 (HT) | `home,draw,away` | İlk Yarı Sonucu |

#### Response

```json
{
  "success": true,
  "data": {
    "match_id": 2882312,
    "odds": {
      "asian_handicap": {
        "home": 1.02,
        "line": -0.5,
        "away": 0.88,
        "opening_home": 1.05,
        "opening_line": -0.25,
        "opening_away": 0.85
      },
      "match_result": {
        "home": 2.10,
        "draw": 3.40,
        "away": 3.20,
        "opening_home": 2.20,
        "opening_draw": 3.30,
        "opening_away": 3.10
      },
      "over_under": {
        "over": 1.85,
        "line": 2.5,
        "under": 1.95,
        "opening_over": 1.90,
        "opening_line": 2.5,
        "opening_under": 1.90
      },
      "btts": {
        "yes": 1.72,
        "no": 2.10
      },
      "double_chance": {
        "home_draw": 1.35,
        "home_away": 1.60,
        "draw_away": 2.25
      },
      "half_time": {
        "home": 2.50,
        "draw": 3.20,
        "away": 2.80
      }
    },
    "bookmaker": "Bet365",
    "cache_ttl": 15
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `live_odds_{match_id}` |
| TTL | **15 saniye** (oranlar daha sık değişir) |

---

### 3.5 GET /api/v1/matches/live/{match_id}/corners

**Açıklama:** Belirli bir maçın korner istatistiklerini ve korner oranlarını getirir.

#### Request

```http
GET /api/v1/matches/live/2882312/corners HTTP/1.1
Host: localhost:8000
```

#### Dış API İsteği

```
URL: https://live3.nowgoal26.com/gf/data/sbCorner.js
Method: GET
```

#### Dış API Ham Response (sbCorner.js)

```javascript
// sCornerData[match_id]="section1^odds^stats^events"

sCornerData[2882312]="^1.85,9.5,1.95,0.92,-1.5,0.98^3,2,7,4^";

Açıklama:
- Section 1: Boş veya temel bilgi
- odds: over,line,under,home,handicap,away (korner oranları)
- stats: home_ht,away_ht,home_total,away_total (korner istatistikleri)
- events: Korner olayları (opsiyonel)
```

#### Response

```json
{
  "success": true,
  "data": {
    "match_id": 2882312,
    "corners": {
      "odds": {
        "over": 1.85,
        "line": 9.5,
        "under": 1.95,
        "home": 0.92,
        "handicap": -1.5,
        "away": 0.98
      },
      "stats": {
        "home_first_half": 3,
        "away_first_half": 2,
        "home_total": 7,
        "away_total": 4
      },
      "total": {
        "home": 7,
        "away": 4
      },
      "first_half": {
        "home": 3,
        "away": 2
      }
    },
    "cache_ttl": 30
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `live_corners_{match_id}` |
| TTL | 30 saniye |

---

### 3.6 GET /api/v1/matches/live/{match_id}/events

**Açıklama:** Belirli bir maçın canlı olaylarını (gol, kart, değişiklik) getirir.

#### Request

```http
GET /api/v1/matches/live/2882312/events HTTP/1.1
Host: localhost:8000
```

#### Dış API İsteği

```
URL: https://live3.nowgoal26.com/gf/data/detail.js
Method: GET
(Stats ile aynı endpoint - rq[] dizisinden parse edilir)
```

#### Dış API Ham Response (detail.js - rq[] kısmı)

```javascript
// rq[index]="match_id^is_home^event_type^minute^player_name^player_id^team_id^extra"

rq[0]="2882312^1^1^23^Saka B.^12345^19^0";           // Ev sahibi gol, 23'
rq[1]="2882312^1^5^34^Rice D.^12348^19^0";           // Ev sahibi sarı kart, 34'
rq[2]="2882312^0^1^45^Palmer C.^12347^18^0";         // Deplasman gol, 45'
rq[3]="2882312^1^8^60^Martinelli G.^12349^19^0";     // Oyuncu giriş, 60'
rq[4]="2882312^1^9^60^Jesus G.^12350^19^0";          // Oyuncu çıkış, 60'
rq[5]="2882312^1^1^67^Havertz K.^12346^19^0";        // Ev sahibi gol, 67'
```

#### Event Type Mapping

| Type ID | İsim | Açıklama |
|---------|------|----------|
| 1 | `goal` | Gol |
| 2 | `own_goal` | Kendi kalesine gol |
| 3 | `penalty_goal` | Penaltı golü |
| 4 | `penalty_missed` | Kaçırılan penaltı |
| 5 | `yellow_card` | Sarı kart |
| 6 | `red_card` | Kırmızı kart |
| 7 | `second_yellow` | İkinci sarı (kırmızı) |
| 8 | `substitution_in` | Oyuncu girişi |
| 9 | `substitution_out` | Oyuncu çıkışı |
| 10 | `var_goal` | VAR gol onayı |
| 11 | `var_no_goal` | VAR gol iptali |

#### Response

```json
{
  "success": true,
  "data": {
    "match_id": 2882312,
    "events": [
      {
        "is_home": true,
        "type_id": 1,
        "type": "goal",
        "minute": 23,
        "player": "Saka B."
      },
      {
        "is_home": true,
        "type_id": 5,
        "type": "yellow_card",
        "minute": 34,
        "player": "Rice D."
      },
      {
        "is_home": false,
        "type_id": 1,
        "type": "goal",
        "minute": 45,
        "player": "Palmer C."
      },
      {
        "is_home": true,
        "type_id": 8,
        "type": "substitution_in",
        "minute": 60,
        "player": "Martinelli G."
      },
      {
        "is_home": true,
        "type_id": 9,
        "type": "substitution_out",
        "minute": 60,
        "player": "Jesus G."
      },
      {
        "is_home": true,
        "type_id": 1,
        "type": "goal",
        "minute": 67,
        "player": "Havertz K."
      }
    ],
    "cache_ttl": 30
  },
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `live_events_{match_id}` |
| TTL | 30 saniye |

---

## 4. Veri Yapıları ve Mapping'ler

### 4.1 Maç Durumu (Match Status)

| State | Status | is_live | Açıklama |
|-------|--------|---------|----------|
| 0 | `not_started` | false | Başlamadı |
| 1 | `first_half` | true | İlk yarı |
| 2 | `half_time` | true | Devre arası |
| 3 | `second_half` | true | İkinci yarı |
| 4 | `extra_time` | true | Uzatma |
| 5 | `penalty` | true | Penaltılar |
| -1 | `finished` | false | Bitti |
| -10 | `cancelled` | false | İptal |
| -11 | `postponed` | false | Ertelendi |
| -12 | `interrupted` | false | Yarıda kesildi |
| -13 | `suspended` | false | Askıya alındı |
| -14 | `abandoned` | false | Terk edildi |

### 4.2 Dakika Hesaplama Mantığı

```python
def calculate_minute(start_time_str, state):
    """
    state=1 (İlk yarı): elapsed dakika (max 45)
    state=2 (Devre arası): 45
    state=3 (İkinci yarı): 45 + elapsed dakika (max 90)
    state=4 (Uzatma): 90 + elapsed
    state=5 (Penaltılar): 120
    """
    if state == 1:
        return min(elapsed, 45)
    elif state == 2:
        return 45
    elif state == 3:
        return 45 + min(elapsed, 45)
    elif state == 4:
        return 90 + elapsed
    elif state == 5:
        return 120
```

### 4.3 Odds Line Değerleri Açıklaması

**Asya Handikap (AH):**
```
line = -0.5  → Ev sahibi 0.5 gol verir (kazanması gerekir)
line = 0.0   → Beraberlik geçersiz (ortalama)
line = +0.5  → Ev sahibi 0.5 gol alır (yenilmese yeter)
line = -1.0  → Ev sahibi 1 gol verir (2+ fark gerekir)
```

**Alt/Üst (O/U):**
```
line = 2.5  → 3+ gol = Üst kazanır, 0-2 gol = Alt kazanır
line = 3.0  → 4+ gol = Üst, 0-2 gol = Alt, 3 gol = İade
line = 3.5  → 4+ gol = Üst, 0-3 gol = Alt
```

---

## 5. Örnek Dış API URL'leri

### 5.1 Tam URL Listesi

```bash
# Canlı Maç Listesi
https://live3.nowgoal26.com/gf/data/bf_en-idn.js

# Teknik İstatistikler + Olaylar
https://live3.nowgoal26.com/gf/data/detail.js

# Bet365 Canlı Oranları
https://live3.nowgoal26.com/gf/data/odds/en/runOddsData_8.txt

# Korner İstatistikleri
https://live3.nowgoal26.com/gf/data/sbCorner.js

# Gerçek Zamanlı Skor Değişiklikleri (XML)
https://live3.nowgoal26.com/gf/data/change_en.xml
```

### 5.2 cURL Test Komutları

```bash
# Canlı maç listesi test
curl -H "User-Agent: Mozilla/5.0" "https://live3.nowgoal26.com/gf/data/bf_en-idn.js"

# Teknik istatistikler test
curl -H "User-Agent: Mozilla/5.0" "https://live3.nowgoal26.com/gf/data/detail.js"

# Oranlar test
curl -H "User-Agent: Mozilla/5.0" "https://live3.nowgoal26.com/gf/data/odds/en/runOddsData_8.txt"

# Korner test
curl -H "User-Agent: Mozilla/5.0" "https://live3.nowgoal26.com/gf/data/sbCorner.js"
```

---

## 6. Hata Kodları

### 6.1 HTTP Durum Kodları

| Kod | Açıklama | Örnek Senaryo |
|-----|----------|---------------|
| 200 | Başarılı | Normal yanıt |
| 404 | Not Found | Maç bulunamadı, stats/odds/corners bulunamadı |
| 500 | Internal Server Error | Parse hatası, beklenmeyen hata |
| 503 | Service Unavailable | Dış API erişilemez |

### 6.2 Hata Response Örnekleri

**404 - Maç Bulunamadı:**
```json
{
  "success": false,
  "error": "Match 9999999 not found",
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

**404 - Stats Bulunamadı:**
```json
{
  "success": false,
  "error": "Stats not found for match 2882312",
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

**503 - Dış API Hatası:**
```json
{
  "success": false,
  "error": "Failed to fetch live data",
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

**500 - Genel Hata:**
```json
{
  "success": false,
  "error": "Failed to fetch live matches",
  "timestamp": "2024-12-27T15:30:00.000000"
}
```

---

## 7. Cache Stratejisi

### 7.1 In-Memory Cache Yapısı

```python
# live_utils.py
_live_cache = {
    "live_all_true_true_false": {
        "data": {...},        # Parsed data
        "expires": 1735312230.0,  # Unix timestamp (now + TTL)
        "created": 1735312200.0   # Unix timestamp
    },
    "live_match_2882312": {...},
    "live_stats_2882312": {...},
    "live_odds_2882312": {...},
    "live_corners_2882312": {...},
    "live_events_2882312": {...}
}
```

### 7.2 Cache TTL Özeti

| Cache Key Pattern | TTL | Açıklama |
|-------------------|-----|----------|
| `live_all_{s}_{o}_{c}` | 30s | Tüm canlı veriler |
| `live_match_{id}` | 30s | Tek maç detayı |
| `live_stats_{id}` | 30s | Maç istatistikleri |
| `live_odds_{id}` | **15s** | Maç oranları (daha sık değişir) |
| `live_corners_{id}` | 30s | Korner istatistikleri |
| `live_events_{id}` | 30s | Maç olayları |

### 7.3 Cache Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        CACHE FLOW                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Request arrives                                                │
│       │                                                          │
│       ▼                                                          │
│  _get_from_cache(cache_key)                                     │
│       │                                                          │
│       ├── Entry exists AND not expired → Return cached data     │
│       │                                                          │
│       └── Entry missing OR expired → Fetch fresh data           │
│                   │                                              │
│                   ▼                                              │
│           fetch_live_endpoint() × N (parallel)                  │
│                   │                                              │
│                   ▼                                              │
│           Parse with LiveDataParser                             │
│                   │                                              │
│                   ▼                                              │
│           _set_cache(cache_key, data, TTL)                      │
│                   │                                              │
│                   ▼                                              │
│           Return fresh data                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.4 Thread-Safe Cache Lock

```python
def _get_cache_lock():
    """Thread-safe cache işlemleri için lock"""
    global _cache_lock
    if _cache_lock is None:
        import threading
        _cache_lock = threading.Lock()
    return _cache_lock

# Kullanım:
lock = _get_cache_lock()
with lock:
    # Cache okuma/yazma işlemi
    pass
```

---

## 8. Parser Detayları

### 8.1 Parser Sınıfları

| Parser | Dosya | Amaç |
|--------|-------|------|
| `LiveMatchParser` | bf_en-idn.js | A[], B[], C[] dizilerini parse eder |
| `LiveStatsParser` | detail.js | tc[] dizisini parse eder |
| `LiveEventsParser` | detail.js | rq[] dizisini parse eder |
| `LiveOddsParser` | runOddsData_8.txt | ! ve $ ile ayrılmış text'i parse eder |
| `CornerStatsParser` | sbCorner.js | sCornerData[] dizisini parse eder |
| `LiveDataParser` | - | Tüm parser'ları koordine eder |

### 8.2 Pre-compiled Regex Pattern'ler

```python
# live_parsers.py - Performans optimizasyonu

# Module load'da bir kez compile edilir
RE_LAST_CREATE_TIME = re.compile(r'lastCreateTime_bfIndex="([^"]+)"')
RE_MATCH_COUNT = re.compile(r'var matchcount=(\d+)')
RE_LIVE_MATCH_ARRAY = re.compile(r"A\[(\d+)\]=\[([^\]]+)\]")
RE_LIVE_LEAGUE_ARRAY = re.compile(r"B\[(\d+)\]=\[([^\]]+)\]")
RE_LIVE_COUNTRY_ARRAY = re.compile(r"C\[(\d+)\]=\[([^\]]+)\]")
RE_TECH_STATS = re.compile(r'tc\[(\d+)\]="([^"]+)"')
RE_EVENTS = re.compile(r'rq\[(\d+)\]="([^"]+)"')
RE_CORNER_DATA = re.compile(r'sCornerData\[(\d+)\]="([^"]*)"')
RE_HTML_TAGS = re.compile(r'<[^>]+>')
```

### 8.3 Smart Split Fonksiyonu

Virgülle ayrılmış string'leri parse ederken tırnak içindeki virgülleri korur:

```python
def _smart_split(self, data_str: str) -> List[str]:
    """
    Input:  "1,2,'Team, Name',4"
    Output: ['1', '2', 'Team, Name', '4']
    """
    parts = []
    current = ""
    in_quotes = False
    quote_char = None

    for char in data_str:
        if char in ["'", '"'] and not in_quotes:
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            in_quotes = False
        elif char == ',' and not in_quotes:
            parts.append(current.strip().strip("'\""))
            current = ""
            continue
        else:
            current += char

    if current:
        parts.append(current.strip().strip("'\""))

    return parts
```

### 8.4 Enrich Matches Fonksiyonu

```python
def enrich_matches_with_stats(self, matches, stats, odds, corners):
    """
    Match listesini stats, odds ve corners ile zenginleştirir

    Input matches: [
        {"match_id": 2882312, "home_team": "Arsenal", ...}
    ]

    Input stats: {
        2882312: {"shots": {"home": 15, "away": 12}, ...}
    }

    Output: [
        {
            "match_id": 2882312,
            "home_team": "Arsenal",
            "stats": {"shots": {"home": 15, "away": 12}, ...},
            "odds": {...},
            "corners": {...}
        }
    ]
    """
```

---

## 9. Performans Notları

### 9.1 Paralel Fetch

```python
# 4 endpoint paralel olarak fetch edilir
executor = get_global_thread_pool()
future_to_key = {
    executor.submit(fetch_live_endpoint, 'matches'): 'matches',
    executor.submit(fetch_live_endpoint, 'stats'): 'stats',
    executor.submit(fetch_live_endpoint, 'odds'): 'odds',
    executor.submit(fetch_live_endpoint, 'corners'): 'corners',
}

# Toplam timeout: 15 saniye
for future in as_completed(future_to_key, timeout=15):
    ...
```

### 9.2 Response Boyutları (Yaklaşık)

| Endpoint | Boyut | Parse Süresi |
|----------|-------|--------------|
| bf_en-idn.js | ~50-100 KB | ~100ms |
| detail.js | ~100-200 KB | ~150ms |
| runOddsData_8.txt | ~30-50 KB | ~50ms |
| sbCorner.js | ~20-40 KB | ~30ms |

### 9.3 Toplam Response Süresi

| Senaryo | Süre |
|---------|------|
| Cache hit | < 10ms |
| Cache miss (paralel fetch + parse) | 500ms - 2s |
| Dış API yavaş | 3-5s |

---

*Bu dokümantasyon Golsinyali API v1.0.0 için hazırlanmıştır.*
*Son güncelleme: 2024-12-27*
