"""
Final Predictions Module
Combines all analysis sources with weighted averages to produce final predictions
"""

import logging
import statistics

# ============================================================================
# Tunable Source Weights — AutoTuner can modify these via config_manager.
# Each dict maps source name → base weight (normalized dynamically).
# ============================================================================

MS_WEIGHTS = {'team_perf': 0.25, 'odds': 0.25, 'h2h': 0.20, 'correct_score': 0.10, 'poisson': 0.15, 'odds_movement': 0.10, 'streaks': 0.05}
GOAL_LINES_WEIGHTS = {'team_perf': 0.30, 'h2h': 0.20, 'correct_score': 0.15, 'poisson': 0.20, 'odds_movement': 0.15, 'streaks': 0.05}
BTTS_WEIGHTS = {'team_perf': 0.30, 'h2h': 0.25, 'correct_score': 0.15, 'poisson': 0.20, 'streaks': 0.05}
HT_1X2_WEIGHTS = {'team_perf': 0.40, 'h2h': 0.30, 'poisson': 0.15, 'odds_movement': 0.10}
HT_GOALS_WEIGHTS = {'team_perf': 0.40, 'h2h': 0.30, 'poisson': 0.15, 'streaks': 0.05}
DC_BLEND_WEIGHT = 0.05
FH_BLEND_WEIGHT = 0.15
HALF_BTTS_BLEND_WEIGHT = 0.30


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

        # 6 YENİ algoritmalar
        card_preds = analysis_data.get('card_predictions', {})
        cs_enhanced = analysis_data.get('correct_score_enhanced', {})
        handicap_preds = analysis_data.get('handicap_predictions', {})
        first_half_preds = analysis_data.get('first_half_predictions', {})
        second_half_preds = analysis_data.get('second_half_predictions', {})
        half_btts_preds = analysis_data.get('half_btts_predictions', {})
        corner_preds = analysis_data.get('corner_predictions', {})

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

        # ===== YENİ TAHMİN KATEGORİLERİ (6 yeni algoritma) =====

        # Card predictions (kart tahminleri)
        if card_preds:
            final_predictions['card'] = card_preds

        # Enhanced correct score (Dixon-Coles model)
        if cs_enhanced:
            final_predictions['correct_score_enhanced'] = cs_enhanced
            # Also update 1x2 with Dixon-Coles derived predictions if available
            cs_derived = cs_enhanced.get('derived_predictions', {})
            if cs_derived.get('1x2') and final_predictions.get('1x2'):
                dc_1x2 = cs_derived['1x2']
                existing_1x2 = final_predictions['1x2']
                for key in ['home', 'draw', 'away']:
                    if key in dc_1x2 and key in existing_1x2:
                        existing_1x2[key] = round(
                            existing_1x2[key] * (1 - DC_BLEND_WEIGHT) + dc_1x2[key] * DC_BLEND_WEIGHT, 1
                        )

        # Handicap predictions
        if handicap_preds:
            final_predictions['handicap'] = handicap_preds

        # First half detailed predictions
        if first_half_preds:
            final_predictions['first_half'] = first_half_preds
            # Update HT predictions with first_half data
            fh_1x2 = first_half_preds.get('ht_1x2', {})
            fh_ou = first_half_preds.get('ht_over_under', {})
            if fh_1x2 and final_predictions.get('ht_1x2'):
                for key in ['home', 'draw', 'away']:
                    if key in fh_1x2 and key in final_predictions['ht_1x2']:
                        final_predictions['ht_1x2'][key] = round(
                            final_predictions['ht_1x2'][key] * (1 - FH_BLEND_WEIGHT) + fh_1x2[key] * FH_BLEND_WEIGHT, 1
                        )
            if fh_ou and final_predictions.get('ht_goals'):
                for key in ['over_0_5', 'under_0_5']:
                    if key in fh_ou and key in final_predictions['ht_goals']:
                        final_predictions['ht_goals'][key] = round(
                            final_predictions['ht_goals'][key] * (1 - FH_BLEND_WEIGHT) + fh_ou[key] * FH_BLEND_WEIGHT, 1
                        )

        # Second half predictions
        if second_half_preds:
            final_predictions['second_half'] = second_half_preds

        # Half-based BTTS
        if half_btts_preds:
            final_predictions['half_btts'] = half_btts_preds

        # Corner predictions
        if corner_preds:
            final_predictions['corner_analysis'] = corner_preds
            # Update HT BTTS with half_btts data
            fh_btts = half_btts_preds.get('first_half_btts', {})
            if fh_btts and final_predictions.get('ht_btts'):
                for key in ['yes', 'no']:
                    if key in fh_btts and key in final_predictions['ht_btts']:
                        final_predictions['ht_btts'][key] = round(
                            final_predictions['ht_btts'][key] * (1 - HALF_BTTS_BLEND_WEIGHT) + fh_btts[key] * HALF_BTTS_BLEND_WEIGHT, 1
                        )

        # Kaynak durumlarını metadata olarak ekle (7 kaynak)
        final_predictions['_eagle_sources'] = {
            'poisson': bool(poisson),
            'odds_movement': bool(odds_movement),
            'streaks': bool(streaks),
            'h2h': bool(h2h),
            'form': bool(team_perf),
            'league_stats': bool(h2h),  # H2H data includes league context
            'market_consensus': bool(odds),
            'card_predictions': bool(card_preds),
            'correct_score_enhanced': bool(cs_enhanced),
            'handicap_predictions': bool(handicap_preds),
            'first_half_predictions': bool(first_half_preds),
            'second_half_predictions': bool(second_half_preds),
            'half_btts_predictions': bool(half_btts_preds),
            'corner_predictions': bool(corner_preds),
            'total_sources': sum(1 for x in [
                poisson, odds_movement, streaks, h2h, team_perf,
                h2h,  # league_stats proxy
                odds,  # market_consensus
                card_preds, cs_enhanced, handicap_preds,
                first_half_preds, second_half_preds, half_btts_preds, corner_preds,
            ] if x),
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

    # Team Performance
    if team_perf.get('1x2'):
        sources.append(team_perf['1x2'])
        weights.append(MS_WEIGHTS['team_perf'])
        source_names.append('team_perf')

    # Odds Analysis
    if odds.get('available') and odds.get('normalized_percentages'):
        sources.append(odds['normalized_percentages'])
        weights.append(MS_WEIGHTS['odds'])
        source_names.append('odds')

    # H2H Analysis
    if h2h.get('1x2'):
        sources.append(h2h['1x2'])
        weights.append(MS_WEIGHTS['h2h'])
        source_names.append('h2h')

    # Correct Score
    if correct_score.get('1x2'):
        sources.append(correct_score['1x2'])
        weights.append(MS_WEIGHTS['correct_score'])
        source_names.append('correct_score')

    # Poisson Model
    if poisson and poisson.get('1x2'):
        sources.append(poisson['1x2'])
        weights.append(MS_WEIGHTS['poisson'])
        source_names.append('poisson')

    # Odds Movement
    if odds_movement and odds_movement.get('1x2'):
        sources.append(odds_movement['1x2'])
        weights.append(MS_WEIGHTS['odds_movement'])
        source_names.append('odds_movement')

    # Streak signals
    if streak_signals and streak_signals.get('ms'):
        ms_sig = streak_signals['ms']
        if ms_sig.get('strength', 0) >= 0.6:
            strength = ms_sig['strength']
            direction = ms_sig['direction']
            bonus = min(15, strength * 20)
            if direction == 'home':
                sources.append({'home': 50 + bonus, 'draw': 25, 'away': 25 - bonus})
            elif direction == 'away':
                sources.append({'home': 25 - bonus, 'draw': 25, 'away': 50 + bonus})
            weights.append(MS_WEIGHTS['streaks'])
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

    # Team Performance
    if team_perf.get('goal_lines'):
        sources.append(team_perf['goal_lines'])
        weights.append(GOAL_LINES_WEIGHTS['team_perf'])
        source_names.append('team_perf')

    # H2H Analysis
    if h2h.get('goal_lines'):
        sources.append(h2h['goal_lines'])
        weights.append(GOAL_LINES_WEIGHTS['h2h'])
        source_names.append('h2h')

    # Correct Score
    if correct_score.get('goal_lines'):
        sources.append(correct_score['goal_lines'])
        weights.append(GOAL_LINES_WEIGHTS['correct_score'])
        source_names.append('correct_score')

    # Poisson Model
    if poisson and poisson.get('goal_lines'):
        sources.append(poisson['goal_lines'])
        weights.append(GOAL_LINES_WEIGHTS['poisson'])
        source_names.append('poisson')

    # Odds Movement
    if odds_movement and odds_movement.get('goal_lines'):
        sources.append(odds_movement['goal_lines'])
        weights.append(GOAL_LINES_WEIGHTS['odds_movement'])
        source_names.append('odds_movement')

    # Streak signals
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
            weights.append(GOAL_LINES_WEIGHTS['streaks'])
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

    # Team Performance
    if team_perf.get('btts'):
        sources.append(team_perf['btts'])
        weights.append(BTTS_WEIGHTS['team_perf'])
        source_names.append('team_perf')

    # H2H Analysis
    if h2h.get('btts'):
        sources.append(h2h['btts'])
        weights.append(BTTS_WEIGHTS['h2h'])
        source_names.append('h2h')

    # Correct Score
    if correct_score.get('both_teams_to_score'):
        sources.append(correct_score['both_teams_to_score'])
        weights.append(BTTS_WEIGHTS['correct_score'])
        source_names.append('correct_score')

    # Poisson Model
    if poisson and poisson.get('btts'):
        sources.append(poisson['btts'])
        weights.append(BTTS_WEIGHTS['poisson'])
        source_names.append('poisson')

    # Streak signals
    if streak_signals and streak_signals.get('btts'):
        btts_sig = streak_signals['btts']
        if btts_sig.get('strength', 0) >= 0.7:
            strength = btts_sig['strength']
            if btts_sig['direction'] == 'yes':
                sources.append({'yes': 50 + strength * 20, 'no': 50 - strength * 20})
            else:
                sources.append({'yes': 50 - strength * 20, 'no': 50 + strength * 20})
            weights.append(BTTS_WEIGHTS['streaks'])
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

    # Team Performance
    if team_perf.get('ht_1x2'):
        sources.append(team_perf['ht_1x2'])
        weights.append(HT_1X2_WEIGHTS['team_perf'])
        source_names.append('team_perf')

    # H2H Analysis
    if h2h.get('ht_1x2'):
        sources.append(h2h['ht_1x2'])
        weights.append(HT_1X2_WEIGHTS['h2h'])
        source_names.append('h2h')

    # Poisson HT model
    if poisson and poisson.get('ht_1x2'):
        sources.append(poisson['ht_1x2'])
        weights.append(HT_1X2_WEIGHTS['poisson'])
        source_names.append('poisson')

    # Odds Movement HT
    if odds_movement and odds_movement.get('ht_1x2'):
        sources.append(odds_movement['ht_1x2'])
        weights.append(HT_1X2_WEIGHTS['odds_movement'])
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

    # Team Performance
    if team_perf.get('ht_goals'):
        sources.append(team_perf['ht_goals'])
        weights.append(HT_GOALS_WEIGHTS['team_perf'])
        source_names.append('team_perf')

    # H2H Analysis
    if h2h.get('ht_goals'):
        sources.append(h2h['ht_goals'])
        weights.append(HT_GOALS_WEIGHTS['h2h'])
        source_names.append('h2h')

    # Poisson HT goals
    if poisson and poisson.get('ht_goals'):
        sources.append(poisson['ht_goals'])
        weights.append(HT_GOALS_WEIGHTS['poisson'])
        source_names.append('poisson')

    # Streak signal for HT goals
    if streak_signals and streak_signals.get('ht_over05'):
        ht_sig = streak_signals['ht_over05']
        if ht_sig.get('strength', 0) >= 0.7:
            strength = ht_sig['strength']
            sources.append({'over_0_5': 50 + strength * 25, 'under_0_5': 50 - strength * 25})
            weights.append(HT_GOALS_WEIGHTS['streaks'])
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

