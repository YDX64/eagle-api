# Golsinyali API - Lig Endpoint'leri Dokümantasyonu

Bu dokümantasyon, Golsinyali API'nin tüm lig endpoint'lerini, dış veri kaynaklarını, istek/yanıt yapılarını ve cache stratejilerini detaylı şekilde açıklamaktadır.

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Veri Kaynakları](#2-veri-kaynakları)
3. [Temel Lig Endpoint'leri (leagues.py)](#3-temel-lig-endpointleri-leaguespy)
4. [Detaylı Lig Endpoint'leri (league_data.py)](#4-detaylı-lig-endpointleri-league_datapy)
5. [Dış API URL Pattern'leri](#5-dış-api-url-patternleri)
6. [Popüler Lig ve Kupa ID'leri](#6-popüler-lig-ve-kupa-idleri)
7. [Hata Kodları](#7-hata-kodları)
8. [Cache Stratejisi](#8-cache-stratejisi)

---

## 1. Genel Bakış

### Mimari Akış

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT REQUEST                                    │
│                    GET /api/v1/leagues/36/standings                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLASK ROUTE HANDLER                                  │
│                        routes/league_data.py                                 │
│                                                                              │
│  1. Query parametrelerini validate et (season, type, sub_league_id)         │
│  2. Cache key oluştur: "league_standings:36:null:2024-2025:overall"         │
│  3. Cache'te var mı kontrol et                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
            [CACHE HIT]                      [CACHE MISS]
                    │                               │
                    ▼                               ▼
┌──────────────────────────┐    ┌────────────────────────────────────────────┐
│   Return cached data     │    │            FETCH FROM EXTERNAL API          │
│   (Instant response)     │    │                                            │
└──────────────────────────┘    │  1. Sub-league ID'yi bul (cache veya HTTP)  │
                                │  2. Dış API URL'i oluştur                   │
                                │  3. HTTP GET request gönder                 │
                                │  4. JavaScript response'u parse et          │
                                │  5. Cache'e kaydet                          │
                                └────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL DATA SOURCE                                  │
│                                                                              │
│  URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js │
│                                                                              │
│  Response: JavaScript değişkenleri (arrLeague, arrTeam, totalScore, etc.)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PARSER LAYER                                       │
│                         league_parser.py                                     │
│                                                                              │
│  LeagueDataParser:                                                          │
│    - _parse_league_info()   → Lig bilgisi                                  │
│    - _parse_teams()         → Takım listesi                                │
│    - _parse_standings()     → Puan durumu                                  │
│    - _parse_rounds()        → Maçlar (haftalara göre)                      │
│    - _parse_zones()         → Düşme/Yükselme bölgeleri                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JSON RESPONSE                                        │
│                                                                              │
│  {                                                                           │
│    "success": true,                                                         │
│    "data": { ... parsed league data ... },                                  │
│    "timestamp": "2024-12-27T10:30:00.000Z"                                 │
│  }                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Response Wrapper Yapısı

Tüm başarılı yanıtlar aşağıdaki formatta döner:

```json
{
  "success": true,
  "data": {
    // Endpoint'e özel veri
  },
  "timestamp": "2024-12-27T10:30:00.000000",
  "cached": true  // Opsiyonel - sadece cache'ten geliyorsa
}
```

### Hata Response Yapısı

```json
{
  "success": false,
  "error": "Hata mesajı",
  "timestamp": "2024-12-27T10:30:00.000000",
  "details": {
    // Opsiyonel detaylar
  }
}
```

---

## 2. Veri Kaynakları

### 2.1 Ana Veri Kaynakları

| Kaynak | Base URL | Kullanım Alanı | Timeout |
|--------|----------|----------------|---------|
| **Nowgoal Live** | `https://live3.nowgoal26.com` | Günlük maçlar, canlı veriler | Connect: 3s, Read: 5s |
| **Nowgoal Football** | `https://football.nowgoal26.com` | Lig verileri, puan durumu, istatistikler | Connect: 3s, Read: 5s |
| **Goaloo** (Fallback) | `https://www.goaloo.com` | Nowgoal başarısız olursa | Connect: 3s, Read: 5s |

### 2.2 Lokal Veri Kaynakları

| Dosya | İçerik | Kullanım |
|-------|--------|----------|
| `data/leagues.json` | 957 lig metadata | `/leagues/all`, `/leagues/top`, `/leagues/countries`, `/leagues/{id}/lookup` |
| `data/leagues_master.json` | Kupa indeksi, rekabet bilgileri | `/leagues/{id}/info`, `/leagues/{id}/matches` optimizasyonu |

### 2.3 Failover Mekanizması

```
┌─────────────────────────────────────────────────────────────────┐
│                     REQUEST FLOW WITH FAILOVER                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Primary Source (live3.nowgoal26.com) → 3s timeout           │
│     │                                                            │
│     ├── SUCCESS → Return data, record_success()                 │
│     │                                                            │
│     └── FAILURE → record_failure(), try next source             │
│                                                                  │
│  2. Fallback Source (www.goaloo.com) → 3s timeout               │
│     │                                                            │
│     ├── SUCCESS → Return data, record_success()                 │
│     │                                                            │
│     └── FAILURE → Return error, send to Sentry                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Temel Lig Endpoint'leri (leagues.py)

### 3.1 GET /api/v1/leagues

**Açıklama:** Bugünkü maçlarda yer alan ligleri listeler.

#### Request

```http
GET /api/v1/leagues HTTP/1.1
Host: localhost:8000
```

#### Dış API İsteği

```
URL: https://live3.nowgoal26.com/ajax/SoccerAjax?type=6&date={YYYY-M-D}&order=league&timezone=3&flesh={random}

Örnek:
https://live3.nowgoal26.com/ajax/SoccerAjax?type=6&date=2024-12-27&order=league&timezone=3&flesh=0.8234567891234

Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
```

#### Dış API Ham Response (JavaScript)

```javascript
// Response, JavaScript değişkenleri olarak gelir
A[0]=[2804405,36,1,-1,'2024-12-27 16:00','Arsenal','Chelsea',2,1,1,0,...];
A[1]=[2804406,36,1,-1,'2024-12-27 18:30','Liverpool','Man City',3,2,1,1,...];
// ... daha fazla maç

// Lig bilgileri
B[36]=['England','ENG PR','Premier League'];
B[37]=['Spain','SPA D1','La Liga'];
// ... daha fazla lig
```

#### Response

```json
{
  "success": true,
  "data": {
    "leagues": [
      {
        "id": "36",
        "name": "Premier League",
        "code": "ENG PR"
      },
      {
        "id": "37",
        "name": "La Liga",
        "code": "SPA D1"
      },
      {
        "id": "34",
        "name": "Serie A",
        "code": "ITA D1"
      }
    ],
    "count": 45
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache | YOK - Her seferinde taze veri |
| Neden | Günlük maçlar sürekli değişiyor |

---

### 3.2 GET /api/v1/leagues/all

**Açıklama:** Tüm ligleri ülkelere göre organize edilmiş şekilde döndürür.

#### Request

```http
GET /api/v1/leagues/all HTTP/1.1
Host: localhost:8000

# Filtreli örnekler:
GET /api/v1/leagues/all?country=england
GET /api/v1/leagues/all?type=cup
GET /api/v1/leagues/all?country=turkey&type=league
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Açıklama | Örnek |
|-----------|-----|---------|----------|-------|
| `country` | string | Hayır | Ülke kodu filtresi | `england`, `turkey`, `spain` |
| `type` | string | Hayır | Tip filtresi | `league`, `subleague`, `cup` |

#### Veri Kaynağı

```
Kaynak: data/leagues.json (Lokal dosya)
HTTP İsteği: YOK - Sadece dosyadan okuma
```

#### Response

```json
{
  "success": true,
  "data": {
    "metadata": {
      "source": "nowgoal26.com",
      "fetched_at": "2025-12-27T02:08:26.489691",
      "total_countries": 128,
      "total_leagues": 957
    },
    "top_leagues": [
      {
        "id": 36,
        "code": "ENG PR",
        "name": "English Premier League",
        "type": "league",
        "country": "England",
        "continent": "europe",
        "current_season": "2025-2026",
        "available_seasons": ["2025-2026", "2024-2025", "2023-2024"]
      }
    ],
    "cups": [
      {
        "id": 90,
        "code": "ENG FAC",
        "name": "FA Cup",
        "type": "cup",
        "country": "England",
        "continent": "europe",
        "current_season": "2025-2026"
      }
    ],
    "leagues": {
      "england": [
        {
          "id": 36,
          "code": "ENG PR",
          "name": "English Premier League",
          "type": "league"
        },
        {
          "id": 37,
          "code": "ENG CH",
          "name": "Championship",
          "type": "league"
        }
      ],
      "turkey": [
        {
          "id": 745,
          "code": "TUR D1",
          "name": "Super Lig",
          "type": "subleague"
        }
      ]
    }
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache | DOLAYILI - JSON dosyası startup'ta yüklenir |
| TTL | Uygulama yaşam döngüsü boyunca |

---

### 3.3 GET /api/v1/leagues/top

**Açıklama:** Popüler ligleri döndürür (Big 5 + büyük kupalar).

#### Request

```http
GET /api/v1/leagues/top HTTP/1.1
Host: localhost:8000
```

#### Veri Kaynağı

```
Kaynak: data/leagues.json (Lokal dosya)
HTTP İsteği: YOK
```

#### Response

```json
{
  "success": true,
  "data": {
    "top_leagues": [
      {
        "id": 36,
        "code": "ENG PR",
        "name": "English Premier League",
        "type": "league",
        "country": "England",
        "continent": "europe",
        "current_season": "2025-2026",
        "available_seasons": ["2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022"]
      },
      {
        "id": 34,
        "code": "ITA D1",
        "name": "Serie A",
        "type": "subleague",
        "country": "Italy"
      },
      {
        "id": 31,
        "code": "SPA D1",
        "name": "La Liga",
        "type": "league",
        "country": "Spain"
      },
      {
        "id": 8,
        "code": "GER D1",
        "name": "Bundesliga",
        "type": "league",
        "country": "Germany"
      },
      {
        "id": 11,
        "code": "FRA D1",
        "name": "Ligue 1",
        "type": "league",
        "country": "France"
      }
    ],
    "major_cups": [
      {
        "id": 90,
        "code": "ENG FAC",
        "name": "FA Cup",
        "type": "cup",
        "country": "England"
      },
      {
        "id": 103,
        "code": "UCL",
        "name": "UEFA Champions League",
        "type": "cup"
      },
      {
        "id": 113,
        "code": "UEL",
        "name": "UEFA Europa League",
        "type": "cup"
      }
    ],
    "count": 10
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

---

### 3.4 GET /api/v1/leagues/countries

**Açıklama:** Lig bulunan ülkelerin listesi (lig sayısına göre sıralı).

#### Request

```http
GET /api/v1/leagues/countries HTTP/1.1
Host: localhost:8000
```

#### Veri Kaynağı

```
Kaynak: data/leagues.json (Lokal dosya)
HTTP İsteği: YOK
```

#### Response

```json
{
  "success": true,
  "data": {
    "countries": [
      {
        "code": "england",
        "name": "England",
        "league_count": 24
      },
      {
        "code": "brazil",
        "name": "Brazil",
        "league_count": 18
      },
      {
        "code": "spain",
        "name": "Spain",
        "league_count": 15
      },
      {
        "code": "germany",
        "name": "Germany",
        "league_count": 14
      },
      {
        "code": "turkey",
        "name": "Turkey",
        "league_count": 8
      }
    ],
    "count": 128
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

---

### 3.5 GET /api/v1/leagues/{league_id}/lookup

**Açıklama:** Belirli bir ligin detaylarını ID ile sorgular.

#### Request

```http
GET /api/v1/leagues/36/lookup HTTP/1.1
Host: localhost:8000
```

#### Path Parametreleri

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `league_id` | integer | Evet | Lig ID'si |

#### Veri Kaynağı

```
Kaynak: data/leagues.json (Lokal dosya)
Arama Sırası:
  1. top_leagues listesi
  2. cups listesi
  3. leagues (ülkelere göre)
  4. sub_league_mappings
```

#### Response (Başarılı)

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 36,
      "code": "ENG PR",
      "name": "English Premier League",
      "type": "league",
      "country": "England",
      "continent": "europe",
      "current_season": "2025-2026",
      "available_seasons": ["2025-2026", "2024-2025", "2023-2024"]
    },
    "found_in": "top_leagues"
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response (Bulunamadı)

```json
{
  "success": false,
  "error": "League 99999 not found",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

---

## 4. Detaylı Lig Endpoint'leri (league_data.py)

### 4.1 GET /api/v1/leagues/{league_id}/standings

**Açıklama:** Lig puan durumu tablosunu getirir.

#### Request

```http
GET /api/v1/leagues/36/standings?season=2024-2025&type=overall HTTP/1.1
Host: localhost:8000
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Varsayılan | Açıklama | Örnek |
|-----------|-----|---------|------------|----------|-------|
| `season` | string | EVET | - | Sezon (YYYY-YYYY formatı) | `2024-2025` |
| `type` | string | Hayır | `overall` | Puan durumu tipi | `overall`, `home`, `away` |
| `sub_league_id` | integer | Hayır | Otomatik | Alt lig ID (gruplu ligler için) | `918` |

#### İşlem Akışı

```
1. season parametresi validate edilir
2. sub_league_id belirtilmemişse:
   a. Cache kontrol: "sub_league_id:{league_id}"
   b. Cache'te yoksa: HTTP GET https://football.nowgoal26.com/league/{league_id}
   c. HTML'den SubSclassID extract edilir
   d. 24 saat cache'lenir

3. Ana veri çekilir:
   URL: https://football.nowgoal26.com/jsData/matchResult/{season}/s{league_id}_{sub_league_id}_en.js
   veya (sub_league_id yoksa):
   URL: https://football.nowgoal26.com/jsData/matchResult/{season}/s{league_id}_en.js
```

#### Dış API İsteği - Sub League ID Bulma

```
URL: https://football.nowgoal26.com/league/36
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8

Response (HTML içinden extract):
  var SubSclassID = 0;  // Premier League için 0 (alt lig yok)
  var SubSclassID = 918; // Türkiye Süper Lig için 918
```

#### Dış API İsteği - Puan Durumu

```
URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js?flesh=0.123456
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: */*
  Referer: https://football.nowgoal26.com/
```

#### Dış API Ham Response (JavaScript)

```javascript
var arrLeague = [36, '', '', 'England Premier League', '2024-2025', '#FFFFFF', ...];

var arrTeam = [
  [19, '', '', 'Arsenal', '', 'images/teams/19.png', 0],
  [15, '', '', 'Liverpool', '', 'images/teams/15.png', 0],
  [18, '', '', 'Chelsea', '', 'images/teams/18.png', 0],
  // ... 20 takım
];

var arrSubLeague = [[139, '联赛', '聯賽', 'League', 1, 38, 20, 0, 1, 21]];

// totalScore = Genel puan durumu
// [zone, rank, team_id, ?, played, won, drawn, lost, gf, ga, gd, win%, draw%, loss%, ?, ?, points, ...]
var totalScore = [
  [1, 1, 15, 0, 17, 14, 2, 1, 45, 15, 30, '82.4', '11.8', '5.9', 2.65, 0.88, 44, ...],  // Liverpool
  [1, 2, 19, 0, 17, 12, 4, 1, 38, 16, 22, '70.6', '23.5', '5.9', 2.24, 0.94, 40, ...],  // Arsenal
  [0, 3, 18, 0, 17, 10, 4, 3, 35, 20, 15, '58.8', '23.5', '17.6', 2.06, 1.18, 34, ...], // Chelsea
  // ... 20 takım
];

// homeScore = Ev sahibi puan durumu
var homeScore = [...];

// guestScore = Deplasman puan durumu
var guestScore = [...];
```

#### Response

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 36,
      "name": "England Premier League",
      "season": "2024-2025",
      "color": "#FFFFFF"
    },
    "sub_league": {
      "id": 139,
      "name": "League",
      "total_rounds": 38,
      "total_teams": 20
    },
    "sub_league_id": null,
    "standings_type": "overall",
    "standings": [
      {
        "rank": 1,
        "team_id": 15,
        "team_name": "Liverpool",
        "team_logo": "images/teams/15.png",
        "played": 17,
        "won": 14,
        "drawn": 2,
        "lost": 1,
        "goals_for": 45,
        "goals_against": 15,
        "goal_difference": 30,
        "points": 44,
        "win_percentage": 82.4,
        "zone": 1
      },
      {
        "rank": 2,
        "team_id": 19,
        "team_name": "Arsenal",
        "team_logo": "images/teams/19.png",
        "played": 17,
        "won": 12,
        "drawn": 4,
        "lost": 1,
        "goals_for": 38,
        "goals_against": 16,
        "goal_difference": 22,
        "points": 40,
        "win_percentage": 70.6,
        "zone": 1
      }
    ],
    "teams_count": 20,
    "zones": {
      "promotion": [1, 2, 3, 4],
      "playoff": [],
      "relegation": [18, 19, 20]
    }
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_standings:{league_id}:{sub_league_id}:{season}:{type}` |
| Fresh TTL | 30 dakika (1800 saniye) |
| Stale TTL | 60 dakika (3600 saniye) |
| Strateji | Stale-While-Revalidate |

---

### 4.2 GET /api/v1/leagues/{league_id}/matches

**Açıklama:** Lig maçlarını haftalara/turlara göre getirir.

#### Request

```http
GET /api/v1/leagues/36/matches?season=2024-2025 HTTP/1.1
Host: localhost:8000

# Belirli bir hafta için:
GET /api/v1/leagues/36/matches?season=2024-2025&round=17

# Kupa maçları için:
GET /api/v1/leagues/90/matches?season=2024-2025
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `season` | string | EVET | - | Sezon (YYYY-YYYY formatı) |
| `round` | integer | Hayır | Tümü | Hafta/Tur numarası |
| `sub_league_id` | integer | Hayır | Otomatik | Alt lig ID |

#### İşlem Akışı (Lig vs Kupa Otomatik Tespit)

```
1. league_id bilinen kupalardan mı kontrol et (KNOWN_CUPS set)
   - Evet → Direkt kupa URL'i dene
   - Hayır → Devam

2. Cache'te comp_type:{league_id} var mı?
   - "cup" → Kupa URL'i dene
   - "league" → Lig URL'i dene
   - Yok → Devam

3. Önce lig URL'ini dene:
   URL: https://football.nowgoal26.com/jsData/matchResult/{season}/s{league_id}_en.js
   - arrLeague varsa → Lig verisi, cache'e "league" kaydet
   - arrCup varsa → Kupa verisi, cache'e "cup" kaydet
   - 404/503 → Kupa URL'ini dene

4. Kupa URL'ini dene:
   URL: https://football.nowgoal26.com/jsData/matchResult/{season}/c{league_id}_en.js
   - arrCup varsa → Kupa verisi, cache'e "cup" kaydet
```

#### Dış API İsteği - Lig Maçları

```
URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js?flesh=0.789123
Method: GET
```

#### Dış API İsteği - Kupa Maçları

```
URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/c90_en.js?flesh=0.456789
Method: GET
```

#### Dış API Ham Response - Lig (JavaScript)

```javascript
// Hafta bazlı maçlar
// jh["R_{round}"] = [[match_data], ...]
// [match_id, league_id, status, datetime, home_id, away_id, score, ht_score, home_rank, away_rank, ...]

jh["R_1"] = [
  [2804001, 36, -1, '2024-08-17 15:00', 19, 14, '2-1', '1-0', 0, 0, ...],  // Arsenal vs Wolves
  [2804002, 36, -1, '2024-08-17 15:00', 13, 24, '1-1', '0-1', 0, 0, ...],  // Everton vs Brighton
  // ... 10 maç
];

jh["R_2"] = [
  [2804011, 36, -1, '2024-08-24 12:30', 15, 20, '2-0', '1-0', 0, 0, ...],  // Liverpool vs Brentford
  // ...
];

// ... R_38'e kadar
```

#### Dış API Ham Response - Kupa (JavaScript)

```javascript
var arrCup = [90, '', '', 'England FA Cup', '', '', 'ENG FAC', '2024-2025', 'cup.png', '#0000cc', ''];

// Kupa turları
var arrCupKind = [
  [25188, 0, '预赛', '預賽', 'Qualifying', 0, 0, 0],
  [25189, 0, '第一轮', '第一輪', '1st Round', 0, 0, 0],
  [25190, 0, '第二轮', '第二輪', '2nd Round', 0, 0, 0],
  [25191, 0, '第三轮', '第三輪', '3rd Round', 0, 0, 0],
  [25192, 0, '第四轮', '第四輪', '4th Round', 0, 0, 0],
  [25193, 0, '四分之一决赛', '四分之一決賽', 'Quarter-finals', 0, 0, 0],
  [25194, 0, '半决赛', '半決賽', 'Semi-finals', 0, 0, 0],
  [25195, 0, '决赛', '決賽', 'Final', 0, 0, 0],
];

// Kupa maçları (tur bazlı)
jh["G25191"] = [  // 3rd Round
  [2850001, 90, -1, '2025-01-04 15:00', 19, 1045, '3-0', '2-0', 0, 0, ...],  // Arsenal vs Lower League Team
  [2850002, 90, -1, '2025-01-04 15:00', 15, 892, '4-1', '2-0', 0, 0, ...],   // Liverpool vs Lower League Team
  // ...
];
```

#### Response - Lig (Tüm Haftalar)

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 36,
      "name": "England Premier League",
      "season": "2024-2025",
      "color": "#FFFFFF"
    },
    "sub_league": {
      "id": 139,
      "name": "League",
      "total_rounds": 38,
      "total_teams": 20
    },
    "sub_league_id": null,
    "season": "2024-2025",
    "round": null,
    "total_rounds": 38,
    "rounds": {
      "1": [
        {
          "match_id": 2804001,
          "datetime": "2024-08-17 15:00",
          "status": "finished",
          "match_type": "round",
          "home_team": {
            "id": 19,
            "name": "Arsenal",
            "logo": "images/teams/19.png",
            "rank": 0
          },
          "away_team": {
            "id": 14,
            "name": "Wolverhampton",
            "logo": "images/teams/14.png",
            "rank": 0
          },
          "score": {
            "full_time": "2-1",
            "half_time": "1-0"
          }
        }
      ],
      "2": [...],
      "17": [...]
    },
    "matches": null,
    "match_count": 380,
    "is_cup": false
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response - Lig (Tek Hafta)

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 36,
      "name": "England Premier League",
      "season": "2024-2025"
    },
    "sub_league": {...},
    "season": "2024-2025",
    "round": 17,
    "total_rounds": 38,
    "rounds": null,
    "matches": [
      {
        "match_id": 2804161,
        "datetime": "2024-12-26 15:00",
        "status": "finished",
        "match_type": "round",
        "home_team": {
          "id": 19,
          "name": "Arsenal",
          "logo": "images/teams/19.png"
        },
        "away_team": {
          "id": 18,
          "name": "Chelsea",
          "logo": "images/teams/18.png"
        },
        "score": {
          "full_time": "2-1",
          "half_time": "1-0"
        }
      }
    ],
    "match_count": 10,
    "is_cup": false
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response - Kupa

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 90,
      "name": "England FA Cup",
      "short_name": "ENG FAC",
      "season": "2024-2025",
      "image": "cup.png",
      "color": "#0000cc",
      "type": "cup"
    },
    "sub_league": {
      "id": null,
      "name": "Cup",
      "total_rounds": 8,
      "total_teams": 124
    },
    "season": "2024-2025",
    "round": null,
    "total_rounds": 8,
    "rounds": {
      "25191": [
        {
          "match_id": 2850001,
          "datetime": "2025-01-04 15:00",
          "status": "not_started",
          "match_type": "cup",
          "round_name": "3rd Round",
          "home_team": {
            "id": 19,
            "name": "Arsenal",
            "logo": "images/teams/19.png"
          },
          "away_team": {
            "id": 1045,
            "name": "Bolton Wanderers",
            "logo": "images/teams/1045.png"
          },
          "score": {
            "full_time": null,
            "half_time": null
          }
        }
      ]
    },
    "match_count": 64,
    "is_cup": true,
    "cup_rounds": {
      "25188": {"id": 25188, "name": "Qualifying", "name_cn": "预赛", "type": 0},
      "25189": {"id": 25189, "name": "1st Round", "name_cn": "第一轮", "type": 0},
      "25190": {"id": 25190, "name": "2nd Round", "name_cn": "第二轮", "type": 0},
      "25191": {"id": 25191, "name": "3rd Round", "name_cn": "第三轮", "type": 0},
      "25192": {"id": 25192, "name": "4th Round", "name_cn": "第四轮", "type": 0},
      "25193": {"id": 25193, "name": "Quarter-finals", "name_cn": "四分之一决赛", "type": 0},
      "25194": {"id": 25194, "name": "Semi-finals", "name_cn": "半决赛", "type": 0},
      "25195": {"id": 25195, "name": "Final", "name_cn": "决赛", "type": 0}
    }
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_matches:{league_id}:{sub_league_id}:{season}:{round\|all}` |
| Fresh TTL | 1 saat (3600 saniye) |
| Stale TTL | 2 saat (7200 saniye) |

---

### 4.3 GET /api/v1/leagues/{league_id}/full

**Açıklama:** Tüm lig verisini tek seferde getirir (puan durumu + tüm maçlar).

#### Request

```http
GET /api/v1/leagues/36/full?season=2024-2025 HTTP/1.1
Host: localhost:8000
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `season` | string | EVET | Sezon (YYYY-YYYY formatı) |

#### Dış API İsteği

```
URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js?flesh=0.123456
Method: GET
```

#### Response

```json
{
  "success": true,
  "data": {
    "league": {
      "id": 36,
      "name": "England Premier League",
      "season": "2024-2025",
      "color": "#FFFFFF"
    },
    "sub_league": {
      "id": 139,
      "name": "League",
      "total_rounds": 38,
      "total_teams": 20
    },
    "sub_league_id": null,
    "teams": [
      {"id": 19, "name": "Arsenal", "logo": "images/teams/19.png"},
      {"id": 15, "name": "Liverpool", "logo": "images/teams/15.png"},
      {"id": 18, "name": "Chelsea", "logo": "images/teams/18.png"}
    ],
    "standings": {
      "overall": [...],
      "home": [...],
      "away": [...]
    },
    "rounds": {
      "1": [...],
      "2": [...],
      "38": [...]
    },
    "zones": {
      "promotion": [1, 2, 3, 4],
      "playoff": [],
      "relegation": [18, 19, 20]
    },
    "total_matches": 380
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_full:{league_id}:{sub_league_id}:{season}` |
| Fresh TTL | 30 dakika |
| Stale TTL | 60 dakika |

---

### 4.4 GET /api/v1/leagues/{league_id}/info

**Açıklama:** Lig bilgisi ve mevcut alt ligleri getirir.

#### Request

```http
GET /api/v1/leagues/36/info HTTP/1.1
Host: localhost:8000

# Champions League (gruplu kupa)
GET /api/v1/leagues/103/info
```

#### İşlem Akışı

```
1. HIZLI YOL: leagues_master.json'da var mı kontrol et
   - Varsa → Direkt döndür (HTTP isteği yok!)

2. YAVAŞ YOL: Website'den çek
   a. HTTP GET https://football.nowgoal26.com/league/{league_id}
   b. HTML'den extract et:
      - SubSclassID
      - arrSubLeague (tüm alt ligler)
   c. Kupa mı kontrol et:
      - SubSclassID == 0 veya KNOWN_CUPS'ta → Kupa olabilir
      - Kupa URL'ini test et
```

#### Dış API İsteği

```
# Master data'da yoksa:
URL: https://football.nowgoal26.com/league/745
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
```

#### Response - Master Data'dan (Hızlı)

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "code": "ENG PR",
    "name": "English Premier League",
    "type": "league",
    "country": "England",
    "country_flag": "images/flags/england.png",
    "has_subleague": false,
    "available_seasons": ["2025-2026", "2024-2025", "2023-2024", "2022-2023"],
    "current_season": "2025-2026",
    "is_cup": false,
    "data_source": "master_data"
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response - Website'den (Alt Liglerle)

```json
{
  "success": true,
  "data": {
    "league_id": 745,
    "sub_league_id": 918,
    "sub_leagues": [
      {"id": 918, "name": "League", "is_default": true},
      {"id": 919, "name": "Championship Group", "is_default": false},
      {"id": 920, "name": "Relegation Group", "is_default": false}
    ],
    "sub_leagues_count": 3,
    "has_multiple_stages": true,
    "data_available": true,
    "is_cup": false,
    "cup_data_available": false,
    "data_source": "website"
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response - Kupa

```json
{
  "success": true,
  "data": {
    "league_id": 90,
    "code": "ENG FAC",
    "name": "FA Cup",
    "type": "cup",
    "country": "England",
    "has_subleague": false,
    "is_cup": true,
    "data_source": "master_data",
    "note": "This is a cup competition. Use /leagues/{id}/matches?season=YYYY-YYYY to get cup matches. Cup data uses round/stage names instead of numbered rounds."
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_info:{league_id}` |
| Fresh TTL | 24 saat |
| Stale TTL | 48 saat |

---

### 4.5 GET /api/v1/leagues/{league_id}/team-stats

**Açıklama:** Takım teknik istatistiklerini getirir (şut, pas, korner, kart, xG, vb.).

#### Request

```http
GET /api/v1/leagues/36/team-stats?season=2024-2025 HTTP/1.1
Host: localhost:8000

# Ev sahibi istatistikleri:
GET /api/v1/leagues/36/team-stats?season=2024-2025&type=home

# Deplasman istatistikleri:
GET /api/v1/leagues/36/team-stats?season=2024-2025&type=guest
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `season` | string | EVET | - | Sezon (YYYY-YYYY formatı) |
| `type` | string | Hayır | `Total` | İstatistik tipi: `Total`, `Home`, `guest` |

#### Dış API İsteği

```
URL: https://football.nowgoal26.com/jsdata/count/2024-2025/teamTech_36.js?r=0.456789
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  Accept: */*
  Referer: https://football.nowgoal26.com/
```

#### Dış API Ham Response (JavaScript)

```javascript
var techCout_Team = {
  "Tid": {
    "15": ["利物浦", "利物浦", "Liverpool"],
    "19": ["阿森纳", "阿森纳", "Arsenal"],
    "18": ["切尔西", "切尔西", "Chelsea"]
  },
  "Total": {
    "value": [
      // [TeamID, SchSum, shots, target, offTarget, passBall, passBallSuc, dribbles, yellow, red, ...]
      [15, 17, 285, 142, 98, 8956, 7891, 234, 18, 0, 89, 145, 98, 12, 45, 32, 67, 34, 89, 234, 45, 12, 28.5, 24.2, 3.1, 1.2, 18.7, 42, 156, 89, 67, 45, 58.2],
      [19, 17, 267, 128, 95, 9234, 8123, 198, 22, 1, 78, 167, 87, 15, 38, 28, 72, 45, 95, 256, 38, 10, 25.3, 21.8, 2.5, 1.0, 16.8, 38, 178, 95, 72, 52, 61.5],
      // ...
    ]
  },
  "Home": {...},
  "guest": {...}
};
```

#### Response

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "stats_type": "Total",
    "teams": [
      {
        "team_id": "15",
        "team_name": "Liverpool",
        "teamid": 15,
        "schsum": 17,
        "shots": 285,
        "target": 142,
        "offtarget": 98,
        "passball": 8956,
        "passballsuc": 7891,
        "dribbles": 234,
        "yellow": 18,
        "red": 0,
        "shotsed": 89,
        "fouls": 145,
        "corner": 98,
        "offside": 12,
        "header": 45,
        "headersuc": 32,
        "save": 67,
        "blocked": 34,
        "tackle": 89,
        "throwins": 234,
        "goal": 45,
        "fumble": 12,
        "expectedgoals": 28.5,
        "xgopenplay": 24.2,
        "xgsetplay": 3.1,
        "xgnonpenalty": 1.2,
        "xgot": 18.7,
        "tiobx": 42,
        "accuratecrosses": 156,
        "groundduelswon": 89,
        "aerialduelswon": 67,
        "clearances": 45,
        "avgcontrol": 58.2
      }
    ],
    "team_count": 20
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_team_stats:{league_id}:{season}:{type}` |
| Fresh TTL | 1 saat |
| Stale TTL | 2 saat |

---

### 4.6 GET /api/v1/leagues/{league_id}/player-stats

**Açıklama:** Oyuncu istatistiklerini getirir (gol, asist, şut, pas, rating, vb.).

#### Request

```http
GET /api/v1/leagues/36/player-stats?season=2024-2025 HTTP/1.1
Host: localhost:8000
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `season` | string | EVET | - | Sezon |
| `category` | string | Hayır | `offensive` | Kategori: `offensive`, `passing`, `defensive`, `summary` |

#### Dış API İsteği

```
URL: https://football.nowgoal26.com/jsdata/count/2024-2025/playertech_36.js?r=0.789456
Method: GET
Headers:
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
  Accept: */*
  Accept-Encoding: gzip, deflate
  Referer: https://football.nowgoal26.com/

Not: Bu endpoint büyük dosya döndürür (~134KB), 1-2 saniye sürebilir.
```

#### Response

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "category": "offensive",
    "players": [
      {
        "player_id": 12345,
        "player_name": "Mohamed Salah",
        "team_id": 15,
        "team_name": "Liverpool",
        "matches": 17,
        "minutes": 1489,
        "rating": 7.85,
        "goals": 15,
        "non_penalty_goals": 13,
        "penalty_goals": 2,
        "shots": 58,
        "shots_on_target": 32,
        "assists": 11,
        "key_passes": 45,
        "passes": 678,
        "pass_accuracy": 84.5
      },
      {
        "player_id": 12346,
        "player_name": "Erling Haaland",
        "team_id": 17,
        "team_name": "Manchester City",
        "matches": 16,
        "minutes": 1412,
        "rating": 7.62,
        "goals": 14,
        "non_penalty_goals": 11,
        "penalty_goals": 3,
        "shots": 62,
        "shots_on_target": 35,
        "assists": 3,
        "key_passes": 12,
        "passes": 245,
        "pass_accuracy": 72.3
      }
    ],
    "player_count": 100
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_player_stats:{league_id}:{season}:{category}` |
| Fresh TTL | 1 saat |
| Stale TTL | 2 saat |

---

### 4.7 GET /api/v1/leagues/{league_id}/handicap-stats

**Açıklama:** Asya Handikap ve Alt/Üst istatistiklerini getirir.

#### Request

```http
GET /api/v1/leagues/36/handicap-stats?season=2024-2025 HTTP/1.1
Host: localhost:8000
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `season` | string | EVET | Sezon |

#### Dış API İsteği

```
URL: https://football.nowgoal26.com/jsData/letGoal/2024-2025/l36.js?r=0.123789
Method: GET
```

#### Response

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "total_ah": [],
    "home_ah": [],
    "guest_ah": [],
    "summary": {
      "total_matches": 170,
      "total_goals": 478,
      "avg_goals": 2.81,
      "over_count": 98,
      "under_count": 72
    }
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_handicap_stats:{league_id}:{season}` |
| Fresh TTL | 30 dakika |
| Stale TTL | 60 dakika |

---

### 4.8 GET /api/v1/leagues/{league_id}/current-round

**Açıklama:** Ligin mevcut/aktif hafta numarasını getirir.

#### Request

```http
GET /api/v1/leagues/36/current-round?season=2024-2025 HTTP/1.1
Host: localhost:8000
```

#### Query Parametreleri

| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `season` | string | EVET | Sezon |

#### İşlem Akışı

```
1. Tüm maç verilerini çek
2. Her hafta için maç durumlarını analiz et:
   - finished: Bitmiş maç
   - live/playing/1H/2H/HT: Canlı maç
   - not_started: Başlamamış maç

3. Mevcut haftayı belirle:
   - Canlı maç varsa → O hafta current_round
   - Karışık (bitmiş + başlamamış) → O hafta current_round
   - Tümü bitmiş → Son bitmiş hafta current_round
   - Tümü başlamamış → İlk başlamamış hafta next_round
```

#### Dış API İsteği

```
URL: https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js?flesh=0.567891
Method: GET
```

#### Response

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "sub_league_id": null,
    "season": "2024-2025",
    "current_round": 17,
    "next_round": 18,
    "last_completed_round": 16,
    "total_rounds": 38,
    "season_completed": false
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Response (Sezon Bitmiş)

```json
{
  "success": true,
  "data": {
    "league_id": 36,
    "sub_league_id": null,
    "season": "2023-2024",
    "current_round": 38,
    "next_round": null,
    "last_completed_round": 38,
    "total_rounds": 38,
    "season_completed": true
  },
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

#### Cache

| Parametre | Değer |
|-----------|-------|
| Cache Key | `league_current_round:{league_id}:{sub_league_id}:{season}` |
| Fresh TTL | 5 dakika |
| Stale TTL | 10 dakika |

---

## 5. Dış API URL Pattern'leri

### 5.1 Nowgoal Live (live3.nowgoal26.com)

| Endpoint | URL Pattern | Açıklama |
|----------|-------------|----------|
| Günlük Maçlar | `/ajax/SoccerAjax?type=6&date={YYYY-M-D}&order=league&timezone=3&flesh={random}` | Belirtilen tarihteki tüm maçlar |

**Örnek URL'ler:**
```
https://live3.nowgoal26.com/ajax/SoccerAjax?type=6&date=2024-12-27&order=league&timezone=3&flesh=0.123456789
https://live3.nowgoal26.com/ajax/SoccerAjax?type=6&date=2025-1-5&order=league&timezone=3&flesh=0.987654321
```

### 5.2 Nowgoal Football (football.nowgoal26.com)

| Endpoint | URL Pattern | Açıklama |
|----------|-------------|----------|
| Lig Sayfası | `/league/{league_id}` | Sub-league ID çıkarmak için HTML |
| Lig Verisi (sub_league'siz) | `/jsData/matchResult/{season}/s{league_id}_en.js` | Puan durumu + maçlar |
| Lig Verisi (sub_league'li) | `/jsData/matchResult/{season}/s{league_id}_{sub_league_id}_en.js` | Alt liglerle birlikte |
| Kupa Verisi | `/jsData/matchResult/{season}/c{cup_id}_en.js` | Kupa maçları |
| Takım İstatistikleri | `/jsdata/count/{season}/teamTech_{league_id}.js` | Teknik istatistikler |
| Oyuncu İstatistikleri | `/jsdata/count/{season}/playertech_{league_id}.js` | Oyuncu performans |
| Handikap İstatistikleri | `/jsData/letGoal/{season}/l{league_id}.js` | AH ve O/U verileri |

**Örnek URL'ler - Lig Sayfası:**
```
https://football.nowgoal26.com/league/36        # Premier League
https://football.nowgoal26.com/league/745       # Türkiye Süper Lig
https://football.nowgoal26.com/league/103       # Champions League
```

**Örnek URL'ler - Lig Verisi:**
```
# Sub-league olmayan ligler
https://football.nowgoal26.com/jsData/matchResult/2024-2025/s36_en.js     # Premier League
https://football.nowgoal26.com/jsData/matchResult/2024-2025/s37_en.js     # La Liga
https://football.nowgoal26.com/jsData/matchResult/2024-2025/s34_en.js     # Bundesliga

# Sub-league olan ligler
https://football.nowgoal26.com/jsData/matchResult/2024-2025/s745_918_en.js   # Süper Lig
https://football.nowgoal26.com/jsData/matchResult/2024-2025/s39_1234_en.js   # Serie A (sub_league varsa)
```

**Örnek URL'ler - Kupa Verisi:**
```
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c90_en.js      # FA Cup
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c103_en.js     # Champions League
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c113_en.js     # Europa League
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c167_en.js     # Türkiye Kupası
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c81_en.js      # Copa del Rey
https://football.nowgoal26.com/jsData/matchResult/2024-2025/c51_en.js      # DFB Pokal
```

**Örnek URL'ler - İstatistikler:**
```
# Takım İstatistikleri
https://football.nowgoal26.com/jsdata/count/2024-2025/teamTech_36.js      # Premier League
https://football.nowgoal26.com/jsdata/count/2024-2025/teamTech_37.js      # La Liga
https://football.nowgoal26.com/jsdata/count/2024-2025/teamTech_745.js     # Süper Lig

# Oyuncu İstatistikleri
https://football.nowgoal26.com/jsdata/count/2024-2025/playertech_36.js    # Premier League
https://football.nowgoal26.com/jsdata/count/2024-2025/playertech_8.js     # Bundesliga

# Handikap İstatistikleri
https://football.nowgoal26.com/jsData/letGoal/2024-2025/l36.js            # Premier League
https://football.nowgoal26.com/jsData/letGoal/2024-2025/l39.js            # Serie A
```

---

## 6. Popüler Lig ve Kupa ID'leri

### 6.1 Top 5 Lig

| Lig | ID | Ülke | Sub-League | Örnek URL |
|-----|-----|------|------------|-----------|
| Premier League | 36 | England | Yok | `s36_en.js` |
| La Liga | 31 | Spain | Yok | `s31_en.js` |
| Bundesliga | 8 | Germany | Yok | `s8_en.js` |
| Serie A | 34 | Italy | Var | `s34_{sub}_en.js` |
| Ligue 1 | 11 | France | Yok | `s11_en.js` |

### 6.2 Diğer Önemli Ligler

| Lig | ID | Ülke | Sub-League | Örnek URL |
|-----|-----|------|------------|-----------|
| Süper Lig | 745 | Turkey | 918 | `s745_918_en.js` |
| Eredivisie | 42 | Netherlands | Yok | `s42_en.js` |
| Primeira Liga | 43 | Portugal | Yok | `s43_en.js` |
| Championship | 37 | England | Yok | `s37_en.js` |
| 2. Bundesliga | 9 | Germany | Yok | `s9_en.js` |
| MLS | 85 | USA | Yok | `s85_en.js` |
| Saudi Pro League | 225 | Saudi Arabia | Yok | `s225_en.js` |

### 6.3 Önemli Kupalar

| Kupa | ID | Format | Örnek URL |
|------|-----|--------|-----------|
| UEFA Champions League | 103 | `c103_en.js` | Grup + Eleme |
| UEFA Europa League | 113 | `c113_en.js` | Grup + Eleme |
| UEFA Conference League | 2187 | `c2187_en.js` | Grup + Eleme |
| FA Cup | 90 | `c90_en.js` | Eleme turları |
| EFL Cup (Carabao) | 84 | `c84_en.js` | Eleme turları |
| Copa del Rey | 81 | `c81_en.js` | Eleme turları |
| DFB Pokal | 51 | `c51_en.js` | Eleme turları |
| Coppa Italia | 83 | `c83_en.js` | Eleme turları |
| Coupe de France | 54 | `c54_en.js` | Eleme turları |
| Türkiye Kupası | 167 | `c167_en.js` | Eleme turları |

---

## 7. Hata Kodları

### 7.1 HTTP Durum Kodları

| Kod | Açıklama | Örnek Senaryo |
|-----|----------|---------------|
| 200 | Başarılı | Normal yanıt |
| 400 | Bad Request | Eksik/geçersiz parametre |
| 404 | Not Found | Lig/Maç bulunamadı |
| 500 | Internal Server Error | Parse hatası, beklenmeyen hata |
| 503 | Service Unavailable | Dış API erişilemez |
| 504 | Gateway Timeout | Dış API zaman aşımı |

### 7.2 Hata Response Örnekleri

**400 - Eksik Parametre:**
```json
{
  "success": false,
  "error": "season is required (e.g., 2025-2026)",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**400 - Geçersiz Parametre:**
```json
{
  "success": false,
  "error": "type must be 'overall', 'home', or 'away'",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**404 - Bulunamadı:**
```json
{
  "success": false,
  "error": "League 99999 not found",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**404 - Hafta Bulunamadı:**
```json
{
  "success": false,
  "error": "Round 99 not found",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**404 - Kupa Verisi Yok:**
```json
{
  "success": false,
  "error": "Match data not available for this league/cup. Some cups (knockout format) may not have detailed match data in this format.",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**503 - Dış API Hatası:**
```json
{
  "success": false,
  "error": "Failed to fetch league data: Connection timeout",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**503 - Geçersiz Format:**
```json
{
  "success": false,
  "error": "Invalid league data format. The data source may have changed or is temporarily unavailable.",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

**500 - Parse Hatası:**
```json
{
  "success": false,
  "error": "Failed to parse league data",
  "timestamp": "2024-12-27T10:30:00.000000"
}
```

---

## 8. Cache Stratejisi

### 8.1 Cache Katmanları

```
┌─────────────────────────────────────────────────────────────────┐
│                        CACHE LAYERS                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: Redis (Primary)                                       │
│    - Distributed cache                                          │
│    - Persistent (survives restart)                              │
│    - TTL-based expiration                                       │
│                                                                  │
│  Layer 2: In-Memory (Fallback)                                  │
│    - Process-local cache                                        │
│    - Fast access                                                │
│    - Used when Redis unavailable                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Stale-While-Revalidate Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                 STALE-WHILE-REVALIDATE FLOW                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Check cache for key                                         │
│     │                                                            │
│     ├── FRESH (age < fresh_ttl)                                 │
│     │   └── Return cached data immediately                      │
│     │                                                            │
│     ├── STALE (fresh_ttl < age < stale_ttl)                    │
│     │   ├── Return cached data immediately (don't block user)  │
│     │   └── Start background thread to refresh cache           │
│     │                                                            │
│     └── EXPIRED (age > stale_ttl) or MISS                      │
│         └── Fetch fresh data (user waits)                       │
│             └── Update cache                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 Cache TTL Özeti

| Endpoint | Cache Key Pattern | Fresh TTL | Stale TTL |
|----------|-------------------|-----------|-----------|
| `/leagues` | - | Yok | Yok |
| `/leagues/all` | - | Startup | Uygulama ömrü |
| `/leagues/top` | - | Startup | Uygulama ömrü |
| `/leagues/countries` | - | Startup | Uygulama ömrü |
| `/leagues/{id}/lookup` | - | Startup | Uygulama ömrü |
| `/leagues/{id}/standings` | `league_standings:{id}:{sub}:{season}:{type}` | 30 dk | 60 dk |
| `/leagues/{id}/matches` | `league_matches:{id}:{sub}:{season}:{round}` | 60 dk | 120 dk |
| `/leagues/{id}/full` | `league_full:{id}:{sub}:{season}` | 30 dk | 60 dk |
| `/leagues/{id}/info` | `league_info:{id}` | 24 sa | 48 sa |
| `/leagues/{id}/team-stats` | `league_team_stats:{id}:{season}:{type}` | 60 dk | 120 dk |
| `/leagues/{id}/player-stats` | `league_player_stats:{id}:{season}:{cat}` | 60 dk | 120 dk |
| `/leagues/{id}/handicap-stats` | `league_handicap_stats:{id}:{season}` | 30 dk | 60 dk |
| `/leagues/{id}/current-round` | `league_current_round:{id}:{sub}:{season}` | 5 dk | 10 dk |

### 8.4 Yardımcı Cache'ler

| Cache Key | İçerik | TTL | Kullanım |
|-----------|--------|-----|----------|
| `sub_league_id:{league_id}` | Alt lig ID'si | 24 saat | HTTP isteğini azaltmak için |
| `comp_type:{league_id}` | `"league"` veya `"cup"` | 24 saat | Doğru URL'i seçmek için |

---

## Ek: HTTP İstek Headers

### Standart Headers

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: en-US,en;q=0.9
Accept-Encoding: gzip, deflate, br
```

### JavaScript Dosyaları İçin

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Accept: */*
Accept-Language: en-US,en;q=0.9
Referer: https://football.nowgoal26.com/
```

### Timeout Ayarları

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| Connect Timeout | 3 saniye | TCP bağlantı kurma süresi |
| Read Timeout | 5 saniye | Veri okuma süresi |
| Total Timeout | 10 saniye | Toplam istek süresi |

---

*Bu dokümantasyon Golsinyali API v1.0.0 için hazırlanmıştır.*
*Son güncelleme: 2024-12-27*
