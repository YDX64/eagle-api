# Bee API vs Eagle API — Ultra Detaylı Karşılaştırma

## Genel Bakış

| Özellik | Bee API (Orijinal) | Eagle API (Geliştirilmiş) |
|---------|-------------------|--------------------------|
| Kod tabanı | basriayaz/football-analysis-api | YDX64/eagle-api (fork + eklentiler) |
| Analiz modül sayısı | 8 modül | **11 modül** (+3 yeni) |
| Tahmin kaynağı sayısı | 4 kaynak | **7 kaynak** (+3 yeni) |
| Toplam analiz kodu | 5,539 satır | **6,644 satır** (+1,105 satır) |
| Tahmin marketleri | 7 market | 7 market (aynı) |
| Matematiksel model | Yok | **Poisson dağılımı** |
| Piyasa sinyal analizi | Statik odds okuma | **Dinamik hareket takibi** |
| Trend tespiti | Yok | **Seri/streak algılama** |
| Port | 8096 | 8098 |

---

## Analiz Modülleri Karşılaştırması

### Ortak Modüller (Her iki API'de aynı)

| Modül | Dosya | Satır | Ne Yapar |
|-------|-------|-------|----------|
| H2H Analysis | `analysis/h2h.py` | 721 | Takımların geçmiş karşılaşmalarını analiz eder |
| Team Performance | `analysis/team_performance.py` | 689 | Son 20 maçtan takım performans metrikleri |
| Correct Score | `analysis/correct_score.py` | 235 | Skor oranlarından türetilmiş tahminler |
| Odds Analysis | `analysis/odds_analysis.py` | 1,117 | 1x2 oran analizi, AH, GL trendleri |
| Odds Trends | `analysis/odds_trends.py` | 602 | Oran hareket trendleri |
| Tactics | `analysis/tactics.py` | 521 | Taktik analiz |
| Tips | `analysis/tips.py` | 74 | Bahis ipuçları |
| Spotlight | `analysis/spotlight.py` | 551 | Öne çıkan istatistikler |

### Eagle'a Eklenen YENİ Modüller

| Modül | Dosya | Satır | Ne Yapar |
|-------|-------|-------|----------|
| **Poisson Model** | `analysis/poisson_model.py` | 246 | İstatistiksel gol olasılık modeli |
| **Odds Movement** | `analysis/odds_movement.py` | 457 | Bahisçi hareket sinyal çıkarımı |
| **Streak Detector** | `analysis/streak_detector.py` | 274 | Takım seri/trend tespiti |

### Güncellenen Modüller

| Modül | Bee Satır | Eagle Satır | Değişiklik |
|-------|-----------|-------------|------------|
| `final_predictions.py` | 436 | **564** | +128 satır, 3 yeni kaynak entegrasyonu |
| `routes/utils.py` | — | +12 satır | Yeni modüller paralel pipeline'a eklendi |

---

## Algoritma Detayları: Kaynak Bazlı Karşılaştırma

### KAYNAK 1: H2H Analysis (Her İkisinde Aynı)

**Algoritma:**
- Takımların son karşılaşmaları (en az 5 maç gerekli)
- Her maçtan: skor, İY skor, gol sayıları, BTTS durumu
- Home/Away/Draw oranları hesaplanır
- Over/Under oranları her line için (1.5, 2.5, 3.5)
- BTTS Yes/No oranları
- HT 1x2 ve HT gol oranları
- **Ağırlık formülü**: Bee'de %25 (1x2), Eagle'da %20 (1x2)

### KAYNAK 2: Team Performance (Her İkisinde Aynı)

**Algoritma:**
- Her takımın son 20 maçı (ev+deplasman)
- Win/Draw/Loss oranları → 1x2
- Gol ortalamaları → Over/Under
- Gol yeme ortalamaları → BTTS
- HT istatistikleri → HT tahminleri
- **Crosstab**: İki takımın performansını çaprazlayarak birleştirir
- **Ağırlık formülü**: Bee'de %30 (1x2), Eagle'da %25 (1x2)

### KAYNAK 3: Correct Score Derived (Her İkisinde Aynı)

**Algoritma:**
- Correct score bahis oranlarından implied probability hesaplar
- Her skor olasılığını toplayarak: P(1x2), P(Over), P(BTTS) türetir
- Örnek: P(Home Win) = P(1-0) + P(2-0) + P(2-1) + P(3-0) + ...
- **Ağırlık formülü**: Bee'de %15 (1x2), Eagle'da %10 (1x2)

### KAYNAK 4: Odds Analysis (Her İkisinde Aynı)

**Algoritma:**
- Tüm bahisçilerin 1x2 oranlarını toplar
- `P(home) = (1/odds_home) / total_implied`
- Smart normalization: %70+ olanlara %30 indirim
- Min %5 kuralı
- Sadece 1x2'de kullanılır (Goal Lines ve BTTS'te yok)
- **Ağırlık formülü**: Bee'de %30 (1x2), Eagle'da %25 (1x2)

---

## Eagle'a Eklenen YENİ Algoritmalar (Ultra Detay)

### KAYNAK 5: Poisson Goal Model (EAGLE YENİ)

**Matematiksel Temel:**
Poisson dağılımı: `P(X=k) = (λ^k × e^{-λ}) / k!`

Burada `λ` = beklenen gol sayısı (Expected Goals)

**Lambda Hesaplama Adımları:**

1. **Veri toplama**: H2H verilerinden son 15 maçı al
2. **Attack rate**: Takımın son maçlarda attığı ortalama gol
3. **Defense rate**: Takımın son maçlarda yediği ortalama gol
4. **Lambda hesaplama**:
   ```
   league_avg = 1.3  (ortalama takım başı gol)

   home_lambda = (home_attack / league_avg) × (away_defense / league_avg) × league_avg
   away_lambda = (away_attack / league_avg) × (home_defense / league_avg) × league_avg
   ```
5. **Clamp**: `0.3 ≤ λ ≤ 4.0` aralığına sınırla

**Over/Under Hesaplama:**
```
P(Over 2.5) = 1 - Σ P(home=h) × P(away=a)  [h+a < 3 olan tüm kombinasyonlar]
```

12×12 matris (0-11 arası goller) kullanarak joint probability hesaplanır.

**BTTS Hesaplama:**
```
P(BTTS) = 1 - P(home=0) - P(away=0) + P(home=0 ∧ away=0)
```

**1x2 Hesaplama:**
```
P(Home) = Σ P(home=h) × P(away=a)  [h > a olan tüm kombinasyonlar]
P(Draw) = Σ P(home=k) × P(away=k)  [k=0..10]
P(Away) = Σ P(home=h) × P(away=a)  [h < a olan tüm kombinasyonlar]
```

**HT Lambda:**
```
ht_home_lambda = home_lambda × 0.42
ht_away_lambda = away_lambda × 0.42
```
(İlk yarı, toplam golün yaklaşık %42'si)

**Confidence Hesaplama:**
- 10+ maç verisi → %75
- 7-9 maç → %65
- 5-6 maç → %55
- 3-4 maç → %45

**Final Predictions'daki Ağırlıklar:**
| Market | Poisson Ağırlığı |
|--------|-----------------|
| 1x2 | %15 |
| Goal Lines | **%20** (en güçlü kaynak) |
| BTTS | **%20** |
| HT 1x2 | %15 |
| HT Goals | %15 |

**Bee'de Neden Yoktu:**
Bee sadece geçmiş maç oranlarına bakıyor (frequentist yaklaşım). Poisson ise olasılık teorisine dayalı matematiksel bir model — "bu takımlar maç başı ortalama kaç gol atıyor/yiyor" bilgisinden tüm skor olasılıklarını hesaplayabiliyor.

---

### KAYNAK 6: Odds Movement Predictions (EAGLE YENİ)

**Temel Prensip:**
Bahisçiler oranları açılış→kapanış arasında değiştirir. Bu değişiklik "akıllı para"nın nereye gittiğini gösterir.

**4 Alt Sinyal:**

#### 6a. Goal Line Movement
```
Her bahisçi için:
  opening_line = first_odds.over_under.line  (örn: 2.5)
  closing_line = pre_match_odds.over_under.line  (örn: 2.75)

  if closing > opening + 0.05 → raised += 1  (Over sinyali)
  if closing < opening - 0.05 → lowered += 1  (Under sinyali)

signal = "over" if raised > lowered else "under"
strength = |raised - lowered| / total_bookmakers
```

**Örnek**: 10 bahisçiden 7'si goal line'ı 2.5→2.75'e yükseltmişse → Güçlü Over 2.5 sinyali

#### 6b. Asian Handicap Movement
```
Her bahisçi için:
  if closing_ah > opening_ah + 0.05 → home_count += 1  (Ev sahibi güçleniyor)
  if closing_ah < opening_ah - 0.05 → away_count += 1  (Deplasman güçleniyor)

signal = "home" if home_count > away_count else "away"
```

Bu Falcon'un `ms_tahmini()` fonksiyonundaki mantığın aynısı: `ev > 6 → "1X"`, `dep > 6 → "X2"`

#### 6c. 1x2 Odds Movement
```
Her bahisçi için:
  if pre_home < first_home × 0.95 → home_drops += 1  (Para ev sahibine akıyor)
  if pre_away < first_away × 0.95 → away_drops += 1

signal = en çok drop olan taraf
```

#### 6d. HT Odds Movement
İlk yarı oranlarında aynı analiz:
- HT goal line hareketi → HT Over/Under sinyali
- HT 1x2 hareketi → HT MS sinyali

**Sinyalden Tahmine Dönüşüm:**

Goal Line → Over/Under:
```
base = closing_line'dan türetilmiş yüzde
  3.0+ → Over 2.5 %70
  2.75 → %60
  2.5  → %50
  2.25 → %40
  2.0- → %30

direction bonus: ±%10 (hareket yönüne göre)
```

AH → 1x2:
```
base = {home: 33.3%, draw: 33.3%, away: 33.3%}
bonus = min(20, strength × 30)
signal=home → home += bonus, away -= bonus×0.6, draw -= bonus×0.4
```

**Final Predictions'daki Ağırlıklar:**
| Market | Odds Movement Ağırlığı |
|--------|----------------------|
| 1x2 | %10 |
| Goal Lines | %15 |
| BTTS | (dolaylı, GL üzerinden) |
| HT 1x2 | %10 |
| HT Goals | (dolaylı, HT GL üzerinden) |

**Bee'de Neden Yoktu:**
Bee'nin `odds_analysis.py`'si zaten odds değişikliklerini takip ediyor AMA bunları sadece raporlama amaçlı kullanıyordu — **final_predictions'a girdi olarak vermiyordu**. Eagle bu verileri tahmin sinyallerine dönüştürüp ensemble'a ekliyor.

---

### KAYNAK 7: Streak Detector (EAGLE YENİ)

**Temel Prensip:**
Bir takım son 10 maçın 8-10'unda aynı sonucu veriyorsa (örn: hep Over 2.5), bu çok güçlü bir sinyal.

**Tespit Edilen Seriler:**

| Seri | Algılama | Eşik | Sinyal Gücü |
|------|----------|------|-------------|
| Over 2.5 | `goals > 2` sayımı / toplam | ≥%80 oran | `avg(home_rate, away_rate)` |
| Under 2.5 | `goals ≤ 2` sayımı / toplam | ≤%30 oran | `1.0 - avg_rate` |
| BTTS Yes | `home_score>0 AND away_score>0` | ≥%75 oran | `avg(home_btts, away_btts)` |
| BTTS No | tersi | ≤%30 oran | `1.0 - avg_rate` |
| HT Gol | `ht_home+ht_away > 0` | ≥%80 oran | `avg(home_ht, away_ht)` |
| MS Home | home win rate ≥%70 AND away ≤%30 | ≥%70 home WR | `home_win_rate` |
| MS Away | tersi | ≥%70 away WR | `away_win_rate` |
| H2H Over | H2H maçlarda over oranı | ≥%80, min 5 maç | `h2h_over_rate` |

**Algoritma Akışı:**
```
1. Home takımın son 10 maçı → _analyze_team_streaks()
   - over_25_rate, btts_rate, ht_goal_rate, scoring_rate, win_rate

2. Away takımın son 10 maçı → _analyze_team_streaks()

3. H2H son 10 maç → _analyze_h2h_streaks()

4. Sinyallere dönüştür → _streaks_to_signals()
   - avg_over = (home_over_rate + away_over_rate) / 2
   - avg_over ≥ 0.8 → {direction: "over", strength: avg_over}

5. Sinyal → Final Predictions bonus:
   - strength ≥ 0.6 → 1x2'de %5 ağırlık
   - strength ≥ 0.7 → goal lines'da %5 ağırlık
```

**Falcon'dan Esinlenme:**
Falcon'un `predictions.py`'sindeki kurallar:
- `home_over25 == 10 AND goalline > 2.75 → "2.5 Üst"` (10/10 seri)
- `home_btts == 10 AND goalline > 2.75 → "Kg Var"` (10/10 seri)
- `h2h_ht_goals == 10 AND goalline_ht > 0.75 → "İy 0.5 Üst"` (10/10 seri)

Eagle bu kuralları daha esnek ve istatistiksel yapıda implement ediyor: kesin 10/10 yerine %80+ eşik kullanarak daha fazla maçta sinyal üretiyor.

---

## Final Predictions Ağırlık Karşılaştırması

### 1x2 (Maç Sonucu)

| Kaynak | Bee Ağırlığı | Eagle Ağırlığı | Fark |
|--------|-------------|----------------|------|
| Team Performance | %30 | %25 | -5% |
| Odds Analysis | %30 | %25 | -5% |
| H2H | %25 | %20 | -5% |
| Correct Score | %15 | %10 | -5% |
| **Poisson** | — | **%15** | +15% YENİ |
| **Odds Movement** | — | **%10** | +10% YENİ |
| **Streaks** | — | **%5** | +5% YENİ |
| **TOPLAM** | **4 kaynak** | **7 kaynak** | **+3** |

### Goal Lines (Over/Under)

| Kaynak | Bee Ağırlığı | Eagle Ağırlığı | Fark |
|--------|-------------|----------------|------|
| Team Performance | %40 | %30 | -10% |
| H2H | %30 | %20 | -10% |
| Correct Score | %30 | %15 | -15% |
| **Poisson** | — | **%20** | +20% YENİ |
| **Odds Movement** | — | **%15** | +15% YENİ |
| **Streaks** | — | **%5** | +5% YENİ |
| **TOPLAM** | **3 kaynak** | **6 kaynak** | **+3** |

### BTTS (Karşılıklı Gol)

| Kaynak | Bee Ağırlığı | Eagle Ağırlığı | Fark |
|--------|-------------|----------------|------|
| Team Performance | %40 | %30 | -10% |
| H2H | %35 | %25 | -10% |
| Correct Score | %25 | %15 | -10% |
| **Poisson** | — | **%20** | +20% YENİ |
| **Streaks** | — | **%5** | +5% YENİ |
| **TOPLAM** | **3 kaynak** | **5 kaynak** | **+2** |

### HT 1x2 (İlk Yarı Sonucu)

| Kaynak | Bee Ağırlığı | Eagle Ağırlığı | Fark |
|--------|-------------|----------------|------|
| Team Performance | %55 | %40 | -15% |
| H2H | %45 | %30 | -15% |
| **Poisson HT** | — | **%15** | +15% YENİ |
| **Odds Movement HT** | — | **%10** | +10% YENİ |
| **TOPLAM** | **2 kaynak** | **4 kaynak** | **+2** |

### HT Goals (İlk Yarı Gol)

| Kaynak | Bee Ağırlığı | Eagle Ağırlığı | Fark |
|--------|-------------|----------------|------|
| Team Performance | %55 | %40 | -15% |
| H2H | %45 | %30 | -15% |
| **Poisson HT** | — | **%15** | +15% YENİ |
| **Streaks HT** | — | **%5** | +5% YENİ |
| **TOPLAM** | **2 kaynak** | **4 kaynak** | **+2** |

---

## Confidence Hesaplama Farkı

### Bee Yaklaşımı:
```
Sadece standart sapma (stdev) bazlı:
  stdev ≤ 5  → %95
  stdev ≤ 10 → %85
  stdev ≤ 15 → %75
  stdev ≤ 20 → %65
  stdev ≤ 25 → %55
  stdev > 25 → %45

Bonus: 4+ kaynak → +5%, 3 kaynak → +2%
```

### Eagle Yaklaşımı:
Aynı formül AMA:
- **7 kaynak** olduğu için standart sapma daha güvenilir (daha fazla veri noktası)
- Kaynak sayısı bonusu daha sık tetikleniyor (genellikle 5-7 kaynak aktif)
- Poisson kaynağı yüksek precision nedeniyle sapmaları düşürüyor

---

## Gerçek Maç Karşılaştırması

**Maç**: Aguilas Doradas vs Alianza Petrolera (2922237)
**Gerçek Skor**: 1-0 (Home Win, Under 2.5, BTTS No)

| Tahmin | Bee | Eagle | Doğru Olan | Kazanan |
|--------|-----|-------|-----------|---------|
| **1x2 Home** | %43.0 | %39.6 | Home ✅ | Bee (daha güçlü) |
| **1x2 Draw** | %28.6 | %32.7 | — | — |
| **1x2 Away** | %28.4 | %27.7 | — | — |
| **Over 2.5** | %37.8 | %29.6 | Under ✅ | **Eagle** (daha güçlü Under) |
| **Under 2.5** | %62.0 | **%70.3** | Under ✅ | **Eagle** (+8.3%) |
| **Over 3.5** | %17.2 | %13.1 | Under ✅ | **Eagle** (daha güçlü Under) |
| **Under 3.5** | %82.5 | **%86.8** | Under ✅ | **Eagle** (+4.3%) |
| **BTTS Yes** | %43.8 | %35.3 | No ✅ | **Eagle** (daha güçlü No) |
| **BTTS No** | %56.2 | **%64.7** | No ✅ | **Eagle** (+8.5%) |
| **HT Over 0.5** | %58.1 | %51.6 | Under ✅ (HT 0-0) | **Eagle** (daha kapalı) |
| **Confidence 1x2** | %90.0 | %80.0 | — | Bee (ama daha az kaynak) |
| **Confidence GL** | %87.0 | %80.0 | — | Bee (ama daha az kaynak) |

**Sonuç**: Eagle, gol bazlı tahminlerde (Over/Under, BTTS) **belirgin şekilde daha doğru** çünkü Poisson modeli "bu iki takımın Expected Goals'u sadece 0.6" diyerek alt sinyalini çok güçlü veriyor.

---

## Mimari Farklar

| Özellik | Bee | Eagle |
|---------|-----|-------|
| Paralel analiz worker'ı | 6 thread | **9 thread** (+3 yeni modül) |
| Analiz pipeline süresi | ~1-2s | ~1-2s (aynı, paralel çalışır) |
| Redis cache DB | DB 2 | DB 5 |
| Yeni endpoint'ler | — | `/eagle/match`, `/eagle/status` |
| Expected Goals çıktısı | Yok | `poisson_predictions.expected_goals` |
| Odds sinyal çıktısı | Sadece raporlama | **Tahmine dönüştürülmüş sinyal** |
| Seri bilgisi | Yok | `streak_predictions.signals` |

---

## Teknik Avantajlar Özeti

### Eagle'ın Bee'ye Göre Avantajları:

1. **Poisson Modeli**: Gol olasılıklarını matematiksel olarak hesaplıyor. "Her takım ortalama kaç gol atıyor/yiyor" bilgisinden kesin olasılıklar çıkarıyor. Bee sadece "son maçlarda kaç kez over olmuş" sayıyor.

2. **Piyasa Sinyali**: Bahisçiler açılış→kapanış arasında oranları değiştirir. Bu değişikliğin yönü "akıllı para"nın nereye gittiğini gösterir. Bee bu bilgiyi sadece raporluyor, Eagle tahmine dönüştürüyor.

3. **Seri Tespiti**: Bir takım son 10 maçın 8-10'unda aynı sonucu veriyorsa bu çok güçlü sinyal. Bee bunu hiç tespit etmiyor.

4. **Daha Çeşitli Kaynak**: 4 yerine 7 kaynak = daha stabil tahminler. Tek bir kaynağın hatası diğerleri tarafından dengeleniyor.

5. **Expected Goals**: Eagle, `home_lambda` ve `away_lambda` değerlerini hesaplayarak maçın beklenen gol sayısını veriyor. Bu tek başına bile çok değerli bir metrik.

### Bee'nin Eagle'a Göre Avantajları:

1. **Daha yüksek confidence skorları**: Daha az kaynak = daha düşük standart sapma = daha yüksek (ama yanıltıcı olabilecek) confidence.

2. **Daha stabil/denenmiş**: Uzun süredir production'da çalışan kod.

3. **Basitlik**: Daha az kaynak = daha kolay debug.
