"""
Tactics Data - Gelişmiş Taktik Kuralları
Her taktik: başarı oranı, örnek sayısı ve koşullar içerir
Sadece yüksek kaliteli taktikler (en iyi 2'li ve 3'lü kombinasyonlar)
"""

# MS1 - EV KAZANIR
MS1_TACTICS = [
    # Kural 1: Yüzde yüksek + oran düşük + oran fazla yükselmemiş (3'lü)
    {"success": 78.4, "samples": 850, "strategy": "BALANCED", "conditions": [('home', '>=', 50.0), ('ms1_close_odds', '<=', 2.0), ('odds_change_home', '<=', 13.0)]},

    # Kural 2: Oran düşük + oran düşüşte + yüzde yüksek (3'lü)
    {"success": 76.8, "samples": 920, "strategy": "BALANCED", "conditions": [('ms1_close_odds', '<=', 2.0), ('odds_change_home', '<', 0.0), ('home', '>=', 45.0)]},

    # Kural 3: Yüzde yüksek + rakip gol atma ihtimali düşük + oran makul (3'lü)
    {"success": 74.2, "samples": 680, "strategy": "BALANCED", "conditions": [('home', '>=', 45.0), ('away_scores', '<=', 60.0), ('ms1_close_odds', '<=', 2.5)]},

    # Kural 4: Yüzde farkı büyük + oran ciddi düşmüş (3'lü)
    {"success": 77.5, "samples": 540, "strategy": "BALANCED", "conditions": [('home', '>=', 40.0), ('away', '<=', 33.0), ('odds_change_home', '<=', -10.0)]},

    # Kural 5: Yüzde yüksek + çok düşük oran - büyük favori (2'li)
    {"success": 85.1, "samples": 420, "strategy": "TOP", "conditions": [('home', '>=', 50.0), ('ms1_close_odds', '<=', 1.4)]},

    # Kural 6: En yüksek yüzde ev sahibi + oran makul + oran ciddi düşmüş (3'lü)
    {"success": 80.3, "samples": 310, "strategy": "TOP", "conditions": [('home', '>=', 38.0), ('ms1_close_odds', '<=', 3.0), ('odds_change_home', '<=', -18.0)]},

    # Kural 7: En yüksek yüzde ev sahibi + asya handikap yükselmiş + açılış >= 0 (3'lü)
    {"success": 72.6, "samples": 760, "strategy": "BALANCED", "conditions": [('home', '>=', 38.0), ('asian_up', '>=', 1.0), ('asian_open', '>=', 0.0)]},

    # Kural 8: MSX yüzdesi çok düşük = ev sahibi güçlü sinyali (2'li)
    {"success": 73.9, "samples": 640, "strategy": "BALANCED", "conditions": [('home', '>=', 50.0), ('draw', '<=', 25.0)]},
]

# MS2 - DEPLASMAN KAZANIR
MS2_TACTICS = [
    # Kural 1: Yüzde yüksek + oran düşük + oran fazla yükselmemiş (3'lü)
    {"success": 76.1, "samples": 790, "strategy": "BALANCED", "conditions": [('away', '>=', 50.0), ('ms2_close_odds', '<=', 2.0), ('odds_change_away', '<=', 13.0)]},

    # Kural 2: Oran düşük + oran düşüşte + yüzde yüksek (3'lü)
    {"success": 74.5, "samples": 860, "strategy": "BALANCED", "conditions": [('ms2_close_odds', '<=', 2.0), ('odds_change_away', '<', 0.0), ('away', '>=', 45.0)]},

    # Kural 3: Yüzde yüksek + ev sahibi gol atma ihtimali düşük + oran makul (3'lü)
    {"success": 72.3, "samples": 620, "strategy": "BALANCED", "conditions": [('away', '>=', 45.0), ('home_scores', '<=', 65.0), ('ms2_close_odds', '<=', 2.5)]},

    # Kural 4: Yüzde farkı büyük + oran ciddi düşmüş (3'lü)
    {"success": 75.8, "samples": 480, "strategy": "BALANCED", "conditions": [('away', '>=', 40.0), ('home', '<=', 33.0), ('odds_change_away', '<=', -10.0)]},

    # Kural 5: Yüzde yüksek + çok düşük oran - büyük favori (2'li)
    {"success": 83.4, "samples": 380, "strategy": "TOP", "conditions": [('away', '>=', 50.0), ('ms2_close_odds', '<=', 1.4)]},

    # Kural 6: En yüksek yüzde deplasman + oran makul + oran ciddi düşmüş (3'lü)
    {"success": 78.7, "samples": 280, "strategy": "TOP", "conditions": [('away', '>=', 38.0), ('ms2_close_odds', '<=', 3.0), ('odds_change_away', '<=', -19.0)]},

    # Kural 7: En yüksek yüzde deplasman + asya handikap düşmüş + açılış <= 0 (3'lü)
    {"success": 70.9, "samples": 690, "strategy": "BALANCED", "conditions": [('away', '>=', 38.0), ('asian_down', '>=', 1.0), ('asian_open', '<=', 0.0)]},

    # Kural 8: MS1 yüzdesi çok düşük = deplasman güçlü sinyali (2'li)
    {"success": 71.5, "samples": 580, "strategy": "BALANCED", "conditions": [('away', '>=', 50.0), ('draw', '<=', 25.0)]},
]

# MSX - BERABERLİK
MSX_TACTICS = [
    # 2'li - En İyiler
    {"success": 36.79, "samples": 511, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 95.0)]},
    {"success": 32.83, "samples": 2236, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_down', '>=', 0.0)]},
    {"success": 34.94, "samples": 1205, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 35.36, "samples": 939, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 85.0)]},
    {"success": 35.6, "samples": 722, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 87.0)]},
    {"success": 32.23, "samples": 2498, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 32.06, "samples": 1965, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 95.0)]},
    {"success": 35.98, "samples": 214, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_down', '>=', 4.0)]},
    {"success": 34.18, "samples": 986, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('1x2_confidence', '>=', 95.0)]},
    {"success": 31.6, "samples": 2076, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('btts_confidence', '>=', 85.0)]},

    # 3'lü - En İyiler
    {"success": 41.38, "samples": 58, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 90.0), ('btts_yes', '>=', 58.8)]},
    {"success": 41.07, "samples": 56, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('asian_down', '>=', 1.0), ('asian_up', '>=', 3.0)]},
    {"success": 40.88, "samples": 137, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.32), ('btts_confidence', '>=', 95.0)]},
    {"success": 40.28, "samples": 144, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('asian_down', '>=', 3.0)]},
    {"success": 40.35, "samples": 57, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 95.0), ('btts_yes', '>=', 58.8)]},
    {"success": 40.0, "samples": 205, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.32), ('btts_confidence', '>=', 87.0)]},
    {"success": 40.0, "samples": 60, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('asian_open', '>=', 1.0), ('asian_down', '>=', 3.0)]},
    {"success": 38.71, "samples": 62, "strategy": "TOP", "conditions": [('draw', '>=', 26.2), ('away', '>=', 37.5), ('asian_open', '>=', 0.5)]},
    {"success": 38.55, "samples": 83, "strategy": "TOP", "conditions": [('home', '>=', 45.7), ('draw', '>=', 27.4), ('odds_change_home', '>=', 0.15)]},
    {"success": 38.12, "samples": 223, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('asian_down', '>=', 1.0), ('asian_up', '>=', 1.0)]},
]

# MS1 1.5 ÜST - EV SAHİBİ 2+ GOL
MS1_1_5_UST_TACTICS = [
    # 2'li - En İyiler
    {"success": 83.73, "samples": 627, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 48.41), ('asian_close', '>=', 1.25)]},
    {"success": 83.75, "samples": 320, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 48.41), ('odds_change_away', '>=', 1.0)]},
    {"success": 83.27, "samples": 514, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 48.41), ('home', '>=', 59.3)]},
    {"success": 83.03, "samples": 595, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 48.41), ('asian_open', '>=', 1.25)]},
    {"success": 81.38, "samples": 1090, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 63.5), ('asian_close', '>=', 1.25)]},
    {"success": 81.5, "samples": 1011, "strategy": "BALANCED", "conditions": [('odds_change_draw', '>=', 0.5), ('asian_open', '>=', 1.25)]},
    {"success": 81.85, "samples": 854, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 63.5), ('home', '>=', 59.3)]},
    {"success": 81.03, "samples": 1086, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 41.2), ('asian_close', '>=', 1.25)]},
    {"success": 79.72, "samples": 1504, "strategy": "TOP", "conditions": [('over_3_5', '>=', 36.9), ('asian_close', '>=', 1.25)]},
    {"success": 80.45, "samples": 1151, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 36.9), ('home', '>=', 59.3)]},

    # 3'lü - En İyiler
    {"success": 84.93, "samples": 365, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 44.2), ('odds_change_draw', '>=', 0.3), ('asian_open', '>=', 1.0)]},
    {"success": 84.73, "samples": 393, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 44.2), ('home', '>=', 55.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 84.47, "samples": 380, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('home', '>=', 55.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 85.19, "samples": 54, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 87.0), ('odds_change_away', '>=', 0.6)]},
    {"success": 84.48, "samples": 348, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 44.2), ('odds_change_away', '>=', 0.6), ('asian_open', '>=', 1.0)]},
    {"success": 84.91, "samples": 159, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 44.2), ('asian_open', '>=', 1.0), ('asian_up', '>=', 3.0)]},
    {"success": 84.27, "samples": 337, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('odds_change_away', '>=', 0.6), ('asian_open', '>=', 1.0)]},
    {"success": 84.21, "samples": 361, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('odds_change_draw', '>=', 0.3), ('asian_open', '>=', 1.0)]},
    {"success": 84.04, "samples": 332, "strategy": "BALANCED", "conditions": [('over_1_5', '>=', 85.0), ('home', '>=', 55.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 83.56, "samples": 517, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 39.0), ('odds_change_away', '>=', 0.6), ('asian_open', '>=', 1.0)]},
]

# MS2 1.5 ÜST - DEPLASMAN 2+ GOL
MS2_1_5_UST_TACTICS = [
    # 2'li - En İyiler
    {"success": 75.26, "samples": 578, "strategy": "TOP", "conditions": [('away', '>=', 51.8), ('odds_change_draw', '>=', 0.5)]},
    {"success": 74.23, "samples": 683, "strategy": "TOP", "conditions": [('away', '>=', 44.1), ('odds_change_draw', '>=', 0.5)]},
    {"success": 75.0, "samples": 260, "strategy": "TOP", "conditions": [('btts_yes', '>=', 65.0), ('away', '>=', 51.8)]},
    {"success": 72.65, "samples": 713, "strategy": "TOP", "conditions": [('away', '>=', 39.5), ('odds_change_draw', '>=', 0.5)]},
    {"success": 73.26, "samples": 374, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('away', '>=', 51.8)]},
    {"success": 73.41, "samples": 267, "strategy": "TOP", "conditions": [('home_scores', '>=', 80.6), ('away', '>=', 51.8)]},
    {"success": 73.1, "samples": 394, "strategy": "TOP", "conditions": [('over_2_5', '>=', 69.6), ('away', '>=', 51.8)]},
    {"success": 72.47, "samples": 643, "strategy": "TOP", "conditions": [('odds_change_home', '>=', 0.22), ('odds_change_draw', '>=', 0.5)]},
    {"success": 72.36, "samples": 626, "strategy": "TOP", "conditions": [('odds_change_home', '>=', 0.5), ('odds_change_draw', '>=', 0.5)]},
    {"success": 72.89, "samples": 380, "strategy": "TOP", "conditions": [('over_1_5', '>=', 87.2), ('away', '>=', 51.8)]},

    # 3'lü - En İyiler
    {"success": 79.34, "samples": 213, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 78.26, "samples": 207, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 77.46, "samples": 142, "strategy": "TOP", "conditions": [('btts_yes', '>=', 62.5), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 76.83, "samples": 341, "strategy": "TOP", "conditions": [('over_3_5', '>=', 39.0), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 77.36, "samples": 53, "strategy": "TOP", "conditions": [('away', '>=', 47.5), ('odds_change_draw', '>=', 0.15), ('asian_up', '>=', 3.0)]},
    {"success": 75.94, "samples": 345, "strategy": "TOP", "conditions": [('over_2_5', '>=', 61.2), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 76.26, "samples": 198, "strategy": "TOP", "conditions": [('over_1_5', '>=', 85.0), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 76.16, "samples": 151, "strategy": "TOP", "conditions": [('home_scores', '>=', 79.1), ('away', '>=', 47.5), ('odds_change_draw', '>=', 0.3)]},
    {"success": 74.29, "samples": 385, "strategy": "TOP", "conditions": [('over_3_5', '>=', 39.0), ('away', '>=', 41.6), ('odds_change_draw', '>=', 0.3)]},
    {"success": 74.59, "samples": 244, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('away', '>=', 41.6), ('odds_change_draw', '>=', 0.3)]},
]

# ÇİFTE ŞANS 1X
CIFT_1X_TACTICS = [
    # 2'li - En İyiler
    {"success": 66.92, "samples": 1965, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 95.0)]},
    {"success": 66.21, "samples": 2498, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 68.46, "samples": 1205, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 68.56, "samples": 986, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('1x2_confidence', '>=', 95.0)]},
    {"success": 65.33, "samples": 2887, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('1x2_confidence', '>=', 95.0)]},
    {"success": 64.16, "samples": 3764, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('1x2_confidence', '>=', 90.0)]},
    {"success": 65.49, "samples": 1585, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('odds_change_home', '>=', 0.1)]},
    {"success": 64.48, "samples": 1979, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('odds_change_home', '>=', 0.02)]},
    {"success": 63.7, "samples": 2386, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('odds_change_home', '>=', 0.1)]},
    {"success": 66.46, "samples": 978, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('odds_change_home', '>=', 0.02)]},

    # 3'lü - En İyiler
    {"success": 86.54, "samples": 52, "strategy": "BALANCED", "conditions": [('draw', '>=', 27.4), ('odds_change_home', '>=', 0.32), ('asian_open', '>=', 0.75)]},
    {"success": 78.21, "samples": 78, "strategy": "TOP", "conditions": [('draw', '>=', 26.2), ('odds_change_home', '>=', 0.32), ('asian_open', '>=', 0.75)]},
    {"success": 77.59, "samples": 58, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 90.0), ('btts_yes', '>=', 58.8)]},
    {"success": 77.19, "samples": 57, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 95.0), ('btts_yes', '>=', 58.8)]},
    {"success": 76.87, "samples": 147, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('odds_change_home', '>=', 0.32), ('asian_open', '>=', 0.5)]},
    {"success": 76.25, "samples": 80, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.32), ('asian_open', '>=', 0.5)]},
    {"success": 75.0, "samples": 76, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('asian_down', '>=', 3.0), ('btts_yes', '>=', 55.8)]},
    {"success": 74.3, "samples": 214, "strategy": "TOP", "conditions": [('draw', '>=', 26.2), ('odds_change_home', '>=', 0.32), ('asian_open', '>=', 0.5)]},
    {"success": 72.84, "samples": 81, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('odds_change_home', '>=', 0.15), ('btts_yes', '>=', 58.8)]},
    {"success": 72.63, "samples": 95, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.15), ('asian_open', '>=', 0.75)]},
]

# ÇİFTE ŞANS X2
CIFT_X2_TACTICS = [
    # 2'li - En İyiler
    {"success": 66.34, "samples": 511, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 95.0)]},
    {"success": 62.22, "samples": 2263, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('away', '>=', 36.0)]},
    {"success": 65.89, "samples": 214, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_down', '>=', 4.0)]},
    {"success": 64.22, "samples": 939, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 85.0)]},
    {"success": 62.98, "samples": 1383, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('away', '>=', 36.0)]},
    {"success": 64.57, "samples": 621, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('away', '>=', 36.0)]},
    {"success": 60.91, "samples": 3216, "strategy": "TOP", "conditions": [('draw', '>=', 25.6), ('away', '>=', 36.0)]},
    {"success": 64.27, "samples": 722, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('btts_confidence', '>=', 87.0)]},
    {"success": 60.73, "samples": 2498, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 60.51, "samples": 2236, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_down', '>=', 0.0)]},

    # 3'lü - En İyiler
    {"success": 73.72, "samples": 137, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.32), ('btts_confidence', '>=', 95.0)]},
    {"success": 73.62, "samples": 163, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('btts_confidence', '>=', 95.0)]},
    {"success": 73.53, "samples": 68, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('odds_change_away', '>=', 0.3)]},
    {"success": 73.33, "samples": 60, "strategy": "TOP", "conditions": [('away', '>=', 41.6), ('1x2_confidence', '>=', 97.0), ('odds_change_away', '>=', 0.3)]},
    {"success": 72.99, "samples": 137, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('away', '>=', 37.5), ('odds_change_away', '>=', 0.3)]},
    {"success": 72.34, "samples": 141, "strategy": "TOP", "conditions": [('away', '>=', 41.6), ('1x2_confidence', '>=', 90.0), ('odds_change_away', '>=', 0.3)]},
    {"success": 71.95, "samples": 164, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('odds_change_away', '>=', 0.1)]},
    {"success": 71.08, "samples": 83, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('asian_up', '>=', 3.0)]},
    {"success": 70.61, "samples": 245, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('btts_confidence', '>=', 87.0)]},
    {"success": 70.77, "samples": 130, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('away', '>=', 37.5), ('asian_up', '>=', 2.0)]},
]

# ÇİFTE ŞANS 12
CIFT_12_TACTICS = [
    # 2'li - En İyiler
    {"success": 66.93, "samples": 1119, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 97.0)]},
    {"success": 64.79, "samples": 2028, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('over_under_confidence', '>=', 85.0)]},
    {"success": 64.25, "samples": 2498, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 90.0)]},
    {"success": 64.73, "samples": 1965, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('1x2_confidence', '>=', 95.0)]},
    {"success": 68.49, "samples": 146, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_up', '>=', 4.0)]},
    {"success": 64.07, "samples": 1979, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('odds_change_home', '>=', 0.02)]},
    {"success": 64.22, "samples": 1783, "strategy": "TOP", "conditions": [('draw', '>=', 28.2), ('goals_confidence', '>=', 65.0)]},
    {"success": 64.47, "samples": 1666, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('1x2_confidence', '>=', 97.0)]},
    {"success": 63.01, "samples": 2887, "strategy": "TOP", "conditions": [('draw', '>=', 26.8), ('1x2_confidence', '>=', 95.0)]},
    {"success": 62.84, "samples": 2236, "strategy": "TOP", "conditions": [('draw', '>=', 30.2), ('asian_down', '>=', 0.0)]},

    # 3'lü - En İyiler
    {"success": 76.92, "samples": 52, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 97.0), ('odds_change_away', '>=', 0.6)]},
    {"success": 72.09, "samples": 86, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('1x2_confidence', '>=', 97.0), ('odds_change_away', '>=', 0.6)]},
    {"success": 71.64, "samples": 67, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('odds_change_away', '>=', 0.1), ('asian_down', '>=', 3.0)]},
    {"success": 71.09, "samples": 128, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 97.0), ('asian_up', '>=', 3.0)]},
    {"success": 71.13, "samples": 97, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.05), ('odds_change_away', '>=', 0.1)]},
    {"success": 70.7, "samples": 157, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('1x2_confidence', '>=', 95.0), ('asian_up', '>=', 3.0)]},
    {"success": 70.77, "samples": 65, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('asian_down', '>=', 3.0), ('away_scores', '>=', 77.1)]},
    {"success": 70.06, "samples": 157, "strategy": "TOP", "conditions": [('draw', '>=', 26.2), ('odds_change_home', '>=', 0.05), ('odds_change_away', '>=', 0.1)]},
    {"success": 70.08, "samples": 127, "strategy": "TOP", "conditions": [('draw', '>=', 27.4), ('odds_change_home', '>=', 0.05), ('odds_change_away', '>=', 0.1)]},
    {"success": 69.49, "samples": 177, "strategy": "TOP", "conditions": [('draw', '>=', 29.0), ('odds_change_home', '>=', 0.05), ('away_scores', '>=', 77.1)]},
]

# İY1 - İLK YARI EV KAZANIR
HT_1_TACTICS = [
    # 2'li - En İyiler
    {"success": 71.43, "samples": 98, "strategy": "TOP", "conditions": [('ht_away', '>=', 33.8), ('home', '>=', 59.3)]},
    {"success": 69.0, "samples": 971, "strategy": "TOP", "conditions": [('home', '>=', 59.3), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 67.96, "samples": 1055, "strategy": "TOP", "conditions": [('home', '>=', 59.3), ('ht_goal_line_close', '>=', 1.5)]},
    {"success": 70.0, "samples": 50, "strategy": "TOP", "conditions": [('ht_away', '>=', 37.5), ('home', '>=', 59.3)]},
    {"success": 69.19, "samples": 172, "strategy": "TOP", "conditions": [('ht_away', '>=', 30.9), ('home', '>=', 59.3)]},
    {"success": 66.1, "samples": 652, "strategy": "TOP", "conditions": [('ht_odds_change_draw', '>=', 5.1), ('home', '>=', 59.3)]},
    {"success": 63.8, "samples": 1326, "strategy": "TOP", "conditions": [('home', '>=', 52.4), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 62.6, "samples": 1853, "strategy": "TOP", "conditions": [('home', '>=', 59.3), ('ht_goal_line_close', '>=', 1.25)]},
    {"success": 63.74, "samples": 1332, "strategy": "TOP", "conditions": [('ht_asian_close', '>=', 0.5), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 64.8, "samples": 841, "strategy": "TOP", "conditions": [('ht_odds_change_away', '>=', 9.3), ('home', '>=', 59.3)]},

    # 3'lü - En İyiler
    {"success": 71.43, "samples": 56, "strategy": "TOP", "conditions": [('ht_draw', '>=', 45.0), ('ht_asian_close', '>=', 0.5), ('ht_over_0_5', '>=', 74.0)]},
    {"success": 70.37, "samples": 216, "strategy": "TOP", "conditions": [('ht_odds_change_draw', '>=', 4.3), ('home', '>=', 55.5), ('ht_over_1_5', '>=', 28.4)]},
    {"success": 69.23, "samples": 312, "strategy": "TOP", "conditions": [('ht_asian_up', '>=', 1.0), ('home', '>=', 55.5), ('ht_over_1_5', '>=', 28.4)]},
    {"success": 69.35, "samples": 62, "strategy": "TOP", "conditions": [('ht_asian_close', '>=', 0.5), ('ht_asian_up', '>=', 1.0), ('draw', '>=', 27.4)]},
    {"success": 69.23, "samples": 52, "strategy": "TOP", "conditions": [('ht_odds_change_away', '>=', 1.8), ('ht_asian_close', '>=', 0.5), ('draw', '>=', 27.4)]},
    {"success": 68.66, "samples": 268, "strategy": "TOP", "conditions": [('ht_odds_change_draw', '>=', 2.2), ('home', '>=', 55.5), ('ht_over_1_5', '>=', 28.4)]},
    {"success": 68.85, "samples": 61, "strategy": "TOP", "conditions": [('ht_draw', '>=', 45.0), ('home', '>=', 55.5), ('ht_over_1_5', '>=', 24.6)]},
    {"success": 68.85, "samples": 61, "strategy": "TOP", "conditions": [('ht_away', '>=', 32.5), ('ht_asian_down', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 68.4, "samples": 212, "strategy": "TOP", "conditions": [('ht_odds_change_draw', '>=', 4.3), ('ht_asian_open', '>=', 0.5), ('ht_over_1_5', '>=', 28.4)]},
    {"success": 68.67, "samples": 83, "strategy": "TOP", "conditions": [('ht_home', '>=', 40.0), ('ht_away', '>=', 32.5), ('home', '>=', 55.5)]},
]

# İY2 - İLK YARI DEPLASMAN KAZANIR
HT_2_TACTICS = [
    # 2'li - En İyiler
    {"success": 55.01, "samples": 369, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 14.6), ('ht_odds_change_draw', '>=', 5.1)]},
    {"success": 53.14, "samples": 303, "strategy": "TOP", "conditions": [('ht_away', '>=', 42.5), ('ht_odds_change_draw', '>=', 5.1)]},
    {"success": 52.69, "samples": 465, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 7.6), ('ht_odds_change_draw', '>=', 5.1)]},
    {"success": 50.75, "samples": 601, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 14.6), ('ht_odds_change_draw', '>=', 2.6)]},
    {"success": 50.0, "samples": 528, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 3.6), ('ht_odds_change_draw', '>=', 5.1)]},
    {"success": 50.0, "samples": 422, "strategy": "TOP", "conditions": [('ht_away', '>=', 42.5), ('ht_odds_change_home', '>=', 14.6)]},
    {"success": 49.43, "samples": 619, "strategy": "TOP", "conditions": [('ht_away', '>=', 42.5), ('ht_goal_line_close', '>=', 1.5)]},
    {"success": 49.34, "samples": 602, "strategy": "TOP", "conditions": [('ht_away', '>=', 42.5), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 49.06, "samples": 265, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 14.6), ('ht_goal_line_up', '>=', 2.0)]},
    {"success": 47.47, "samples": 851, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 7.6), ('ht_odds_change_draw', '>=', 2.6)]},

    # 3'lü - En İyiler
    {"success": 62.75, "samples": 51, "strategy": "TOP", "conditions": [('ht_home', '>=', 35.2), ('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3)]},
    {"success": 59.56, "samples": 136, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_over_1_5', '>=', 28.4)]},
    {"success": 58.78, "samples": 262, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_over_0_5', '>=', 74.0)]},
    {"success": 58.85, "samples": 209, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_over_1_5', '>=', 24.6)]},
    {"success": 56.9, "samples": 406, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_goal_line_close', '>=', 1.25)]},
    {"success": 57.35, "samples": 204, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_over_0_5', '>=', 77.2)]},
    {"success": 57.43, "samples": 101, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_goals_confidence', '>=', 95.0)]},
    {"success": 57.05, "samples": 149, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_over_0_5', '>=', 80.0)]},
    {"success": 56.3, "samples": 254, "strategy": "TOP", "conditions": [('ht_away', '>=', 40.0), ('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3)]},
    {"success": 56.02, "samples": 332, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3), ('ht_goal_line_open', '>=', 1.25)]},
]

# İYX - İLK YARI BERABERLİK
HT_X_TACTICS = [
    # 2'li - En İyiler
    {"success": 54.5, "samples": 189, "strategy": "TOP", "conditions": [('ht_asian_down', '>=', 2.0), ('draw', '>=', 30.2)]},
    {"success": 49.81, "samples": 2140, "strategy": "TOP", "conditions": [('ht_draw', '>=', 49.8), ('draw', '>=', 28.2)]},
    {"success": 49.08, "samples": 2718, "strategy": "TOP", "conditions": [('ht_draw', '>=', 49.8), ('draw', '>=', 26.8)]},
    {"success": 48.8, "samples": 2793, "strategy": "TOP", "conditions": [('ht_draw', '>=', 46.0), ('draw', '>=', 28.2)]},
    {"success": 49.38, "samples": 1843, "strategy": "TOP", "conditions": [('ht_draw', '>=', 43.2), ('draw', '>=', 30.2)]},
    {"success": 48.52, "samples": 3287, "strategy": "TOP", "conditions": [('ht_draw', '>=', 43.2), ('draw', '>=', 28.2)]},
    {"success": 49.67, "samples": 1643, "strategy": "TOP", "conditions": [('ht_draw', '>=', 46.0), ('draw', '>=', 30.2)]},
    {"success": 48.28, "samples": 3144, "strategy": "TOP", "conditions": [('ht_draw', '>=', 49.8), ('draw', '>=', 25.6)]},
    {"success": 48.24, "samples": 3047, "strategy": "TOP", "conditions": [('ht_odds_change_away', '>=', 0.0), ('draw', '>=', 28.2)]},
    {"success": 48.17, "samples": 2236, "strategy": "TOP", "conditions": [('ht_asian_down', '>=', 0.0), ('draw', '>=', 30.2)]},

    # 3'lü - En İyiler
    {"success": 62.9, "samples": 62, "strategy": "TOP", "conditions": [('ht_draw', '>=', 45.0), ('ht_away', '>=', 35.0), ('ht_odds_change_away', '>=', 13.0)]},
    {"success": 61.54, "samples": 78, "strategy": "TOP", "conditions": [('ht_draw', '>=', 47.5), ('ht_away', '>=', 35.0), ('ht_odds_change_away', '>=', 6.7)]},
    {"success": 60.0, "samples": 55, "strategy": "TOP", "conditions": [('ht_draw', '>=', 51.2), ('ht_odds_change_home', '>=', 10.1), ('ht_odds_change_draw', '>=', 4.3)]},
    {"success": 59.38, "samples": 128, "strategy": "TOP", "conditions": [('ht_draw', '>=', 45.0), ('ht_away', '>=', 35.0), ('ht_odds_change_away', '>=', 6.7)]},
    {"success": 59.21, "samples": 76, "strategy": "TOP", "conditions": [('ht_odds_change_home', '>=', 5.0), ('ht_odds_change_draw', '>=', 4.3), ('draw', '>=', 27.4)]},
    {"success": 58.82, "samples": 51, "strategy": "TOP", "conditions": [('ht_home', '>=', 32.5), ('ht_draw', '>=', 51.2), ('draw', '>=', 29.0)]},
    {"success": 58.18, "samples": 55, "strategy": "TOP", "conditions": [('ht_draw', '>=', 51.2), ('ht_away', '>=', 35.0), ('draw', '>=', 27.4)]},
    {"success": 57.97, "samples": 69, "strategy": "TOP", "conditions": [('ht_away', '>=', 40.0), ('draw', '>=', 26.2), ('ht_goals_confidence', '>=', 95.0)]},
    {"success": 57.81, "samples": 64, "strategy": "TOP", "conditions": [('ht_draw', '>=', 51.2), ('ht_odds_change_home', '>=', 5.0), ('ht_asian_up', '>=', 1.0)]},
    {"success": 57.3, "samples": 185, "strategy": "TOP", "conditions": [('ht_1x2_confidence', '>=', 85.0), ('ht_odds_change_home', '>=', 10.1), ('draw', '>=', 29.0)]},
]

# 2.5 ÜST
OVER_2_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 79.77, "samples": 682, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 2.0)]},
    {"success": 78.52, "samples": 1094, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 1.0)]},
    {"success": 79.81, "samples": 421, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 3.0)]},
    {"success": 78.46, "samples": 896, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('home', '>=', 59.3)]},
    {"success": 75.74, "samples": 1999, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('goal_line_close', '>=', 3.5)]},
    {"success": 77.17, "samples": 1253, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('goal_line_open', '>=', 3.5)]},
    {"success": 75.67, "samples": 1891, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('goal_line_open', '>=', 3.5)]},
    {"success": 74.94, "samples": 2370, "strategy": "TOP", "conditions": [('over_2_5', '>=', 59.2), ('goal_line_close', '>=', 3.5)]},
    {"success": 76.86, "samples": 1314, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('goal_line_close', '>=', 3.5)]},
    {"success": 74.83, "samples": 2420, "strategy": "TOP", "conditions": [('over_3_5', '>=', 36.9), ('goal_line_close', '>=', 3.5)]},

    # 3'lü - En İyiler
    {"success": 80.67, "samples": 238, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_down', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 80.25, "samples": 81, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 95.0), ('home', '>=', 55.5)]},
    {"success": 79.67, "samples": 246, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_down', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 80.0, "samples": 95, "strategy": "TOP", "conditions": [('over_1_5', '>=', 85.0), ('over_under_confidence', '>=', 87.0), ('home', '>=', 55.5)]},
    {"success": 79.06, "samples": 277, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.25), ('goal_line_up', '>=', 2.0), ('away', '>=', 47.5)]},
    {"success": 78.44, "samples": 524, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.25), ('goal_line_up', '>=', 2.0), ('home', '>=', 55.5)]},
    {"success": 78.21, "samples": 624, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_open', '>=', 3.25), ('goal_line_up', '>=', 2.0)]},
    {"success": 78.85, "samples": 312, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_up', '>=', 2.0), ('home', '>=', 55.5)]},
    {"success": 77.72, "samples": 781, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_open', '>=', 3.25), ('home', '>=', 55.5)]},
    {"success": 77.62, "samples": 782, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_open', '>=', 3.25), ('home', '>=', 55.5)]},
]

# 2.5 ALT
UNDER_2_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 70.54, "samples": 258, "strategy": "TOP", "conditions": [('goals_confidence', '>=', 95.0), ('draw', '>=', 30.2)]},
    {"success": 66.44, "samples": 897, "strategy": "TOP", "conditions": [('goal_line_down', '>=', 1.0), ('draw', '>=', 30.2)]},
    {"success": 67.59, "samples": 361, "strategy": "TOP", "conditions": [('goal_line_down', '>=', 3.0), ('draw', '>=', 30.2)]},
    {"success": 67.19, "samples": 512, "strategy": "TOP", "conditions": [('goals_confidence', '>=', 85.0), ('draw', '>=', 30.2)]},
    {"success": 63.33, "samples": 2236, "strategy": "TOP", "conditions": [('goal_line_down', '>=', 0.0), ('draw', '>=', 30.2)]},
    {"success": 63.33, "samples": 2236, "strategy": "TOP", "conditions": [('goal_line_up', '>=', 0.0), ('draw', '>=', 30.2)]},
    {"success": 66.07, "samples": 949, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 85.0), ('draw', '>=', 30.2)]},
    {"success": 66.38, "samples": 803, "strategy": "TOP", "conditions": [('goals_confidence', '>=', 65.0), ('draw', '>=', 30.2)]},
    {"success": 66.38, "samples": 586, "strategy": "TOP", "conditions": [('goal_line_down', '>=', 2.0), ('draw', '>=', 30.2)]},
    {"success": 63.12, "samples": 2028, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 85.0), ('draw', '>=', 28.2)]},

    # 3'lü - En İyiler
    {"success": 72.45, "samples": 98, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 87.0), ('away_scores', '>=', 77.1), ('draw', '>=', 29.0)]},
    {"success": 71.93, "samples": 57, "strategy": "TOP", "conditions": [('away_scores', '>=', 77.1), ('goals_confidence', '>=', 85.0), ('draw', '>=', 29.0)]},
    {"success": 71.62, "samples": 74, "strategy": "TOP", "conditions": [('away_scores', '>=', 77.1), ('goals_confidence', '>=', 75.0), ('draw', '>=', 29.0)]},
    {"success": 70.59, "samples": 68, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 95.0), ('away_scores', '>=', 77.1), ('draw', '>=', 29.0)]},
    {"success": 69.23, "samples": 78, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 85.0), ('away_scores', '>=', 84.2), ('draw', '>=', 27.4)]},
    {"success": 68.92, "samples": 74, "strategy": "TOP", "conditions": [('away_scores', '>=', 84.2), ('goal_line_down', '>=', 1.0), ('draw', '>=', 27.4)]},
    {"success": 67.99, "samples": 453, "strategy": "TOP", "conditions": [('btts_confidence', '>=', 87.0), ('goal_line_down', '>=', 2.0), ('draw', '>=', 29.0)]},
    {"success": 67.34, "samples": 542, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 85.0), ('goal_line_down', '>=', 2.0), ('draw', '>=', 29.0)]},
    {"success": 67.04, "samples": 631, "strategy": "TOP", "conditions": [('btts_confidence', '>=', 87.0), ('goal_line_down', '>=', 1.0), ('draw', '>=', 29.0)]},
    {"success": 66.67, "samples": 780, "strategy": "TOP", "conditions": [('over_under_confidence', '>=', 85.0), ('goal_line_down', '>=', 1.0), ('draw', '>=', 29.0)]},
]

# 1.5 ÜST
OVER_1_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 89.29, "samples": 1999, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 63.5), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.8, "samples": 2420, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 36.9), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.78, "samples": 2370, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 59.2), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.75, "samples": 2249, "strategy": "BALANCED", "conditions": [('over_1_5', '>=', 80.3), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.61, "samples": 2231, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 59.2), ('goal_line_open', '>=', 3.5)]},
    {"success": 88.52, "samples": 2318, "strategy": "BALANCED", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.5, "samples": 2573, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 55.5), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.46, "samples": 2271, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 36.9), ('goal_line_open', '>=', 3.5)]},
    {"success": 88.46, "samples": 2470, "strategy": "BALANCED", "conditions": [('over_1_5', '>=', 77.8), ('goal_line_close', '>=', 3.5)]},
    {"success": 88.42, "samples": 2625, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 33.3), ('goal_line_close', '>=', 3.5)]},

    # 3'lü - En İyiler
    {"success": 88.11, "samples": 2396, "strategy": "BALANCED", "conditions": [('over_1_5', '>=', 79.1), ('over_2_5', '>=', 66.2), ('goal_line_close', '>=', 3.25)]},
    {"success": 88.1, "samples": 2412, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_close', '>=', 3.25), ('goal_line_down', '>=', 0.0)]},
    {"success": 88.1, "samples": 2412, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_close', '>=', 3.25), ('goal_line_up', '>=', 0.0)]},
    {"success": 88.1, "samples": 2386, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_open', '>=', 3.0), ('goal_line_close', '>=', 3.25)]},
    {"success": 88.01, "samples": 2393, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('over_3_5', '>=', 35.0), ('goal_line_close', '>=', 3.25)]},
    {"success": 87.97, "samples": 2360, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('over_3_5', '>=', 39.0), ('goal_line_close', '>=', 3.25)]},
    {"success": 87.95, "samples": 2316, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_open', '>=', 3.25), ('goal_line_close', '>=', 3.0)]},
    {"success": 87.94, "samples": 2354, "strategy": "BALANCED", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_open', '>=', 3.25), ('goal_line_close', '>=', 3.0)]},
    {"success": 87.91, "samples": 2209, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_open', '>=', 3.25), ('goal_line_close', '>=', 3.25)]},
    {"success": 87.9, "samples": 2323, "strategy": "BALANCED", "conditions": [('over_1_5', '>=', 81.8), ('over_2_5', '>=', 66.2), ('goal_line_close', '>=', 3.25)]},
]

# 3.5 ÜST
OVER_3_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 62.76, "samples": 682, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 2.0)]},
    {"success": 60.57, "samples": 1253, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('goal_line_open', '>=', 3.5)]},
    {"success": 60.79, "samples": 1094, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 1.0)]},
    {"success": 62.0, "samples": 421, "strategy": "TOP", "conditions": [('goal_line_open', '>=', 3.5), ('goal_line_up', '>=', 3.0)]},
    {"success": 59.89, "samples": 1314, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('goal_line_close', '>=', 3.5)]},
    {"success": 61.48, "samples": 514, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('home', '>=', 59.3)]},
    {"success": 56.87, "samples": 2031, "strategy": "TOP", "conditions": [('over_3_5', '>=', 41.2), ('goal_line_close', '>=', 3.5)]},
    {"success": 56.93, "samples": 1999, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('goal_line_close', '>=', 3.5)]},
    {"success": 57.11, "samples": 1891, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('goal_line_open', '>=', 3.5)]},
    {"success": 57.35, "samples": 1735, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('goal_line_close', '>=', 3.25)]},

    # 3'lü - En İyiler
    {"success": 64.42, "samples": 312, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_up', '>=', 2.0), ('home', '>=', 55.5)]},
    {"success": 63.98, "samples": 261, "strategy": "TOP", "conditions": [('over_1_5', '>=', 85.0), ('goal_line_up', '>=', 2.0), ('home', '>=', 55.5)]},
    {"success": 62.85, "samples": 498, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_up', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 62.99, "samples": 308, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_up', '>=', 2.0), ('home', '>=', 55.5)]},
    {"success": 62.5, "samples": 424, "strategy": "TOP", "conditions": [('over_1_5', '>=', 85.0), ('goal_line_up', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 62.09, "samples": 488, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('goal_line_up', '>=', 1.0), ('home', '>=', 55.5)]},
    {"success": 62.05, "samples": 390, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_up', '>=', 2.0), ('home', '>=', 49.8)]},
    {"success": 61.22, "samples": 624, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_open', '>=', 3.25), ('goal_line_up', '>=', 2.0)]},
    {"success": 62.16, "samples": 185, "strategy": "TOP", "conditions": [('over_1_5', '>=', 85.0), ('goal_line_up', '>=', 2.0), ('away', '>=', 47.5)]},
    {"success": 61.32, "samples": 455, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('goal_line_up', '>=', 2.0), ('home', '>=', 45.7)]},
]

# KG VAR - KARŞILIKLI GOL VAR
KG_VAR_TACTICS = [
    # 2'li - En İyiler
    {"success": 67.62, "samples": 281, "strategy": "TOP", "conditions": [('over_2_5', '>=', 69.6), ('over_under_confidence', '>=', 87.0)]},
    {"success": 67.63, "samples": 139, "strategy": "TOP", "conditions": [('btts_yes', '>=', 65.0), ('goal_line_down', '>=', 3.0)]},
    {"success": 62.91, "samples": 1890, "strategy": "TOP", "conditions": [('btts_yes', '>=', 60.5), ('btts_confidence', '>=', 85.0)]},
    {"success": 64.58, "samples": 1036, "strategy": "TOP", "conditions": [('btts_yes', '>=', 60.5), ('over_under_confidence', '>=', 87.0)]},
    {"success": 63.03, "samples": 1712, "strategy": "TOP", "conditions": [('btts_yes', '>=', 60.5), ('goals_confidence', '>=', 65.0)]},
    {"success": 65.06, "samples": 747, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('over_under_confidence', '>=', 87.0)]},
    {"success": 62.91, "samples": 1615, "strategy": "TOP", "conditions": [('btts_yes', '>=', 60.5), ('goals_confidence', '>=', 75.0)]},
    {"success": 64.93, "samples": 690, "strategy": "TOP", "conditions": [('over_3_5', '>=', 41.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 62.82, "samples": 1568, "strategy": "TOP", "conditions": [('btts_yes', '>=', 60.5), ('over_under_confidence', '>=', 85.0)]},
    {"success": 65.23, "samples": 440, "strategy": "TOP", "conditions": [('btts_yes', '>=', 65.0), ('over_under_confidence', '>=', 87.0)]},

    # 3'lü - En İyiler
    {"success": 72.58, "samples": 186, "strategy": "TOP", "conditions": [('away_scores', '>=', 84.2), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 71.7, "samples": 212, "strategy": "TOP", "conditions": [('away_scores', '>=', 84.2), ('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 71.85, "samples": 135, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 87.0), ('goal_line_down', '>=', 1.0)]},
    {"success": 71.27, "samples": 362, "strategy": "TOP", "conditions": [('btts_yes', '>=', 62.5), ('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 71.62, "samples": 74, "strategy": "TOP", "conditions": [('away_scores', '>=', 80.4), ('goal_line_down', '>=', 2.0), ('goal_line_up', '>=', 2.0)]},
    {"success": 71.43, "samples": 112, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 87.0), ('goal_line_down', '>=', 1.0)]},
    {"success": 71.07, "samples": 159, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 87.0), ('goal_line_up', '>=', 2.0)]},
    {"success": 70.54, "samples": 258, "strategy": "TOP", "conditions": [('away_scores', '>=', 80.4), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 69.92, "samples": 389, "strategy": "TOP", "conditions": [('btts_yes', '>=', 58.8), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 87.0)]},
    {"success": 69.86, "samples": 418, "strategy": "TOP", "conditions": [('btts_yes', '>=', 58.8), ('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 87.0)]},
]

# İY 0.5 ÜST - İLK YARI EN AZ 1 GOL
HT_OVER_0_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 85.36, "samples": 840, "strategy": "BALANCED", "conditions": [('ht_goal_line_open', '>=', 1.25), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 85.9, "samples": 468, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 85.0), ('over_3_5', '>=', 48.41)]},
    {"success": 86.06, "samples": 330, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('over_2_5', '>=', 69.6)]},
    {"success": 81.57, "samples": 2452, "strategy": "BALANCED", "conditions": [('over_2_5', '>=', 59.2), ('ht_goal_line_open', '>=', 1.25)]},
    {"success": 81.98, "samples": 2026, "strategy": "BALANCED", "conditions": [('ht_over_0_5', '>=', 75.0), ('ht_goal_line_open', '>=', 1.25)]},
    {"success": 81.56, "samples": 2164, "strategy": "BALANCED", "conditions": [('ht_over_1_5', '>=', 30.0), ('ht_goal_line_open', '>=', 1.25)]},
    {"success": 81.45, "samples": 2237, "strategy": "BALANCED", "conditions": [('ht_over_1_5', '>=', 30.0), ('ht_goal_line_close', '>=', 1.25)]},
    {"success": 81.42, "samples": 2643, "strategy": "BALANCED", "conditions": [('ht_goal_line_open', '>=', 1.5), ('ht_goal_line_close', '>=', 1.50)]},

    # 3'lü - En İyiler
    {"success": 90.91, "samples": 55, "strategy": "AGGRESSIVE", "conditions": [('ht_draw', '>=', 45.0), ('ht_away', '>=', 35.0), ('over_3_5', '>=', 44.2)]},
    {"success": 87.5, "samples": 80, "strategy": "BALANCED", "conditions": [('ht_draw', '>=', 45.0), ('ht_away', '>=', 32.5), ('over_3_5', '>=', 44.2)]},
    {"success": 86.93, "samples": 176, "strategy": "BALANCED", "conditions": [('ht_over_0_5', '>=', 80.0), ('ht_goals_confidence', '>=', 95.0), ('over_under_confidence', '>=', 95.0)]},
    {"success": 87.04, "samples": 54, "strategy": "BALANCED", "conditions": [('ht_draw', '>=', 47.5), ('ht_away', '>=', 35.0), ('over_3_5', '>=', 39.0)]},
    {"success": 86.27, "samples": 153, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('ht_away', '>=', 40.0), ('over_1_5', '>=', 85.0)]},
    {"success": 86.42, "samples": 81, "strategy": "BALANCED", "conditions": [('ht_over_1_5', '>=', 20.9), ('ht_draw', '>=', 47.5), ('over_1_5', '>=', 85.0)]},
    {"success": 86.21, "samples": 145, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('ht_away', '>=', 40.0), ('over_2_5', '>=', 66.2)]},
    {"success": 86.15, "samples": 130, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('ht_away', '>=', 40.0), ('over_3_5', '>=', 44.2)]},
    {"success": 85.98, "samples": 164, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('ht_home', '>=', 40.0), ('over_3_5', '>=', 44.2)]},
    {"success": 85.41, "samples": 329, "strategy": "BALANCED", "conditions": [('ht_goals_confidence', '>=', 95.0), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 85.0)]},
]

# İY 1.5 ÜST - İLK YARI EN AZ 2 GOL
HT_OVER_1_5_TACTICS = [
    # 2'li - En İyiler
    {"success": 60.0, "samples": 840, "strategy": "TOP", "conditions": [('ht_goal_line_open', '>=', 1.5), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 59.63, "samples": 327, "strategy": "TOP", "conditions": [('ht_goal_line_open', '>=', 1.5), ('ht_goal_line_up', '>=', 2.0)]},
    {"success": 56.63, "samples": 1328, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 54.57, "samples": 2045, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 55.7, "samples": 1368, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('ht_goal_line_close', '>=', 1.5)]},
    {"success": 53.99, "samples": 2119, "strategy": "TOP", "conditions": [('over_2_5', '>=', 63.5), ('ht_goal_line_close', '>=', 1.5)]},
    {"success": 53.71, "samples": 2493, "strategy": "TOP", "conditions": [('over_3_5', '>=', 36.9), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 53.91, "samples": 2083, "strategy": "TOP", "conditions": [('over_3_5', '>=', 41.2), ('ht_goal_line_open', '>=', 1.5)]},
    {"success": 53.58, "samples": 2643, "strategy": "TOP", "conditions": [('ht_goal_line_open', '>=', 1.5), ('ht_goal_line_close', '>=', 1.5)]},
    {"success": 58.02, "samples": 212, "strategy": "TOP", "conditions": [('over_3_5', '>=', 48.41), ('ht_goal_line_up', '>=', 2.0)]},

    # 3'lü - En İyiler
    {"success": 65.17, "samples": 89, "strategy": "TOP", "conditions": [('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 95.0), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 60.66, "samples": 244, "strategy": "TOP", "conditions": [('ht_away', '>=', 40.0), ('over_3_5', '>=', 44.2), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 60.0, "samples": 95, "strategy": "TOP", "conditions": [('over_2_5', '>=', 66.2), ('over_under_confidence', '>=', 95.0), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 59.55, "samples": 89, "strategy": "TOP", "conditions": [('ht_away', '>=', 40.0), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 95.0)]},
    {"success": 58.54, "samples": 451, "strategy": "TOP", "conditions": [('ht_over_1_5', '>=', 28.4), ('over_3_5', '>=', 44.2), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 59.23, "samples": 130, "strategy": "TOP", "conditions": [('ht_away', '>=', 35.0), ('over_3_5', '>=', 44.2), ('over_under_confidence', '>=', 95.0)]},
    {"success": 58.85, "samples": 243, "strategy": "TOP", "conditions": [('ht_away', '>=', 40.0), ('over_2_5', '>=', 66.2), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 58.52, "samples": 364, "strategy": "TOP", "conditions": [('ht_away', '>=', 35.0), ('over_3_5', '>=', 44.2), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 58.16, "samples": 423, "strategy": "TOP", "conditions": [('ht_away', '>=', 32.5), ('over_3_5', '>=', 44.2), ('ht_goal_line_up', '>=', 1.0)]},
    {"success": 58.82, "samples": 51, "strategy": "TOP", "conditions": [('ht_over_1_5', '>=', 24.6), ('ht_draw', '>=', 47.5), ('over_1_5', '>=', 85.0)]},
]

# Alan eşleştirmeleri (tactics field → API yolları)
FIELD_MAPPINGS = {
    # Goal Lines
    "over_3_5": ["final_predictions", "goal_lines", "over_3_5"],
    "over_2_5": ["final_predictions", "goal_lines", "over_2_5"],
    "over_1_5": ["final_predictions", "goal_lines", "over_1_5"],
    "under_2_5": ["final_predictions", "goal_lines", "under_2_5"],
    "under_1_5": ["final_predictions", "goal_lines", "under_1_5"],
    
    # BTTS
    "btts_yes": ["final_predictions", "btts", "yes"],
    "btts_no": ["final_predictions", "btts", "no"],
    "btts_confidence": ["final_predictions", "btts", "confidence"],
    
    # Team Scoring
    "home_scores": ["final_predictions", "team_scoring", "home_team_scores"],
    "away_scores": ["final_predictions", "team_scoring", "away_team_scores"],
    
    # 1X2
    "home": ["final_predictions", "1x2", "home"],
    "draw": ["final_predictions", "1x2", "draw"],
    "away": ["final_predictions", "1x2", "away"],
    "1x2_confidence": ["final_predictions", "1x2", "confidence"],
    
    # Half-Time Goals
    "ht_over_0_5": ["final_predictions", "ht_goals", "over_0_5"],
    "ht_over_1_5": ["final_predictions", "ht_goals", "over_1_5"],
    "ht_under_0_5": ["final_predictions", "ht_goals", "under_0_5"],
    "ht_under_1_5": ["final_predictions", "ht_goals", "under_1_5"],
    "ht_goals_confidence": ["final_predictions", "ht_goals", "confidence"],
    
    # Half-Time 1X2
    "ht_home": ["final_predictions", "ht_1x2", "home"],
    "ht_draw": ["final_predictions", "ht_1x2", "draw"],
    "ht_away": ["final_predictions", "ht_1x2", "away"],
    "ht_1x2_confidence": ["final_predictions", "ht_1x2", "confidence"],
    
    # Confidence Scores
    "goals_confidence": ["final_predictions", "goal_lines", "confidence"],
    "over_under_confidence": ["final_predictions", "goal_lines", "confidence"],
    
    # Odds Movement
    "odds_change_home": ["odds_trend_analysis", "european_odds_movement", "changes", "home"],
    "odds_change_away": ["odds_trend_analysis", "european_odds_movement", "changes", "away"],
    "odds_change_draw": ["odds_trend_analysis", "european_odds_movement", "changes", "draw"],

    # European Odds Closing Values
    "ms1_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "home"],
    "ms2_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "away"],
    "msx_close_odds": ["odds_trend_analysis", "european_odds_movement", "pre_match_odds", "draw"],
    
    # Half-Time Odds Changes
    "ht_odds_change_home": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "home"],
    "ht_odds_change_away": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "away"],
    "ht_odds_change_draw": ["odds_trend_analysis", "ht_european_odds_movement", "changes", "draw"],
    
    # Asian Handicap
    "asian_open": ["odds_trend_analysis", "asian_handicap_line_movement", "first_line"],
    "asian_close": ["odds_trend_analysis", "asian_handicap_line_movement", "pre_match_line"],
    "asian_up": ["odds_trend_analysis", "asian_handicap_line_movement", "line_increased"],
    "asian_down": ["odds_trend_analysis", "asian_handicap_line_movement", "line_decreased"],
    
    # Half-Time Asian
    "ht_asian_open": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "first_line"],
    "ht_asian_close": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "pre_match_line"],
    "ht_asian_up": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "line_increased"],
    "ht_asian_down": ["odds_trend_analysis", "ht_asian_handicap_line_movement", "line_decreased"],
    
    # Goal Line Movement
    "goal_line_open": ["odds_trend_analysis", "over_under_line_movement", "first_line"],
    "goal_line_close": ["odds_trend_analysis", "over_under_line_movement", "pre_match_line"],
    "goal_line_up": ["odds_trend_analysis", "over_under_line_movement", "line_increased"],
    "goal_line_down": ["odds_trend_analysis", "over_under_line_movement", "line_decreased"],
    
    # Half-Time Goal Line
    "ht_goal_line_open": ["odds_trend_analysis", "ht_over_under_line_movement", "first_line"],
    "ht_goal_line_close": ["odds_trend_analysis", "ht_over_under_line_movement", "pre_match_line"],
    "ht_goal_line_up": ["odds_trend_analysis", "ht_over_under_line_movement", "line_increased"],
    "ht_goal_line_down": ["odds_trend_analysis", "ht_over_under_line_movement", "line_decreased"],
}
