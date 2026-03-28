"""
Final Predictions Module
Combines all analysis sources with weighted averages to produce final predictions
"""

import logging
import statistics


def calculate_final_predictions(analysis_data):
    """
    Tüm analiz kaynaklarını birleştirerek ağırlıklı final tahminler üretir.
    
    Args:
        analysis_data (dict): Tüm analiz sonuçları
        
    Returns:
        dict: Final tahminler ve confidence skorları
    """
    try:
        # Mevcut kaynaklar (4 kaynak)
        correct_score = analysis_data.get('correct_score_predictions', {}).get('derived_predictions', {})
        h2h = analysis_data.get('h2h_analysis', {}).get('final_predictions', {})
        team_perf = analysis_data.get('team_performance_analysis', {}).get('crosstab_final_predictions', {})
        odds = analysis_data.get('odds_analysis', {}).get('1x2_analysis', {})

        # YENİ kaynaklar (Eagle eklentileri)
        poisson = analysis_data.get('poisson_predictions', {})
        odds_movement = analysis_data.get('odds_movement_predictions', {})
        streaks = analysis_data.get('streak_predictions', {})
        streak_signals = streaks.get('signals', {}) if streaks else {}

        final_predictions = {}

        # 1X2 - 4 → 7 kaynak (+ poisson, odds_movement, streaks)
        final_predictions['1x2'] = calculate_1x2_final(correct_score, h2h, team_perf, odds,
                                                         poisson, odds_movement, streak_signals)

        # Goal Lines - 3 → 6 kaynak
        final_predictions['goal_lines'] = calculate_goal_lines_final(correct_score, h2h, team_perf,
                                                                       poisson, odds_movement, streak_signals)

        # BTTS - 3 → 5 kaynak
        final_predictions['btts'] = calculate_btts_final(correct_score, h2h, team_perf,
                                                          poisson, streak_signals)

        # HT 1X2 - 2 → 4 kaynak
        final_predictions['ht_1x2'] = calculate_ht_1x2_final(h2h, team_perf,
                                                                poisson, odds_movement)

        # HT Goals - 2 → 4 kaynak
        final_predictions['ht_goals'] = calculate_ht_goals_final(h2h, team_perf,
                                                                    poisson, streak_signals)

        # HT BTTS - 1 kaynak (değişmedi)
        final_predictions['ht_btts'] = calculate_ht_btts_final(h2h)

        # Team Scoring - 2 kaynak (değişmedi)
        final_predictions['team_scoring'] = calculate_team_scoring_final(h2h, team_perf)

        # YENİ: Kaynak sayısını metadata olarak ekle
        final_predictions['_eagle_sources'] = {
            'poisson': bool(poisson),
            'odds_movement': bool(odds_movement),
            'streaks': bool(streaks),
            'total_sources': 4 + sum(1 for x in [poisson, odds_movement, streaks] if x),
        }

        return {
            'final_predictions': final_predictions
        }
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in calculate_final_predictions: {str(e)}")
        return {'error': f'Final predictions failed: {str(e)}'}


def calculate_1x2_final(correct_score, h2h, team_perf, odds,
                         poisson=None, odds_movement=None, streak_signals=None):
    """
    1X2 için ağırlıklı final tahmin.
    Orijinal: Team Perf 30%, Odds 30%, H2H 25%, Correct Score 15%
    Eagle: + Poisson 20%, Odds Movement 15%, Streaks 10%
    Ağırlıklar dinamik olarak normalize edilir.
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []

    # Team Performance (25% → dinamik)
    if team_perf.get('1x2'):
        sources.append(team_perf['1x2'])
        weights.append(0.25)
        source_names.append('team_perf')

    # Odds Analysis (25% → dinamik)
    if odds.get('available') and odds.get('normalized_percentages'):
        sources.append(odds['normalized_percentages'])
        weights.append(0.25)
        source_names.append('odds')

    # H2H Analysis (20% → dinamik)
    if h2h.get('1x2'):
        sources.append(h2h['1x2'])
        weights.append(0.20)
        source_names.append('h2h')

    # Correct Score (10% → dinamik)
    if correct_score.get('1x2'):
        sources.append(correct_score['1x2'])
        weights.append(0.10)
        source_names.append('correct_score')

    # EAGLE: Poisson Model (15%)
    if poisson and poisson.get('1x2'):
        sources.append(poisson['1x2'])
        weights.append(0.15)
        source_names.append('poisson')

    # EAGLE: Odds Movement (10%)
    if odds_movement and odds_movement.get('1x2'):
        sources.append(odds_movement['1x2'])
        weights.append(0.10)
        source_names.append('odds_movement')

    # EAGLE: Streak signals (5% bonus if strong signal)
    if streak_signals and streak_signals.get('ms'):
        ms_sig = streak_signals['ms']
        if ms_sig.get('strength', 0) >= 0.6:
            strength = ms_sig['strength']
            direction = ms_sig['direction']
            # Convert signal to percentages
            bonus = min(15, strength * 20)
            if direction == 'home':
                sources.append({'home': 50 + bonus, 'draw': 25, 'away': 25 - bonus})
            elif direction == 'away':
                sources.append({'home': 25 - bonus, 'draw': 25, 'away': 50 + bonus})
            weights.append(0.05)
            source_names.append('streaks')
    
    if not sources:
        logger.warning("1X2: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'home': weighted_average([s.get('home', 0) for s in sources], weights),
        'draw': weighted_average([s.get('draw', 0) for s in sources], weights),
        'away': weighted_average([s.get('away', 0) for s in sources], weights)
    }
    
    # Confidence hesapla
    confidence = calculate_confidence([s.get('home', 0) for s in sources])
    final['confidence'] = confidence
    
    return final


def calculate_goal_lines_final(correct_score, h2h, team_perf,
                                poisson=None, odds_movement=None, streak_signals=None):
    """
    Goal Lines için ağırlıklı final tahmin.
    Orijinal: Team Perf 40%, H2H 30%, Correct Score 30%
    Eagle: + Poisson 20%, Odds Movement 15%, Streaks 5%
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []

    # Team Performance (30% → dinamik)
    if team_perf.get('goal_lines'):
        sources.append(team_perf['goal_lines'])
        weights.append(0.30)
        source_names.append('team_perf')

    # H2H Analysis (20% → dinamik)
    if h2h.get('goal_lines'):
        sources.append(h2h['goal_lines'])
        weights.append(0.20)
        source_names.append('h2h')

    # Correct Score (15% → dinamik)
    if correct_score.get('goal_lines'):
        sources.append(correct_score['goal_lines'])
        weights.append(0.15)
        source_names.append('correct_score')

    # EAGLE: Poisson Model (20%) - çok güçlü gol tahmini kaynağı
    if poisson and poisson.get('goal_lines'):
        sources.append(poisson['goal_lines'])
        weights.append(0.20)
        source_names.append('poisson')

    # EAGLE: Odds Movement (15%) - piyasa beklentisi
    if odds_movement and odds_movement.get('goal_lines'):
        sources.append(odds_movement['goal_lines'])
        weights.append(0.15)
        source_names.append('odds_movement')

    # EAGLE: Streak signals (5% bonus)
    if streak_signals:
        over_sig = streak_signals.get('over25') or streak_signals.get('h2h_over25')
        if over_sig and over_sig.get('strength', 0) >= 0.7:
            strength = over_sig['strength']
            if over_sig['direction'] == 'over':
                sources.append({'over_2_5': 50 + strength * 20, 'under_2_5': 50 - strength * 20,
                                'over_3_5': 30 + strength * 10, 'under_3_5': 70 - strength * 10})
            else:
                sources.append({'over_2_5': 50 - strength * 20, 'under_2_5': 50 + strength * 20,
                                'over_3_5': 30 - strength * 10, 'under_3_5': 70 + strength * 10})
            weights.append(0.05)
            source_names.append('streaks')
    
    if not sources:
        logger.warning("Goal Lines: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'over_1_5': weighted_average([s.get('over_1_5', 0) for s in sources], weights),
        'over_2_5': weighted_average([s.get('over_2_5', 0) for s in sources], weights),
        'over_3_5': weighted_average([s.get('over_3_5', 0) for s in sources], weights),
        'under_1_5': weighted_average([s.get('under_1_5', 0) for s in sources], weights),
        'under_2_5': weighted_average([s.get('under_2_5', 0) for s in sources], weights),
        'under_3_5': weighted_average([s.get('under_3_5', 0) for s in sources], weights)
    }
    
    # Confidence hesapla (over_2_5 bazlı)
    confidence = calculate_confidence([s.get('over_2_5', 0) for s in sources])
    final['confidence'] = confidence
    
    return final


def calculate_btts_final(correct_score, h2h, team_perf,
                          poisson=None, streak_signals=None):
    """
    BTTS için ağırlıklı final tahmin.
    Orijinal: Team Perf 40%, H2H 35%, Correct Score 25%
    Eagle: + Poisson 15%, Streaks 5%
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []

    # Team Performance (30% → dinamik)
    if team_perf.get('btts'):
        sources.append(team_perf['btts'])
        weights.append(0.30)
        source_names.append('team_perf')

    # H2H Analysis (25% → dinamik)
    if h2h.get('btts'):
        sources.append(h2h['btts'])
        weights.append(0.25)
        source_names.append('h2h')

    # Correct Score (15% → dinamik)
    if correct_score.get('both_teams_to_score'):
        sources.append(correct_score['both_teams_to_score'])
        weights.append(0.15)
        source_names.append('correct_score')

    # EAGLE: Poisson Model (20%) - BTTS için çok güçlü
    if poisson and poisson.get('btts'):
        sources.append(poisson['btts'])
        weights.append(0.20)
        source_names.append('poisson')

    # EAGLE: Streak signals (5%)
    if streak_signals and streak_signals.get('btts'):
        btts_sig = streak_signals['btts']
        if btts_sig.get('strength', 0) >= 0.7:
            strength = btts_sig['strength']
            if btts_sig['direction'] == 'yes':
                sources.append({'yes': 50 + strength * 20, 'no': 50 - strength * 20})
            else:
                sources.append({'yes': 50 - strength * 20, 'no': 50 + strength * 20})
            weights.append(0.05)
            source_names.append('streaks')
    
    if not sources:
        logger.warning("BTTS: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'yes': weighted_average([s.get('yes', 0) for s in sources], weights),
        'no': weighted_average([s.get('no', 0) for s in sources], weights)
    }
    
    # Confidence hesapla
    confidence = calculate_confidence([s.get('yes', 0) for s in sources])
    final['confidence'] = confidence
    
    return final


def calculate_ht_1x2_final(h2h, team_perf,
                            poisson=None, odds_movement=None):
    """
    Half Time 1X2 için ağırlıklı final tahmin.
    Orijinal: Team Perf 55%, H2H 45%
    Eagle: + Poisson 15%, Odds Movement 10%
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []

    # Team Performance (40% → dinamik)
    if team_perf.get('ht_1x2'):
        sources.append(team_perf['ht_1x2'])
        weights.append(0.40)
        source_names.append('team_perf')

    # H2H Analysis (30% → dinamik)
    if h2h.get('ht_1x2'):
        sources.append(h2h['ht_1x2'])
        weights.append(0.30)
        source_names.append('h2h')

    # EAGLE: Poisson HT model (15%)
    if poisson and poisson.get('ht_1x2'):
        sources.append(poisson['ht_1x2'])
        weights.append(0.15)
        source_names.append('poisson')

    # EAGLE: Odds Movement HT (10%)
    if odds_movement and odds_movement.get('ht_1x2'):
        sources.append(odds_movement['ht_1x2'])
        weights.append(0.10)
        source_names.append('odds_movement')
    
    if not sources:
        logger.warning("HT 1X2: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'home': weighted_average([s.get('home', 0) for s in sources], weights),
        'draw': weighted_average([s.get('draw', 0) for s in sources], weights),
        'away': weighted_average([s.get('away', 0) for s in sources], weights)
    }
    
    # Confidence hesapla
    confidence = calculate_confidence([s.get('home', 0) for s in sources])
    final['confidence'] = confidence
    
    return final


def calculate_ht_goals_final(h2h, team_perf,
                              poisson=None, streak_signals=None):
    """
    Half Time Goals için ağırlıklı final tahmin.
    Orijinal: Team Perf 55%, H2H 45%
    Eagle: + Poisson 15%, Streaks 5%
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []

    # Team Performance (40% → dinamik)
    if team_perf.get('ht_goals'):
        sources.append(team_perf['ht_goals'])
        weights.append(0.40)
        source_names.append('team_perf')

    # H2H Analysis (30% → dinamik)
    if h2h.get('ht_goals'):
        sources.append(h2h['ht_goals'])
        weights.append(0.30)
        source_names.append('h2h')

    # EAGLE: Poisson HT goals (15%)
    if poisson and poisson.get('ht_goals'):
        sources.append(poisson['ht_goals'])
        weights.append(0.15)
        source_names.append('poisson')

    # EAGLE: Streak signal for HT goals (5%)
    if streak_signals and streak_signals.get('ht_over05'):
        ht_sig = streak_signals['ht_over05']
        if ht_sig.get('strength', 0) >= 0.7:
            strength = ht_sig['strength']
            sources.append({'over_0_5': 50 + strength * 25, 'under_0_5': 50 - strength * 25})
            weights.append(0.05)
            source_names.append('streaks')
    
    if not sources:
        logger.warning("HT Goals: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'over_0_5': weighted_average([s.get('ht_over_0_5', s.get('over_0_5', 0)) for s in sources], weights),
        'over_1_5': weighted_average([s.get('ht_over_1_5', s.get('over_1_5', 0)) for s in sources], weights),
        'under_0_5': weighted_average([s.get('ht_under_0_5', s.get('under_0_5', 0)) for s in sources], weights),
        'under_1_5': weighted_average([s.get('ht_under_1_5', s.get('under_1_5', 0)) for s in sources], weights)
    }
    
    # Confidence hesapla
    confidence = calculate_confidence([s.get('ht_over_0_5', s.get('over_0_5', 0)) for s in sources])
    final['confidence'] = confidence
    
    return final


def calculate_ht_btts_final(h2h):
    """
    Half Time BTTS - Sadece H2H'dan geliyor.
    """
    logger = logging.getLogger(__name__)
    
    if not h2h.get('ht_btts'):
        logger.warning("HT BTTS: No H2H data available")
        return {}
    
    final = {
        'yes': h2h['ht_btts'].get('yes', 0),
        'no': h2h['ht_btts'].get('no', 0),
        'confidence': 60.0  # Tek kaynak olduğu için sabit confidence
    }
    
    return final


def calculate_team_scoring_final(h2h, team_perf):
    """
    Team Scoring için ağırlıklı final tahmin.
    Ağırlıklar: Team Perf 55%, H2H 45%
    """
    logger = logging.getLogger(__name__)
    sources = []
    weights = []
    source_names = []
    
    # Team Performance (55%)
    if team_perf.get('team_scoring'):
        sources.append({
            'home': team_perf['team_scoring'].get('home_scores', 0),
            'away': team_perf['team_scoring'].get('away_scores', 0)
        })
        weights.append(0.55)
        source_names.append('team_perf')
    
    # H2H Analysis (45%)
    if h2h.get('team_scoring'):
        sources.append({
            'home': h2h['team_scoring'].get('home_team_scores', 0),
            'away': h2h['team_scoring'].get('away_team_scores', 0)
        })
        weights.append(0.45)
        source_names.append('h2h')
    
    if not sources:
        logger.warning("Team Scoring: No sources available for calculation")
        return {}
    
    # Ağırlıkları normalize et (dinamik yeniden dağıtım)
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    
    # Ağırlıklı ortalama hesapla
    final = {
        'home_team_scores': weighted_average([s.get('home', 0) for s in sources], weights),
        'away_team_scores': weighted_average([s.get('away', 0) for s in sources], weights)
    }
    
    # Confidence hesapla
    confidence = calculate_confidence([s.get('home', 0) for s in sources])
    final['confidence'] = confidence
    
    return final


def weighted_average(values, weights):
    """
    Ağırlıklı ortalama hesaplar.
    
    Args:
        values (list): Değerler
        weights (list): Ağırlıklar (toplamı 1 olmalı)
        
    Returns:
        float: Ağırlıklı ortalama
    """
    if not values or not weights or len(values) != len(weights):
        return 0.0
    
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return round(weighted_sum, 1)


def calculate_confidence(values):
    """
    Değerlerin birbirine yakınlığına göre confidence skoru hesaplar.
    
    Args:
        values (list): Yüzde değerleri
        
    Returns:
        float: Confidence skoru (0-100)
    """
    if not values or len(values) < 2:
        return 60.0  # Tek kaynak varsa sabit düşük confidence
    
    try:
        # Standart sapma hesapla
        stdev = statistics.stdev(values)
        
        # Standart sapmaya göre confidence hesapla
        # Düşük sapma = yüksek confidence
        if stdev <= 5:
            confidence = 95.0
        elif stdev <= 10:
            confidence = 85.0
        elif stdev <= 15:
            confidence = 75.0
        elif stdev <= 20:
            confidence = 65.0
        elif stdev <= 25:
            confidence = 55.0
        else:
            confidence = 45.0
        
        # Kaynak sayısına göre bonus
        source_count = len(values)
        if source_count >= 4:
            confidence = min(confidence + 5, 100)
        elif source_count == 3:
            confidence = min(confidence + 2, 100)
        
        return round(confidence, 1)
        
    except Exception:
        return 60.0

