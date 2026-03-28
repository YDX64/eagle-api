# Golsinyali API Documentation

**Version:** 1.0.0
**Base URL:** `https://api.golsinyali.com/api/v1` (Production)
**Local Development:** `http://localhost:8000/api/v1`

---

## Table of Contents

1. [Introduction](#introduction)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Response Format](#response-format)
5. [Error Handling](#error-handling)
6. [Endpoints](#endpoints)
   - [Match Endpoints](#match-endpoints)
   - [Live Match Endpoints](#live-match-endpoints)
   - [League Endpoints](#league-endpoints)
   - [Team Endpoints](#team-endpoints)
   - [Health & Admin Endpoints](#health--admin-endpoints)
7. [Data Models](#data-models)
8. [Caching Strategy](#caching-strategy)
9. [Best Practices](#best-practices)

---

## Introduction

Golsinyali API, yuksek performansli bir futbol mac verisi API'sidir. Coklu kaynak failover, akilli onbellekleme (caching) ve kapsamli analiz ozellikleri sunar.

### Key Features

- **Multi-Source Failover:** Birincil kaynak (nowgoal26.com) baskrisiz olursa otomatik olarak yedek kaynaga (goaloo.com) gecer
- **Hybrid Caching:** Redis + in-memory onbellekleme ile stale-while-revalidate modeli
- **Real-Time Data:** Canli mac verileri 30 saniyede bir guncellenir
- **Comprehensive Analysis:** Kafa kafaya istatistikleri, oran analizleri, tahminler ve takim performanslari

### Supported Data

| Veri Tipi | Aciklama | Guncelleme Sikligi |
|-----------|----------|-------------------|
| Match Details | Mac detaylari, takimlar, skorlar | 1-5 dakika |
| Live Matches | Canli maclar, anlik istatistikler | 30 saniye |
| H2H Statistics | Kafa kafaya istatistikler | 24 saat |
| Odds Data | Bahis oranlari | 15 dakika |
| League Data | Lig puan durumlari, fiksturler | 30 dakika - 1 saat |

---

## Authentication

API iki authentication yontemi destekler:

### 1. JWT Token Authentication

```bash
# 1. Token al
curl -X POST https://api.golsinyali.com/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-api-key"}'

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}

# 2. Token ile istek yap
curl https://api.golsinyali.com/api/v1/protected-endpoint \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 2. API Key Authentication

```bash
curl https://api.golsinyali.com/api/v1/protected-endpoint \
  -H "X-API-Key: your-api-key"
```

### Token Endpoint

#### `POST /auth/token`

JWT token olusturur.

**Request Body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `api_key` | string | Yes | API anahtariniz |

**Alternatif:** API key `X-API-Key` header ile de gonderilebilir.

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 400 | API key eksik |
| 403 | Gecersiz API key |

---

## Rate Limiting

API, asiri kullanimi onlemek icin rate limiting uygular.

### Limitler

| Limit | Deger | Periyot |
|-------|-------|---------|
| Dakika Limiti | 200 istek | 1 dakika |
| Saat Limiti | 3000 istek | 1 saat |

### Rate Limit Headers

Her response'ta asagidaki header'lar bulunur:

```
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 150
X-RateLimit-Reset: 1640995200
```

### Rate Limit Asildiginda

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "error": "Rate limit exceeded",
  "success": false
}
```

---

## Response Format

### Basarili Response

```json
{
  "data": { ... },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

### Hata Response

```json
{
  "error": "Error message",
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": false
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Istek basarili |
| 400 | Bad Request | Gecersiz parametre veya istek |
| 401 | Unauthorized | Authentication gerekli |
| 403 | Forbidden | Erisim reddedildi |
| 404 | Not Found | Kaynak bulunamadi |
| 429 | Too Many Requests | Rate limit asildi |
| 500 | Internal Server Error | Sunucu hatasi |
| 503 | Service Unavailable | Veri kaynaklari gecici olarak erisilemez |
| 504 | Gateway Timeout | Veri kaynagi timeout |

### Retry-After Header

503 ve 504 hatalari icin `Retry-After` header doner:

- **503:** `Retry-After: 60` (60 saniye sonra tekrar deneyin)
- **504:** `Retry-After: 30` (30 saniye sonra tekrar deneyin)

### Ornek Hata Responselari

```json
// 400 Bad Request
{
  "error": "Gecersiz tarih formati. YYYY-MM-DD formatini kullanin",
  "success": false
}

// 404 Not Found
{
  "error": "Match 123456 not found",
  "success": false
}

// 503 Service Unavailable
{
  "error": "Failed to fetch live data",
  "status_code": 503,
  "success": false
}
```

---

## Endpoints

---

### Match Endpoints

#### `GET /match/{match_id}`

Belirli bir macin detaylarini getirir. Takım bilgileri, istatistikler ve analiz icierir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID (ornek: 2804405) |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fields` | string | - | Donmesini istediginiz alanlar (virgullu liste) |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "home_team": "Manchester United",
    "away_team": "Liverpool",
    "home_score": 2,
    "away_score": 1,
    "match_time": "2024-12-29T15:00:00",
    "status": "finished",
    "league": {
      "id": 36,
      "name": "Premier League",
      "code": "EPL"
    },
    "analysis": {
      "h2h_summary": { ... },
      "prediction": { ... },
      "odds_analysis": { ... }
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:**
- Live maclar: 60 saniye
- Bitmis maclar: 24 saat
- Gelecek maclar: 5 dakika

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/match/2804405
```

---

#### `GET /match/{match_id}/h2h`

Belirli bir macin kafa kafaya (H2H) detaylarini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "h2h_details": {
      "head_to_head": [
        {
          "match_id": 2800001,
          "date": "2024-09-15",
          "home_team": "Manchester United",
          "away_team": "Liverpool",
          "home_score": 1,
          "away_score": 2,
          "league": "Premier League"
        }
      ],
      "home_team_recent": [ ... ],
      "away_team_recent": [ ... ],
      "standings": { ... },
      "injuries": [ ... ],
      "last_lineups": { ... }
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 24 saat

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/match/2804405/h2h
```

---

#### `GET /match/{match_id}/odds`

Belirli bir macin oran detaylarini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "odds_data": {
      "corner_odds": {
        "over_9.5": 1.85,
        "under_9.5": 1.95
      },
      "correct_score_odds": {
        "1-0": 6.50,
        "2-1": 8.00,
        "0-0": 10.00
      },
      "double_chance_odds": {
        "1X": 1.35,
        "X2": 1.45,
        "12": 1.20
      },
      "first_half_odds": {
        "home": 3.50,
        "draw": 2.10,
        "away": 3.80
      },
      "odds_comp": {
        "bet365": { "home": 2.10, "draw": 3.50, "away": 3.20 },
        "pinnacle": { "home": 2.15, "draw": 3.45, "away": 3.25 }
      }
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 15 dakika

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/match/2804405/odds
```

---

#### `GET /matches/date/{date}`

Belirli bir tarihteki maclari getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `date` | string | Tarih (YYYY-MM-DD formati) |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by_time` | boolean | true | Maclari saate gore sirala |

**Response:**

```json
{
  "data": {
    "date": "2024-12-29",
    "matches": [
      {
        "match_id": 2804405,
        "home_team": "Manchester United",
        "away_team": "Liverpool",
        "match_time": "2024-12-29T15:00:00",
        "status": "scheduled",
        "league_id": 36,
        "league_name": "Premier League"
      }
    ],
    "leagues": {
      "36": {
        "league_name": "Premier League",
        "league_code": "EPL"
      }
    },
    "total_matches": 45
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 5 dakika

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/date/2024-12-29
curl "https://api.golsinyali.com/api/v1/matches/date/2024-12-29?sort_by_time=false"
```

---

#### `GET /matches/today`

Bugunku maclari getirir. `/matches/date/{today}` endpoint'inin kisa yoludur.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by_time` | boolean | true | Maclari saate gore sirala |

**Cache TTL:** 1 dakika

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/today
```

---

#### `GET /matches/tomorrow`

Yarinki maclari getirir.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by_time` | boolean | true | Maclari saate gore sirala |

**Cache TTL:** 5 dakika

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/tomorrow
```

---

#### `GET /matches/yesterday`

Dunku maclari getirir.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by_time` | boolean | true | Maclari saate gore sirala |

**Cache TTL:** 24 saat

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/yesterday
```

---

### Live Match Endpoints

#### `GET /matches/live`

Tum canli maclari gercek zamanli istatistikler ve oranlarla getirir.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_stats` | boolean | true | Teknik istatistikleri dahil et |
| `include_odds` | boolean | true | Canli oranlari dahil et |
| `include_corners` | boolean | false | Korner istatistiklerini dahil et |
| `league_id` | integer | - | Lig ID'sine gore filtrele |
| `only_live` | boolean | false | Sadece canli maclari getir (yaklasan maclari haric tut) |

**Response:**

```json
{
  "data": {
    "matches": [
      {
        "match_id": 2804405,
        "home_team": "Manchester United",
        "away_team": "Liverpool",
        "home_score": 1,
        "away_score": 0,
        "minute": 34,
        "status": "1H",
        "is_live": true,
        "league_id": 36,
        "stats": {
          "possession": { "home": 55, "away": 45 },
          "shots": { "home": 8, "away": 5 },
          "shots_on_target": { "home": 4, "away": 2 },
          "corners": { "home": 3, "away": 1 },
          "fouls": { "home": 7, "away": 9 }
        },
        "odds": {
          "asian_handicap": { "home": 1.95, "line": -0.5, "away": 1.85 },
          "over_under": { "over": 1.90, "line": 2.5, "under": 1.90 },
          "match_result": { "home": 2.10, "draw": 3.50, "away": 3.20 }
        }
      }
    ],
    "leagues": {
      "36": { "name": "Premier League", "code": "EPL" }
    },
    "meta": {
      "total_matches": 15,
      "live_count": 8,
      "last_update": "2024-12-29T10:30:00.000Z",
      "cache_ttl": 30
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 saniye

**Example:**

```bash
# Tum canli maclar
curl https://api.golsinyali.com/api/v1/matches/live

# Sadece canli maclar (yaklasan haric)
curl "https://api.golsinyali.com/api/v1/matches/live?only_live=true"

# Belirli lig
curl "https://api.golsinyali.com/api/v1/matches/live?league_id=36"

# Korner istatistikleri ile
curl "https://api.golsinyali.com/api/v1/matches/live?include_corners=true"
```

---

#### `GET /matches/live/{match_id}`

Belirli bir canli macin detaylarini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "home_team": "Manchester United",
    "away_team": "Liverpool",
    "home_score": 1,
    "away_score": 0,
    "minute": 34,
    "status": "1H",
    "stats": { ... },
    "odds": { ... },
    "events": [ ... ]
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 saniye

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/live/2804405
```

---

#### `GET /matches/live/{match_id}/stats`

Belirli bir canli macin teknik istatistiklerini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "stats": {
      "shots": { "home": 12, "away": 8 },
      "shots_on_target": { "home": 5, "away": 3 },
      "shots_off_target": { "home": 7, "away": 5 },
      "possession": { "home": 58, "away": 42 },
      "corners": { "home": 6, "away": 3 },
      "fouls": { "home": 10, "away": 12 },
      "yellow_cards": { "home": 1, "away": 2 },
      "red_cards": { "home": 0, "away": 0 },
      "attacks": { "home": 45, "away": 32 },
      "dangerous_attacks": { "home": 28, "away": 18 },
      "passes": { "home": 320, "away": 245 },
      "pass_accuracy": { "home": 85, "away": 78 }
    },
    "cache_ttl": 30
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 saniye

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/live/2804405/stats
```

---

#### `GET /matches/live/{match_id}/odds`

Belirli bir canli macin oranlarini getirir (Bet365 kaynagli).

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "odds": {
      "asian_handicap": {
        "home": 1.95,
        "line": -0.5,
        "away": 1.85
      },
      "match_result": {
        "home": 2.10,
        "draw": 3.50,
        "away": 3.20
      },
      "over_under": {
        "over": 1.90,
        "line": 2.5,
        "under": 1.90
      },
      "both_teams_to_score": {
        "yes": 1.75,
        "no": 2.05
      },
      "double_chance": {
        "1X": 1.35,
        "X2": 1.50,
        "12": 1.25
      }
    },
    "bookmaker": "Bet365",
    "cache_ttl": 15
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 15 saniye

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/live/2804405/odds
```

---

#### `GET /matches/live/{match_id}/corners`

Belirli bir canli macin korner istatistiklerini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "corners": {
      "total": {
        "home": 6,
        "away": 3
      },
      "first_half": {
        "home": 4,
        "away": 2
      },
      "odds": {
        "over_9.5": 1.85,
        "under_9.5": 1.95,
        "handicap": {
          "home": 1.90,
          "line": -2.5,
          "away": 1.90
        }
      }
    },
    "cache_ttl": 30
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 saniye

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/live/2804405/corners
```

---

#### `GET /matches/live/{match_id}/events`

Belirli bir canli macin olaylarini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `match_id` | integer | Mac ID |

**Response:**

```json
{
  "data": {
    "match_id": 2804405,
    "events": [
      {
        "minute": 23,
        "type": "goal",
        "team": "home",
        "player": "Marcus Rashford",
        "assist": "Bruno Fernandes",
        "score": "1-0"
      },
      {
        "minute": 34,
        "type": "yellow_card",
        "team": "away",
        "player": "Mohamed Salah"
      },
      {
        "minute": 45,
        "type": "substitution",
        "team": "home",
        "player_in": "Antony",
        "player_out": "Jadon Sancho"
      }
    ],
    "cache_ttl": 30
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Event Types:**
- `goal` - Gol
- `own_goal` - Kendi kalesine gol
- `penalty_goal` - Penalti golu
- `penalty_missed` - Kacirilan penalti
- `yellow_card` - Sari kart
- `red_card` - Kirmizi kart
- `second_yellow` - Ikinci sari (kirmizi)
- `substitution` - Oyuncu degisikligi
- `var_decision` - VAR karari

**Cache TTL:** 30 saniye

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/matches/live/2804405/events
```

---

### League Endpoints

#### `GET /leagues`

Bugunku maclardan ligleri listeler.

**Response:**

```json
{
  "data": {
    "leagues": [
      { "id": "36", "name": "Premier League", "code": "EPL" },
      { "id": "37", "name": "La Liga", "code": "LAS" },
      { "id": "38", "name": "Serie A", "code": "SAI" }
    ],
    "count": 25
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/leagues
```

---

#### `GET /leagues/all`

Tum ligleri ulkelere gore organize edilmis sekilde getirir.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `country` | string | - | Ulke koduna gore filtrele (ornek: 'england', 'turkey') |
| `type` | string | - | Tur'e gore filtrele ('league', 'subleague', 'cup') |

**Response:**

```json
{
  "data": {
    "metadata": {
      "total_leagues": 450,
      "total_cups": 85,
      "last_updated": "2024-12-29"
    },
    "top_leagues": [
      { "id": 36, "name": "Premier League", "country": "England" },
      { "id": 37, "name": "La Liga", "country": "Spain" }
    ],
    "cups": [
      { "id": 103, "name": "UEFA Champions League" },
      { "id": 113, "name": "UEFA Europa League" }
    ],
    "leagues": {
      "england": [
        { "id": 36, "name": "Premier League", "type": "league" },
        { "id": 37, "name": "Championship", "type": "league" }
      ],
      "spain": [
        { "id": 37, "name": "La Liga", "type": "league" }
      ]
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
# Tum ligler
curl https://api.golsinyali.com/api/v1/leagues/all

# Sadece Ingiltere ligleri
curl "https://api.golsinyali.com/api/v1/leagues/all?country=england"

# Sadece kupalar
curl "https://api.golsinyali.com/api/v1/leagues/all?type=cup"
```

---

#### `GET /leagues/top`

Populer ligleri (Big 5 + buyuk kupalar) getirir.

**Response:**

```json
{
  "data": {
    "top_leagues": [
      { "id": 36, "name": "Premier League", "country": "England" },
      { "id": 37, "name": "La Liga", "country": "Spain" },
      { "id": 38, "name": "Serie A", "country": "Italy" },
      { "id": 39, "name": "Bundesliga", "country": "Germany" },
      { "id": 40, "name": "Ligue 1", "country": "France" }
    ],
    "major_cups": [
      { "id": 103, "name": "UEFA Champions League" },
      { "id": 113, "name": "UEFA Europa League" }
    ],
    "count": 10
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/leagues/top
```

---

#### `GET /leagues/countries`

Lig bulunan ulkeleri listeler.

**Response:**

```json
{
  "data": {
    "countries": [
      { "code": "england", "name": "England", "league_count": 12 },
      { "code": "spain", "name": "Spain", "league_count": 8 },
      { "code": "turkey", "name": "Turkey", "league_count": 5 }
    ],
    "count": 45
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/leagues/countries
```

---

#### `GET /leagues/{league_id}/lookup`

Lig ID'sine gore lig detaylarini arar.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Response:**

```json
{
  "data": {
    "league": {
      "id": 36,
      "name": "Premier League",
      "country": "england",
      "type": "league"
    },
    "found_in": "top_leagues"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/leagues/36/lookup
```

---

#### `GET /leagues/{league_id}/info`

Lig bilgisi ve alt ligleri getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Response:**

```json
{
  "data": {
    "league_id": 36,
    "code": "EPL",
    "name": "Premier League",
    "type": "league",
    "country": "England",
    "country_flag": "https://example.com/england.png",
    "has_subleague": false,
    "available_seasons": ["2024-2025", "2023-2024", "2022-2023"],
    "current_season": "2024-2025",
    "is_cup": false,
    "data_source": "master_data"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 24 saat

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/leagues/36/info
```

---

#### `GET /leagues/{league_id}/standings`

Lig puan durumunu getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `season` | string | Yes | - | Sezon (ornek: '2024-2025') |
| `type` | string | No | overall | 'overall', 'home', veya 'away' |
| `sub_league_id` | integer | No | - | Alt lig ID (grubu olan ligler icin) |

**Response:**

```json
{
  "data": {
    "league": {
      "id": 36,
      "name": "Premier League"
    },
    "sub_league": {
      "id": 918,
      "name": "Premier League 2024-25"
    },
    "sub_league_id": 918,
    "standings_type": "overall",
    "standings": [
      {
        "position": 1,
        "team_id": 14,
        "team_name": "Liverpool",
        "played": 17,
        "won": 12,
        "drawn": 4,
        "lost": 1,
        "goals_for": 40,
        "goals_against": 15,
        "goal_difference": 25,
        "points": 40
      }
    ],
    "teams_count": 20,
    "zones": {
      "champions_league": [1, 2, 3, 4],
      "europa_league": [5],
      "conference_league": [6],
      "relegation": [18, 19, 20]
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 dakika

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/standings?season=2024-2025"
curl "https://api.golsinyali.com/api/v1/leagues/36/standings?season=2024-2025&type=home"
```

---

#### `GET /leagues/{league_id}/matches`

Lig maclarini (haftalik) getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `season` | string | Yes | - | Sezon (ornek: '2024-2025') |
| `round` | integer | No | - | Hafta numarasi (belirtilmezse tum haftalar) |
| `sub_league_id` | integer | No | - | Alt lig ID |

**Response:**

```json
{
  "data": {
    "league": {
      "id": 36,
      "name": "Premier League"
    },
    "sub_league": {
      "id": 918,
      "name": "Premier League 2024-25"
    },
    "season": "2024-2025",
    "round": 17,
    "total_rounds": 38,
    "matches": [
      {
        "match_id": 2804405,
        "round": 17,
        "date": "2024-12-29",
        "time": "15:00",
        "home_team": "Manchester United",
        "home_team_id": 33,
        "away_team": "Liverpool",
        "away_team_id": 14,
        "home_score": null,
        "away_score": null,
        "status": "scheduled"
      }
    ],
    "match_count": 10,
    "is_cup": false
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 1 saat

**Example:**

```bash
# Tum haftalar
curl "https://api.golsinyali.com/api/v1/leagues/36/matches?season=2024-2025"

# Belirli hafta
curl "https://api.golsinyali.com/api/v1/leagues/36/matches?season=2024-2025&round=17"
```

---

#### `GET /leagues/{league_id}/full`

Tam lig verisini getirir (puan durumu + tum maclar).

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `season` | string | Yes | Sezon (ornek: '2024-2025') |

**Response:**

```json
{
  "data": {
    "league": { ... },
    "sub_league": { ... },
    "sub_league_id": 918,
    "teams": { ... },
    "standings": {
      "overall": [ ... ],
      "home": [ ... ],
      "away": [ ... ]
    },
    "rounds": {
      "1": [ ... ],
      "2": [ ... ]
    },
    "zones": { ... },
    "total_matches": 380
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 dakika

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/full?season=2024-2025"
```

---

#### `GET /leagues/{league_id}/current-round`

Ligin guncel/son haftasini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `season` | string | Yes | Sezon |

**Response:**

```json
{
  "data": {
    "league_id": 36,
    "sub_league_id": 918,
    "season": "2024-2025",
    "current_round": 17,
    "next_round": 18,
    "last_completed_round": 16,
    "total_rounds": 38,
    "season_completed": false
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 5 dakika

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/current-round?season=2024-2025"
```

---

#### `GET /leagues/{league_id}/team-stats`

Lig takim istatistiklerini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `season` | string | Yes | - | Sezon |
| `type` | string | No | total | 'total', 'home', veya 'guest' |

**Response:**

```json
{
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "stats_type": "Total",
    "teams": [
      {
        "team_id": "14",
        "team_name": "Liverpool",
        "schsum": 17,
        "shots": 215,
        "target": 85,
        "offtarget": 130,
        "passball": 8500,
        "passballsuc": 7200,
        "yellow": 25,
        "red": 1,
        "corner": 95,
        "expectedgoals": 38.5,
        "avgcontrol": 62.5
      }
    ],
    "team_count": 20
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 1 saat

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/team-stats?season=2024-2025"
```

---

#### `GET /leagues/{league_id}/player-stats`

Lig oyuncu istatistiklerini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `season` | string | Yes | - | Sezon |
| `category` | string | No | offensive | 'offensive', 'passing', 'defensive', 'summary' |

**Response:**

```json
{
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "category": "offensive",
    "players": [
      {
        "player_id": 1234,
        "player_name": "Mohamed Salah",
        "team_id": 14,
        "team_name": "Liverpool",
        "matches": 17,
        "minutes": 1450,
        "rating": 8.2,
        "goals": 15,
        "non_penalty_goals": 12,
        "penalty_goals": 3,
        "shots": 52,
        "shots_on_target": 28,
        "assists": 10,
        "key_passes": 45,
        "passes": 580,
        "pass_accuracy": 82.5
      }
    ],
    "player_count": 100
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 1 saat

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/player-stats?season=2024-2025"
```

---

#### `GET /leagues/{league_id}/handicap-stats`

Lig Asian Handicap ve Ust/Alt istatistiklerini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `league_id` | integer | Lig ID |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `season` | string | Yes | Sezon |

**Response:**

```json
{
  "data": {
    "league_id": 36,
    "season": "2024-2025",
    "total_ah": [ ... ],
    "home_ah": [ ... ],
    "guest_ah": [ ... ],
    "summary": {
      "total_matches": 170,
      "total_goals": 450,
      "avg_goals": 2.65,
      "over_count": 95,
      "under_count": 75
    }
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Cache TTL:** 30 dakika

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/leagues/36/handicap-stats?season=2024-2025"
```

---

### Team Endpoints

#### `GET /teams/search`

Takim arar.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Arama sorgusu (takim adi) |

**Response:**

```json
{
  "data": {
    "query": "liverpool",
    "teams": [
      {
        "name": "Liverpool",
        "type": "home_team",
        "match_id": 2804405,
        "league": "Premier League",
        "league_id": 36
      }
    ],
    "count": 1
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl "https://api.golsinyali.com/api/v1/teams/search?q=liverpool"
```

---

#### `GET /teams/{team_name}/matches`

Belirli bir takimin maclarini getirir.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `team_name` | string | Takim adi |

**Response:**

```json
{
  "data": {
    "team_name": "Liverpool",
    "matches": [
      {
        "match_id": 2804405,
        "home_team": "Manchester United",
        "away_team": "Liverpool",
        "match_time": "2024-12-29T15:00:00",
        "league": {
          "id": 36,
          "name": "Premier League",
          "code": "EPL"
        },
        "is_home": false
      }
    ],
    "count": 5
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/teams/Liverpool/matches
```

---

### Health & Admin Endpoints

#### `GET /health`

Temel saglik kontrolu.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-12-29T10:30:00.000Z",
  "version": "1.0.0"
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/health
```

---

#### `GET /health/detailed`

Detayli saglik kontrolu.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-12-29T10:30:00.000Z",
  "version": "1.0.0",
  "cache": "enabled",
  "cache_info": {
    "type": "redis",
    "timeout": 1800
  },
  "session": "managed by http_client",
  "background_tasks": {
    "cache_cleanup": "running",
    "log_rotation": "running"
  }
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/health/detailed
```

---

#### `GET /cache/status`

Cache konfigurasyonunu gosterir.

**Response:**

```json
{
  "data": {
    "cache_type": "redis",
    "redis_host": "localhost",
    "redis_port": 6379,
    "default_timeout": 1800,
    "status": "active"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/cache/status
```

---

#### `GET /cache/stats`

Cache performans istatistiklerini gosterir.

**Response:**

```json
{
  "data": {
    "hits": 15420,
    "misses": 3280,
    "hit_rate": 82.45,
    "stale_served": 450,
    "background_refreshes": 1200,
    "refresh_failures": 15,
    "dedup_hits": 890,
    "active_background_refreshes": 2,
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Metric Descriptions:**

| Metric | Description |
|--------|-------------|
| `hits` | Cache hit sayisi (cache'ten sunulan) |
| `misses` | Cache miss sayisi (upstream'den cekilen) |
| `hit_rate` | Cache hit orani (%) |
| `stale_served` | Stale veri sunulma sayisi |
| `background_refreshes` | Arka plan yenileme sayisi |
| `refresh_failures` | Basarisiz yenileme sayisi |
| `dedup_hits` | Deduplicate edilen istek sayisi |

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/cache/stats
```

---

#### `POST /cache/clear`

Cache'i temizler.

**Response:**

```json
{
  "data": {
    "message": "Cache basariyla temizlendi",
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl -X POST https://api.golsinyali.com/api/v1/cache/clear
```

---

#### `POST /cache/stats/reset`

Cache istatistiklerini sifirlar.

**Response:**

```json
{
  "data": {
    "message": "Cache istatistikleri sifirlandi",
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl -X POST https://api.golsinyali.com/api/v1/cache/stats/reset
```

---

#### `GET /sources/health`

Veri kaynagi saglik metriklerini gosterir.

**Response:**

```json
{
  "data": {
    "sources": {
      "https://live3.nowgoal26.com": {
        "total_requests": 15000,
        "successful_requests": 14500,
        "failed_requests": 500,
        "error_rate": 0.0333,
        "priority_score": 0.95,
        "consecutive_failures": 0,
        "last_error_type": "timeout",
        "last_error_time": "2024-12-29T09:15:00.000Z",
        "is_primary": true
      },
      "https://www.goaloo.com": {
        "total_requests": 500,
        "successful_requests": 480,
        "failed_requests": 20,
        "error_rate": 0.04,
        "priority_score": 0.90,
        "consecutive_failures": 0,
        "is_primary": false
      }
    },
    "summary": {
      "total_requests": 15500,
      "total_failures": 520,
      "overall_error_rate": 0.0335,
      "primary_source": "https://live3.nowgoal26.com",
      "total_sources": 2
    },
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl https://api.golsinyali.com/api/v1/sources/health
```

---

#### `POST /sources/force-primary`

Birincil kaynagi manuel olarak degistirir.

**Request Body:**

```json
{
  "source_url": "https://www.goaloo.com"
}
```

**Response:**

```json
{
  "data": {
    "message": "Primary source forced to https://www.goaloo.com",
    "new_primary": "https://www.goaloo.com",
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
curl -X POST https://api.golsinyali.com/api/v1/sources/force-primary \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://www.goaloo.com"}'
```

---

#### `POST /sources/reset-metrics`

Kaynak metriklerini sifirlar.

**Request Body (Optional):**

```json
{
  "source_url": "https://www.goaloo.com"
}
```

Belirtilmezse tum kaynaklar sifirlanir.

**Response:**

```json
{
  "data": {
    "message": "Metrics reset for all sources",
    "timestamp": "2024-12-29T10:30:00.000Z"
  },
  "timestamp": "2024-12-29T10:30:00.000Z",
  "success": true
}
```

**Example:**

```bash
# Tum kaynaklari sifirla
curl -X POST https://api.golsinyali.com/api/v1/sources/reset-metrics

# Belirli kaynagi sifirla
curl -X POST https://api.golsinyali.com/api/v1/sources/reset-metrics \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://www.goaloo.com"}'
```

---

## Data Models

### Match Object

```json
{
  "match_id": 2804405,
  "home_team": "Manchester United",
  "away_team": "Liverpool",
  "home_team_id": 33,
  "away_team_id": 14,
  "home_score": 2,
  "away_score": 1,
  "home_ht_score": 1,
  "away_ht_score": 0,
  "match_time": "2024-12-29T15:00:00",
  "status": "finished",
  "minute": null,
  "league_id": 36,
  "league_name": "Premier League",
  "league_code": "EPL",
  "round": 17,
  "season": "2024-2025"
}
```

### Match Status Values

| Status | Description |
|--------|-------------|
| `scheduled` | Mac henuz baslamadi |
| `1H` | Ilk yari |
| `HT` | Devre arasi |
| `2H` | Ikinci yari |
| `ET` | Uzatma |
| `PEN` | Penaltilar |
| `finished` | Mac bitti |
| `postponed` | Ertelendi |
| `cancelled` | Iptal edildi |
| `abandoned` | Yarida kaldi |

### League Object

```json
{
  "id": 36,
  "name": "Premier League",
  "code": "EPL",
  "country": "England",
  "type": "league",
  "has_subleague": false
}
```

### Standing Object

```json
{
  "position": 1,
  "team_id": 14,
  "team_name": "Liverpool",
  "played": 17,
  "won": 12,
  "drawn": 4,
  "lost": 1,
  "goals_for": 40,
  "goals_against": 15,
  "goal_difference": 25,
  "points": 40
}
```

### Live Stats Object

```json
{
  "possession": { "home": 55, "away": 45 },
  "shots": { "home": 12, "away": 8 },
  "shots_on_target": { "home": 5, "away": 3 },
  "shots_off_target": { "home": 7, "away": 5 },
  "corners": { "home": 6, "away": 3 },
  "fouls": { "home": 10, "away": 12 },
  "yellow_cards": { "home": 1, "away": 2 },
  "red_cards": { "home": 0, "away": 0 },
  "attacks": { "home": 45, "away": 32 },
  "dangerous_attacks": { "home": 28, "away": 18 },
  "passes": { "home": 320, "away": 245 },
  "pass_accuracy": { "home": 85, "away": 78 }
}
```

### Odds Object

```json
{
  "asian_handicap": {
    "home": 1.95,
    "line": -0.5,
    "away": 1.85
  },
  "match_result": {
    "home": 2.10,
    "draw": 3.50,
    "away": 3.20
  },
  "over_under": {
    "over": 1.90,
    "line": 2.5,
    "under": 1.90
  },
  "both_teams_to_score": {
    "yes": 1.75,
    "no": 2.05
  }
}
```

### Event Object

```json
{
  "minute": 23,
  "type": "goal",
  "team": "home",
  "player": "Marcus Rashford",
  "assist": "Bruno Fernandes",
  "score": "1-0"
}
```

---

## Caching Strategy

### Cache TTL Values

| Data Type | TTL | Description |
|-----------|-----|-------------|
| Live Matches | 30s | Canli mac verileri |
| Live Odds | 15s | Canli oranlar |
| Live Stats | 30s | Canli istatistikler |
| Today Matches | 1 min | Bugunku maclar |
| Future Matches | 5 min | Gelecek maclar |
| Finished Matches | 24 hours | Bitmis maclar |
| H2H Data | 24 hours | Kafa kafaya istatistikler |
| Odds Data | 15 min | Oran verileri |
| League Standings | 30 min | Puan durumlari |
| League Matches | 1 hour | Lig maclari |
| Player Stats | 1 hour | Oyuncu istatistikleri |
| Team Stats | 1 hour | Takim istatistikleri |
| League Info | 24 hours | Lig bilgisi |

### Stale-While-Revalidate

API, stale-while-revalidate modeli kullanir:

1. Cache'te veri varsa (taze veya bayat) hemen doner
2. Bayatsa arka planda yenileme baslatilir
3. Kullanici beklemez, eski veri alinir
4. Sonraki istek taze veriyi alir

### Request Deduplication

Ayni anda gelen ayni istekler icin tek upstream istegi yapilir:

```
Request 1: /match/123 → Upstream fetch baslatilir
Request 2: /match/123 → Bekler (duplicate)
Request 3: /match/123 → Bekler (duplicate)

Upstream response gelince:
Request 1, 2, 3 → Ayni response doner
```

---

## Best Practices

### 1. Cache-Friendly Requests

```bash
# Cache'i etkin kullanmak icin consistent parametreler kullanin
curl "https://api.golsinyali.com/api/v1/matches/live?include_stats=true"

# Her seferinde farkli parametreler cache'i bosaltir
# YANLIS:
curl "https://api.golsinyali.com/api/v1/matches/live?include_stats=true&include_odds=true"
curl "https://api.golsinyali.com/api/v1/matches/live?include_stats=true"
```

### 2. Rate Limit Management

```python
import time
import requests

def fetch_with_retry(url, max_retries=3):
    for i in range(max_retries):
        response = requests.get(url)

        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            time.sleep(retry_after)
            continue

        return response

    raise Exception("Max retries exceeded")
```

### 3. Error Handling

```python
import requests

def fetch_match(match_id):
    try:
        response = requests.get(f"https://api.golsinyali.com/api/v1/match/{match_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Match {match_id} not found")
        elif e.response.status_code == 503:
            retry_after = e.response.headers.get('Retry-After', 60)
            print(f"Service unavailable, retry after {retry_after}s")
        elif e.response.status_code == 504:
            print("Gateway timeout, try again later")
        raise
```

### 4. Efficient Polling

```python
import time

def poll_live_matches(interval=30):
    """
    30 saniyede bir canli maclari kontrol et.
    Cache TTL 30 saniye oldugu icin daha sik sorgulamaya gerek yok.
    """
    while True:
        response = requests.get(
            "https://api.golsinyali.com/api/v1/matches/live",
            params={"only_live": "true"}
        )

        if response.ok:
            data = response.json()
            process_live_matches(data['data']['matches'])

        time.sleep(interval)
```

### 5. Batch Processing

```python
import concurrent.futures

def fetch_multiple_matches(match_ids):
    """
    Birden fazla maci paralel olarak cek.
    Rate limit'e dikkat et.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_match, mid): mid
            for mid in match_ids
        }

        results = {}
        for future in concurrent.futures.as_completed(futures):
            match_id = futures[future]
            try:
                results[match_id] = future.result()
            except Exception as e:
                results[match_id] = {"error": str(e)}

        return results
```

---

## Changelog

### v1.0.0 (2024-12-29)

- Initial API release
- Match endpoints (details, H2H, odds)
- Live match endpoints (stats, odds, corners, events)
- League endpoints (standings, matches, stats)
- Team endpoints (search, matches)
- Health and admin endpoints
- Multi-source failover system
- Redis caching with stale-while-revalidate
- Rate limiting (200/min, 3000/hour)

---

## Support

For issues or questions:

- GitHub Issues: https://github.com/golsinyali/api/issues
- Email: api@golsinyali.com

---

*Document generated: 2024-12-29*
