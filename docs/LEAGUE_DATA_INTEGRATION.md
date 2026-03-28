# Golsinyali API — Lig & Kupa Verisi Entegrasyon Kılavuzu

**Base URL:** `https://api.golsinyali.com/api/v1`
**Auth:** Her istekte `X-API-Key: <api_key>` header'ı zorunlu.

---

## İçindekiler

1. [Genel Kavramlar](#1-genel-kavramlar)
2. [Yanıt Yapısı](#2-yanıt-yapısı)
3. [Endpoint Referansı](#3-endpoint-referansı)
   - [Standings — Puan Durumu](#31-standings--puan-durumu)
   - [Matches — Maçlar](#32-matches--maçlar)
   - [Full — Tam Veri](#33-full--tam-veri)
   - [Info — Lig Bilgisi](#34-info--lig-bilgisi)
   - [Team Stats — Takım İstatistikleri](#35-team-stats--takım-istatistikleri)
   - [Player Stats — Oyuncu İstatistikleri](#36-player-stats--oyuncu-istatistikleri)
   - [Handicap Stats — Asya Handikap](#37-handicap-stats--asya-handikap)
   - [Current Round — Güncel Hafta](#38-current-round--güncel-hafta)
4. [Lig vs Kupa Farkları](#4-lig-vs-kupa-farkları)
5. [Sezon Formatları](#5-sezon-formatları)
6. [Logo & Görsel URL'leri](#6-logo--görsel-urleri)
7. [Entegrasyon Örnekleri](#7-entegrasyon-örnekleri)
8. [Hata Yönetimi](#8-hata-yönetimi)
9. [Cache & Performans](#9-cache--performans)
10. [Önemli Lig ID'leri](#10-önemli-lig-idleri)

---

## 1. Genel Kavramlar

### Lig mi, Kupa mı?
API iki tür yarışmayı destekler:

| Tür | `is_cup` | Özellikler |
|-----|----------|-----------|
| **Lig** | `false` | Puan durumu, haftalık maçlar, ev/deplasman tablosu |
| **Kupa** | `true` | Tur bazlı maçlar, eleme/grup aşamaları, standings yok |

Bir yarışmanın kupa olup olmadığını `is_cup` alanından veya `league.type === "cup"` kontrolünden anlayabilirsiniz.

### Sub-League (Alt Lig)
Bazı ligler birden fazla alt bölüme sahiptir (örn. Suudi Arabistan'da "Lig" ve alt kategoriler). Bu durumda:
- API `sub_league_id` döner (örn. `918`)
- Cache key bu ID'yi içerir
- Genellikle sorguda belirtmenize gerek yoktur; API otomatik tespit eder

---

## 2. Yanıt Yapısı

Tüm başarılı yanıtlar şu formattadır:

```json
{
  "success": true,
  "timestamp": "2026-02-20T10:00:00.000000",
  "data": {
    "cached": true,
    "cache_hit": true,
    "stale": false,
    ...
  }
}
```

Hata yanıtı:

```json
{
  "success": false,
  "error": "Hata mesajı",
  "status_code": 404,
  "timestamp": "2026-02-20T10:00:00.000000"
}
```

**Cache alanları** (`data` içinde):
- `cached: true` — yanıt cache'den geldi
- `cache_hit: true` — aynı anlama gelir
- `stale: true` — cache süresi dolmuş ama arka planda yenileniyor (eski veri döndü)

---

## 3. Endpoint Referansı

### 3.1 Standings — Puan Durumu

```
GET /leagues/{id}/standings?season=2024-2025
GET /leagues/{id}/standings?season=2024-2025&type=home
GET /leagues/{id}/standings?season=2024-2025&type=away
```

**Query Parametreleri:**

| Parametre | Zorunlu | Değerler | Açıklama |
|-----------|---------|----------|---------|
| `season` | ✅ | `2024-2025` | Sezon (bkz. §5) |
| `type` | ❌ | `overall` `home` `away` | Tablo türü (varsayılan: `overall`) |
| `sub_league_id` | ❌ | number | Alt lig ID'si (kupalar için özel aşama) |

**Yanıt `data` alanları:**

```json
{
  "league": {
    "id": 36,
    "name": "English Premier League",
    "season": "2024-2025",
    "color": "#FF3333"
  },
  "sub_league": {
    "id": null,
    "name": "League",
    "total_rounds": 38,
    "total_teams": 20
  },
  "sub_league_id": null,
  "standings_type": "overall",
  "standings": [
    {
      "rank": 1,
      "team_id": 25,
      "team_name": "Liverpool",
      "team_logo": "images/1jq85dyw7v2x.png",
      "played": 38,
      "won": 25,
      "drawn": 9,
      "lost": 4,
      "goals_for": 86,
      "goals_against": 41,
      "goal_difference": 45,
      "points": 84,
      "win_percentage": 65.8,
      "zone": 0
    }
  ],
  "teams_count": 20,
  "zones": {
    "promotion": [],
    "playoff": [],
    "relegation": [22, 23, 24]
  }
}
```

**`zone` değerleri:**
- `1` → Şampiyonlar Ligi / promosyon bölgesi
- `0` → Orta sıra
- `-1` → Küme düşme bölgesi

**`zones` alanı:** Hangi sıraların hangi bölgede olduğunu ranklar listesi olarak verir (örn. `relegation: [22, 23, 24]` = 22., 23., 24. sıralar küme düşme).

> **Not:** Kupalar (is_cup=true) standings döndürmez — `standings: []` boş gelir.

**Cache TTL:** 12 saat

---

### 3.2 Matches — Maçlar

```
GET /leagues/{id}/matches?season=2024-2025
GET /leagues/{id}/matches?season=2024-2025&round=1
```

**Query Parametreleri:**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|---------|
| `season` | ✅ | Sezon |
| `round` | ❌ | Belirli bir hafta/tur numarası |
| `sub_league_id` | ❌ | Alt lig ID'si |

**Yanıt (TÜM haftalar — round belirtilmemişse):**

```json
{
  "league": { "id": 36, "name": "English Premier League", "season": "2024-2025", "color": "#FF3333" },
  "sub_league": { "id": null, "name": "League", "total_rounds": 38, "total_teams": 20 },
  "sub_league_id": null,
  "season": "2024-2025",
  "round": null,
  "total_rounds": 38,
  "is_cup": false,
  "match_count": 380,
  "rounds": {
    "1": [
      {
        "match_id": 2700001,
        "datetime": "2024-08-17 14:00",
        "status": "finished",
        "match_type": "round",
        "home_team": { "id": 25, "name": "Liverpool", "logo": "images/...", "rank": 1 },
        "away_team": { "id": 19, "name": "Arsenal", "logo": "images/...", "rank": 2 },
        "score": { "full_time": "2-0", "half_time": "1-0" }
      }
    ],
    "2": [ ... ],
    "38": [ ... ]
  },
  "matches": null
}
```

**Yanıt (belirli hafta — round=1):**

```json
{
  "round": 1,
  "matches": [ { ...maç... }, { ...maç... } ],
  "rounds": null,
  "match_count": 10
}
```

**`status` değerleri:**
- `"finished"` → Bitmiş maç
- `"not_started"` → Başlamamış
- `"live"` → Canlı (dakika bilgisi için `/matches/live/{id}` kullanın)

**Kupa maçları için ek alanlar:**

```json
{
  "is_cup": true,
  "cup_rounds": {
    "25696": { "id": 25696, "name": "Round 1", "name_cn": "第一圈", "type": 0 },
    "25777": { "id": 25777, "name": "Round 2", "name_cn": "第二圈", "type": 0 },
    "26358": { "id": 26358, "name": "Semifinal", "name_cn": "准决赛", "type": 0 },
    "26525": { "id": 26525, "name": "Finals",    "name_cn": "决赛",   "type": 0 }
  },
  "rounds": {
    "25696": [
      {
        "match_id": 2642561,
        "datetime": "2024-08-03 22:00",
        "status": "finished",
        "match_type": "cup",
        "round_name": "Round 1",
        "home_team": { "id": 39107, "name": "Ossett United", "logo": "images/..." },
        "away_team": { "id": 27832, "name": "Widnes",        "logo": "images/..." },
        "score": { "full_time": "0-1", "half_time": "0-0" }
      }
    ]
  }
}
```

> **Önemli:** Kupa `rounds` dict'inin keyleri, hafta numarası değil `cup_rounds` ID'leridir (25696, 25777...). Görüntülemede `cup_rounds[id].name` kullanın.

**Cache TTL:** 48 saat

---

### 3.3 Full — Tam Veri

```
GET /leagues/{id}/full?season=2024-2025
```

Standings + matches tek istekte. Büyük payload döner.

**Yanıt `data` alanları:** `league`, `sub_league`, `sub_league_id`, `teams`, `standings`, `rounds`, `zones`, `total_matches`

**Cache TTL:** 12 saat

---

### 3.4 Info — Lig Bilgisi

```
GET /leagues/{id}/info
```

Sezon bağımsız. Alt ligleri ve mevcut sezonları listeler.

**Yanıt:**

```json
{
  "competition_id": 103,
  "name": "UEFA Champions League",
  "is_cup": true,
  "seasons": ["2025-2026", "2024-2025", "2023-2024"],
  "sub_leagues": [
    { "id": 24969, "name": "Round 1", "is_default": false },
    { "id": 25352, "name": "League Stage", "is_default": true }
  ]
}
```

Kupalar için `sub_leagues` = mevcut turlar/aşamalar.

**Cache TTL:** 7 gün

---

### 3.5 Team Stats — Takım İstatistikleri

```
GET /leagues/{id}/team-stats?season=2024-2025
GET /leagues/{id}/team-stats?season=2024-2025&type=Home
GET /leagues/{id}/team-stats?season=2024-2025&category=defensive
```

**Yanıt `data.teams[0]`:**

```json
{
  "team_id": 19,
  "team_name": "Arsenal",
  "goal": 69,
  "shots": 548,
  "target": 189,
  "offtarget": 202,
  "expectedgoals": 56.34,
  "xgot": 60.39,
  "corner": 251,
  "yellow": 70,
  "red": 6,
  "save": 88,
  "passball": 18600,
  "passballsuc": 16199,
  "avgcontrol": 56.95,
  "fouls": 398,
  "offside": 80,
  "dribbles": 317,
  "tackle": 592,
  "clearances": 608,
  "aerialduelswon": 420,
  "headersuc": 480,
  "schsum": 38
}
```

**Cache TTL:** 12 saat

---

### 3.6 Player Stats — Oyuncu İstatistikleri

```
GET /leagues/{id}/player-stats?season=2024-2025
GET /leagues/{id}/player-stats?season=2024-2025&category=assists
```

**`category` değerleri:** `offensive` (varsayılan gol listesi), `assists`

**Yanıt `data.players[0]`:**

```json
{
  "player_id": 100443,
  "player_name": "Mohamed Salah",
  "team_id": 25,
  "team_name": "Liverpool",
  "goals": 29,
  "assists": 18,
  "matches": 38,
  "minutes": 3380,
  "shots": 130,
  "shots_on_target": 61,
  "key_passes": 89,
  "passes": 1155,
  "pass_accuracy": 73.9,
  "penalty_goals": 9,
  "non_penalty_goals": 20,
  "rating": 291.06
}
```

**Cache TTL:** 24 saat

---

### 3.7 Handicap Stats — Asya Handikap

```
GET /leagues/{id}/handicap-stats?season=2024-2025
```

**Yanıt `data` alanları:** `home_ah`, `guest_ah`, `total_ah`, `summary`

**`home_ah[0]`:**

```json
{
  "rank": 1,
  "team_id": 28,
  "matches": 19,
  "win": 13,
  "draw": 0,
  "lose": 6,
  "win_pct": 68.4,
  "draw_pct": 0.0,
  "net": 7,
  "over_goals": 16,
  "under_goals": 3
}
```

**Cache TTL:** 12 saat

---

### 3.8 Current Round — Güncel Hafta

```
GET /leagues/{id}/current-round?season=2025-2026
```

**Yanıt:**

```json
{
  "league_id": 36,
  "season": "2025-2026",
  "sub_league_id": null,
  "current_round": 26,
  "last_completed_round": 25,
  "next_round": 27,
  "total_rounds": 38,
  "season_completed": false
}
```

**Cache TTL:** 12 saat

---

## 4. Lig vs Kupa Farkları

Sitenizde lig sayfası ve kupa sayfasını ayrı render etmek için:

```javascript
const data = response.data;
const isCup = data.is_cup === true || data.league?.type === "cup";

if (isCup) {
  // Kupa sayfası: cup_rounds ile tur tablosu göster
  // standings gösterme
  renderCupBracket(data.rounds, data.cup_rounds);
} else {
  // Lig sayfası: puan durumu + haftalık maçlar
  renderStandings(data.standings);
  renderMatchRounds(data.rounds);
}
```

| Özellik | Lig | Kupa |
|---------|-----|------|
| `standings` | ✅ Dolu (20+ satır) | ❌ Boş `[]` |
| `zones` | ✅ Küme düşme/çıkma | ❌ Boş `{}` |
| `cup_rounds` | ❌ Yok | ✅ Tur isimleri |
| `rounds` key formatı | Integer hafta no (`"1"`, `"2"`) | Integer tur ID (`"25696"`, `"26358"`) |
| `match_type` | `"round"` | `"cup"` |
| `league.type` | `"league"` (veya yok) | `"cup"` |
| `league.image` | ❌ Yok | ✅ Var |
| `league.short_name` | ❌ Yok | ✅ Var (örn. `"ENG FAC"`) |

---

## 5. Sezon Formatları

Farklı ligler farklı sezon formatı kullanır. Yanlış format gönderilirse veri gelmez.

| Format | Örnek | Kullanıldığı Yerler |
|--------|-------|---------------------|
| `YYYY-YYYY` | `2024-2025` | Avrupa ligleri, Türkiye, SA |
| `YYYY` | `2025` | Bazı Güney Amerika kupaları (Copa Claro vb.) |

Doğru formatı `/leagues/{id}/info` endpoint'inin `seasons` listesinden alın:

```javascript
// Mevcut sezonları çek
const info = await fetchLeagueInfo(leagueId);
const latestSeason = info.seasons[0]; // En güncel sezon
```

---

## 6. Logo & Görsel URL'leri

API görsel yollarını `images/xxx.png` formatında döner. Tam URL için:

```
https://football.nowgoal.com/{image_path}
```

**Örnekler:**

```javascript
// Takım logosu
const logoUrl = `https://football.nowgoal.com/${team.team_logo}`;
// → https://football.nowgoal.com/images/1jq85dyw7v2x.png

// Kupa görseli
const cupImageUrl = `https://football.nowgoal.com/${league.image}`;
// → https://football.nowgoal.com/league_match/images/1hqjdpn0ah1h.png
```

---

## 7. Entegrasyon Örnekleri

### Temel Fetch Yardımcısı

```javascript
const API_BASE = "https://api.golsinyali.com/api/v1";
const API_KEY  = "YOUR_API_KEY";

async function leagueApi(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-API-Key": API_KEY }
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error);
  return json.data;
}
```

---

### Senaryo A: Lig Puan Durumu Sayfası

```javascript
async function loadStandings(leagueId, season = "2025-2026") {
  const data = await leagueApi(`/leagues/${leagueId}/standings?season=${season}`);

  return {
    leagueName: data.league.name,
    leagueColor: data.league.color,
    totalTeams: data.teams_count,
    standings: data.standings, // rank, team_name, team_logo, played, won, drawn, lost, goals_for, goals_against, points, zone
    zones: data.zones,         // { promotion: [1,2,3,4], playoff: [5], relegation: [18,19,20] }
  };
}

// Kullanım:
const pl = await loadStandings(36, "2024-2025");
pl.standings.forEach(row => {
  console.log(`${row.rank}. ${row.team_name} — ${row.points} puan`);
});
```

---

### Senaryo B: Haftalık Maç Listesi

```javascript
async function loadRoundMatches(leagueId, season, round) {
  const data = await leagueApi(
    `/leagues/${leagueId}/matches?season=${season}&round=${round}`
  );

  return {
    round,
    matches: data.matches.map(m => ({
      id:       m.match_id,
      date:     m.datetime,
      status:   m.status,          // "finished" | "not_started" | "live"
      home:     m.home_team.name,
      homeLogo: `https://football.nowgoal.com/${m.home_team.logo}`,
      away:     m.away_team.name,
      awayLogo: `https://football.nowgoal.com/${m.away_team.logo}`,
      score:    m.score.full_time, // "2-0" veya null
      htScore:  m.score.half_time,
    }))
  };
}
```

---

### Senaryo C: Kupa Tur Tablosu

```javascript
async function loadCupMatches(cupId, season) {
  const data = await leagueApi(`/leagues/${cupId}/matches?season=${season}`);

  if (!data.is_cup) throw new Error("Bu bir kupa değil");

  // Turları sırayla göster
  const rounds = Object.entries(data.cup_rounds)
    .map(([id, round]) => ({
      id: Number(id),
      name: round.name,            // "Round 1", "Quarterfinals", "Finals" vb.
      matches: data.rounds[id] || []
    }))
    .filter(r => r.matches.length > 0);

  return {
    cupName:   data.league.name,
    shortName: data.league.short_name,
    image:     `https://football.nowgoal.com/${data.league.image}`,
    rounds
  };
}

// Kullanım — FA Cup
const faCup = await loadCupMatches(90, "2024-2025");
faCup.rounds.forEach(round => {
  console.log(`\n=== ${round.name} ===`);
  round.matches.forEach(m => {
    console.log(`${m.home_team.name} ${m.score.full_time} ${m.away_team.name}`);
  });
});
```

---

### Senaryo D: Mevcut Haftayı Otomatik Getir

```javascript
async function loadCurrentRound(leagueId, season) {
  // Önce güncel haftayı öğren
  const roundInfo = await leagueApi(
    `/leagues/${leagueId}/current-round?season=${season}`
  );

  const currentRound = roundInfo.current_round;
  if (!currentRound) return null;

  // O haftanın maçlarını çek
  const matches = await leagueApi(
    `/leagues/${leagueId}/matches?season=${season}&round=${currentRound}`
  );

  return {
    round: currentRound,
    totalRounds: roundInfo.total_rounds,
    seasonCompleted: roundInfo.season_completed,
    matches: matches.matches
  };
}
```

---

### Senaryo E: Lig Sayfası — Hepsini Tek İstekte

```javascript
// Büyük sayfa için full endpoint kullan
async function loadLeaguePage(leagueId, season) {
  const data = await leagueApi(`/leagues/${leagueId}/full?season=${season}`);

  return {
    league:    data.league,
    standings: data.standings,   // overall puan durumu
    rounds:    data.rounds,      // tüm haftaların maçları
    zones:     data.zones,
    isCup:     false             // /full sadece ligler için anlamlı
  };
}
```

---

### Senaryo F: Gol Krallığı + En Çok Asist

```javascript
async function loadTopScorers(leagueId, season) {
  const [scorers, assisters] = await Promise.all([
    leagueApi(`/leagues/${leagueId}/player-stats?season=${season}&category=offensive`),
    leagueApi(`/leagues/${leagueId}/player-stats?season=${season}&category=assists`)
  ]);

  return {
    topScorers:  scorers.players.slice(0, 10),   // ilk 10
    topAssisters: assisters.players.slice(0, 10)
  };
}
```

---

## 8. Hata Yönetimi

| HTTP Kodu | `error` | Sebep | Çözüm |
|-----------|---------|-------|-------|
| 400 | `"season is required"` | `season` parametresi eksik | Query'ye `?season=2024-2025` ekle |
| 400 | `"type must be..."` | Geçersiz standings type | `overall`, `home` veya `away` kullan |
| 401 | `"API key is required"` | Header eksik | `X-API-Key` header'ı ekle |
| 404 | `"Match data not available"` | Sezon veya ID yanlış | `/info` endpoint'inden geçerli sezonları kontrol et |
| 503 | `"Invalid league data format"` | Kaynak geçici sorun | 30s sonra tekrar dene |

```javascript
async function safeLeagueApi(path) {
  try {
    return await leagueApi(path);
  } catch (err) {
    if (err.message.includes("not available")) {
      // Yanlış sezon veya veri yok — /info'dan sezonları kontrol et
      console.warn("Veri bulunamadı:", path);
      return null;
    }
    throw err;
  }
}
```

---

## 9. Cache & Performans

| Endpoint | Cache TTL | İlk İstek (soğuk) | Sonraki İstekler |
|----------|-----------|-------------------|-----------------|
| standings | 12 saat | ~1.5–3s | ~10ms |
| matches | 48 saat | ~1.5–5s | ~10ms |
| full | 12 saat | ~1.5–3s | ~10ms |
| info | 7 gün | ~1.5s | ~10ms |
| team-stats | 12 saat | ~2–4s | ~10ms |
| player-stats | 24 saat | ~2–4s | ~10ms |
| handicap-stats | 12 saat | ~2–4s | ~10ms |
| current-round | 12 saat | ~1.5–3s | ~10ms |

**İpucu:** Sayfa açılışında `current-round` önce çağırılabilir (küçük yanıt, hızlı), ardından paralel olarak standings + matches çekilebilir:

```javascript
// Paralel çekme — toplam süre max(her biri) kadar
const [roundInfo, standings] = await Promise.all([
  leagueApi(`/leagues/36/current-round?season=2025-2026`),
  leagueApi(`/leagues/36/standings?season=2025-2026`)
]);
```

---

## 10. Önemli Lig ID'leri

### Büyük Ligler

| ID | Lig | Ülke | Sezon Formatı |
|----|-----|------|---------------|
| 36 | Premier League | İngiltere | `2024-2025` |
| 34 | La Liga | İspanya | `2024-2025` |
| 31 | Bundesliga | Almanya | `2024-2025` |
| 32 | Ligue 1 | Fransa | `2024-2025` |
| 33 | Serie A | İtalya | `2024-2025` |
| 203 | Süper Lig | Türkiye | `2024-2025` |
| 6 | Eredivisie | Hollanda | `2024-2025` |
| 745 | Pro League | Suudi Arabistan | `2024-2025` |

### Büyük Kupalar

| ID | Kupa | Ülke | Sezon Formatı |
|----|------|------|---------------|
| 103 | UEFA Champions League | Avrupa | `2024-2025` |
| 113 | UEFA Europa League | Avrupa | `2024-2025` |
| 2187 | UEFA Conference League | Avrupa | `2024-2025` |
| 90 | FA Cup | İngiltere | `2024-2025` |
| 84 | EFL Cup (Carabao) | İngiltere | `2024-2025` |
| 81 | Copa del Rey | İspanya | `2024-2025` |
| 51 | DFB Pokal | Almanya | `2024-2025` |
| 54 | Coupe de France | Fransa | `2024-2025` |
| 83 | Coppa Italia | İtalya | `2024-2025` |
| 167 | Türkiye Kupası | Türkiye | `2024-2025` |

> **Toplam:** 957 competition (393 lig + 564 kupa) desteklenmektedir.
> Tüm liste için: `GET /api/v1/leagues/all`
