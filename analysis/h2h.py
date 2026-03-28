"""
Head-to-Head Analysis Module
Analyzes historical matches between two teams
"""

import logging
import math


def analyze_h2h_details(match_data):
    """
    H2H (Head-to-Head) verilerini analiz eder ve takım istatistiklerini çıkarır.

    Args:
        match_data (dict): Maç verisi

    Returns:
        dict: H2H analiz sonuçları
    """
    try:
        # H2H details var mı kontrol et
        if 'h2h_details' not in match_data or not match_data['h2h_details']:
            return {"error": "H2H details not available"}

        h2h_data = match_data['h2h_details']

        # Head-to-head matches var mı kontrol et
        if 'head_to_head' not in h2h_data or not h2h_data['head_to_head']:
            return {"error": "No head-to-head matches found"}

        matches = h2h_data['head_to_head']

        # Match info'dan current teams'ı al
        if 'match_info' not in match_data:
            return {"error": "Match info not available"}

        current_home_team = match_data['match_info'].get('home_team_name', '')
        current_away_team = match_data['match_info'].get('away_team_name', '')

        if not current_home_team or not current_away_team:
            return {"error": "Team names not found in match info"}

        # En az 5 maç kontrolü - yeterli veri yoksa boş dön
        if len(matches) < 5:
            return {"h2h_analysis": {}}

        # H2H analizini gerçekleştir
        analysis = calculate_h2h_statistics(matches, current_home_team, current_away_team)

        return {
            "h2h_analysis": analysis
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in analyze_h2h_details: {str(e)}")
        return {"error": f"H2H analysis failed: {str(e)}"}


def calculate_h2h_statistics(matches, current_home_team, current_away_team):
    """
    Head-to-head maçlardan detaylı istatistikler hesaplar.

    Args:
        matches (list): H2H maç listesi
        current_home_team (str): Mevcut maçta ev sahibi takım
        current_away_team (str): Mevcut maçta deplasman takımı

    Returns:
        dict: Detaylı H2H istatistikleri
    """
    if not matches:
        return {"match_count": 0}

    total_matches = len(matches)

    # Temel sayaçlar
    stats = {
        'match_count': total_matches,
        'home_wins': 0,
        'away_wins': 0,
        'draws': 0,
        'home_goals_total': 0,  # Geçmiş ev sahibi gol toplamı
        'away_goals_total': 0,  # Geçmiş deplasman gol toplamı
        'home_team_goals_total': 0,  # current_home_team gol toplamı
        'away_team_goals_total': 0,  # current_away_team gol toplamı
        'ht_home_goals_total': 0,
        'ht_away_goals_total': 0,
        'ht_home_team_goals_total': 0,  # current_home_team HT gol toplamı
        'ht_away_team_goals_total': 0,  # current_away_team HT gol toplamı
        'over_2_5_count': 0,
        'under_2_5_count': 0,
        'over_1_5_count': 0,
        'under_1_5_count': 0,
        'over_3_5_count': 0,
        'under_3_5_count': 0,
        'btts_yes_count': 0,
        'btts_no_count': 0,
        'ht_home_wins': 0,
        'ht_draws': 0,
        'ht_away_wins': 0,
        'ht_over_0_5_count': 0,
        'ht_over_1_5_count': 0,
        'ht_btts_yes_count': 0,
        'ht_btts_no_count': 0,
        'home_team_scored_count': 0,
        'away_team_scored_count': 0
    }

    # Her maçı işle
    for match in matches:
        try:
            # Temel maç bilgilerini al
            home_team = match.get('home_team', '')
            away_team = match.get('away_team', '')
            result = match.get('result', '')  # W/L/D (home team açısından)
            score = match.get('score', '0-0')
            ht_score = match.get('ht_score', '0-0')

            # Skorları parse et
            try:
                home_score, away_score = map(int, score.split('-'))
                ht_home, ht_away = map(int, ht_score.split('-'))
            except (ValueError, IndexError):
                continue

            # Score'dan doğru result hesapla
            if home_score > away_score:
                actual_result = 'W'  # home win
            elif home_score < away_score:
                actual_result = 'L'  # home loss (away win)
            else:
                actual_result = 'D'  # draw

            total_goals = home_score + away_score
            ht_total_goals = ht_home + ht_away

            # Maç sonucunu kaydet
            if actual_result == 'W':
                stats['home_wins'] += 1
            elif actual_result == 'L':
                stats['away_wins'] += 1
            elif actual_result == 'D':
                stats['draws'] += 1

            # Gol toplamlarını kaydet (pozisyon bazlı ve takım bazlı)
            stats['home_goals_total'] += home_score  # Geçmiş ev sahibi
            stats['away_goals_total'] += away_score  # Geçmiş deplasman

            # HT gol toplamları (pozisyon bazlı)
            stats['ht_home_goals_total'] += ht_home
            stats['ht_away_goals_total'] += ht_away

            # Takım bazlı gol toplamları
            if home_team == current_home_team:
                # Bu maçta current_home_team ev sahibi
                stats['home_team_goals_total'] += home_score
                stats['away_team_goals_total'] += away_score
                stats['ht_home_team_goals_total'] += ht_home
                stats['ht_away_team_goals_total'] += ht_away
            elif away_team == current_home_team:
                # Bu maçta current_home_team deplasman
                stats['home_team_goals_total'] += away_score
                stats['away_team_goals_total'] += home_score
                stats['ht_home_team_goals_total'] += ht_away
                stats['ht_away_team_goals_total'] += ht_home

            # Over/Under sayıları
            if total_goals >= 3:
                stats['over_2_5_count'] += 1
            else:
                stats['under_2_5_count'] += 1

            if total_goals >= 2:
                stats['over_1_5_count'] += 1
            else:
                stats['under_1_5_count'] += 1

            if total_goals >= 4:
                stats['over_3_5_count'] += 1
            else:
                stats['under_3_5_count'] += 1

            # BTTS (Both Teams To Score)
            if home_score > 0 and away_score > 0:
                stats['btts_yes_count'] += 1
            else:
                stats['btts_no_count'] += 1

            # İlk yarı sonuçları
            if ht_home > ht_away:
                stats['ht_home_wins'] += 1
            elif ht_home == ht_away:
                stats['ht_draws'] += 1
            else:
                stats['ht_away_wins'] += 1

            if ht_total_goals >= 1:
                stats['ht_over_0_5_count'] += 1
            if ht_total_goals >= 2:
                stats['ht_over_1_5_count'] += 1

            # HT BTTS (Half-Time Both Teams To Score)
            if ht_home > 0 and ht_away > 0:
                stats['ht_btts_yes_count'] += 1
            else:
                stats['ht_btts_no_count'] += 1

            # Gol atma istatistikleri (hangi takımın açısından)
            if home_team == current_home_team:
                # Bu maçta current_home_team ev sahibi
                if home_score >= 1:
                    stats['home_team_scored_count'] += 1
                if away_score >= 1:
                    stats['away_team_scored_count'] += 1
            elif away_team == current_home_team:
                # Bu maçta current_home_team deplasman
                if away_score >= 1:
                    stats['home_team_scored_count'] += 1
                if home_score >= 1:
                    stats['away_team_scored_count'] += 1

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error processing match {match}: {str(e)}")
            continue

    # Yüzdelere çevir ve final hesaplamaları yap
    final_stats = calculate_final_percentages(stats, current_home_team, current_away_team)

    return final_stats


def calculate_final_percentages(stats, current_home_team, current_away_team):
    """
    Ham sayıları yüzdelere çevirir ve gelişmiş hesaplamalar yapar.

    Args:
        stats (dict): Ham istatistik sayıları
        current_home_team (str): Mevcut maçta ev sahibi
        current_away_team (str): Mevcut maçta deplasman

    Returns:
        dict: Final yüzdeler ve analizler
    """
    total_matches = stats['match_count']

    if total_matches == 0:
        return {"match_count": 0}

    # Temel yüzdeler
    basic_percentages = {
        'match_count': total_matches,
        '1x2': {
            'home': round((stats['home_wins'] / total_matches) * 100, 1),
            'draw': round((stats['draws'] / total_matches) * 100, 1),
            'away': round((stats['away_wins'] / total_matches) * 100, 1)
        },
        'ht_1x2': {
            'home': round((stats['ht_home_wins'] / total_matches) * 100, 1),
            'draw': round((stats['ht_draws'] / total_matches) * 100, 1),
            'away': round((stats['ht_away_wins'] / total_matches) * 100, 1)
        },
        'btts': {
            'yes': round((stats['btts_yes_count'] / total_matches) * 100, 1),
            'no': round((stats['btts_no_count'] / total_matches) * 100, 1)
        },
        'team_scoring': {
            'home_team_scores': round((stats['home_team_scored_count'] / total_matches) * 100, 1),
            'away_team_scores': round((stats['away_team_scored_count'] / total_matches) * 100, 1)
        }
    }

    # Gol ortalamaları
    avg_goals = {
        'home_avg_goals': round(stats['home_goals_total'] / total_matches, 2),  # Geçmiş ev sahibi ortalaması
        'away_avg_goals': round(stats['away_goals_total'] / total_matches, 2),  # Geçmiş deplasman ortalaması
        'total_avg_goals': round((stats['home_goals_total'] + stats['away_goals_total']) / total_matches, 2),
        'home_team_avg_goals': round(stats['home_team_goals_total'] / total_matches, 2),  # current_home_team ortalaması
        'away_team_avg_goals': round(stats['away_team_goals_total'] / total_matches, 2),  # current_away_team ortalaması
        'ht_home_avg_goals': round(stats['ht_home_goals_total'] / total_matches, 2),
        'ht_away_avg_goals': round(stats['ht_away_goals_total'] / total_matches, 2),
        'ht_total_avg_goals': round((stats['ht_home_goals_total'] + stats['ht_away_goals_total']) / total_matches, 2),
        'ht_home_team_avg_goals': round(stats['ht_home_team_goals_total'] / total_matches, 2),  # current_home_team HT ortalaması
        'ht_away_team_avg_goals': round(stats['ht_away_team_goals_total'] / total_matches, 2)   # current_away_team HT ortalaması
    }

    # Over/Under - Frekans bazlı
    frequency_over_under = {
        'over_1_5': round((stats['over_1_5_count'] / total_matches) * 100, 1),
        'under_1_5': round((stats['under_1_5_count'] / total_matches) * 100, 1),
        'over_2_5': round((stats['over_2_5_count'] / total_matches) * 100, 1),
        'under_2_5': round((stats['under_2_5_count'] / total_matches) * 100, 1),
        'over_3_5': round((stats['over_3_5_count'] / total_matches) * 100, 1),
        'under_3_5': round((stats['under_3_5_count'] / total_matches) * 100, 1)
    }

    # Over/Under - Şiddet bazlı (gol sayısı ağırlıklı)
    intensity_over_under = calculate_intensity_based_over_under(stats)

    # Poisson tabanlı tahminler (full-time ve half-time)
    # Takım bazlı gol ortalamalarını kullan
    team_based_avg_goals = {
        'home_avg_goals': avg_goals['home_team_avg_goals'],  # current_home_team ortalaması
        'away_avg_goals': avg_goals['away_team_avg_goals'],  # current_away_team ortalaması
        'total_avg_goals': avg_goals['total_avg_goals']
    }
    poisson_predictions = calculate_poisson_predictions(team_based_avg_goals)

    # HT için de takım bazlı
    ht_team_based_avg_goals = {
        'ht_home_avg_goals': avg_goals['ht_home_team_avg_goals'],
        'ht_away_avg_goals': avg_goals['ht_away_team_avg_goals'],
        'ht_total_avg_goals': avg_goals['ht_total_avg_goals']
    }
    ht_poisson_predictions = calculate_ht_poisson_predictions(ht_team_based_avg_goals)

    # Kombine edilmiş final yüzdeler - Poisson ağırlıklı
    final_over_under = combine_with_poisson(frequency_over_under, intensity_over_under, poisson_predictions)

    # HT gol yüzdeleri - frekans bazlı
    ht_frequency_goals = {
        'ht_over_0_5': round((stats['ht_over_0_5_count'] / total_matches) * 100, 1),
        'ht_under_0_5': round((total_matches - stats['ht_over_0_5_count']) / total_matches * 100, 1),
        'ht_over_1_5': round((stats['ht_over_1_5_count'] / total_matches) * 100, 1),
        'ht_under_1_5': round((total_matches - stats['ht_over_1_5_count']) / total_matches * 100, 1)
    }

    # HT BTTS yüzdeleri
    ht_btts = {
        'yes': round((stats['ht_btts_yes_count'] / total_matches) * 100, 1),
        'no': round((stats['ht_btts_no_count'] / total_matches) * 100, 1)
    }

    # Final predictions - Poisson ağırlıklı (H2H verisi varsa)
    if total_matches >= 5:  # Yeterli veri varsa Poisson ağırlıklı kullan
        final_1x2 = {
            'home': poisson_predictions.get('home_win_probability', basic_percentages['1x2']['home']),
            'draw': poisson_predictions.get('draw_probability', basic_percentages['1x2']['draw']),
            'away': poisson_predictions.get('away_win_probability', basic_percentages['1x2']['away'])
        }
        final_btts = {
            'yes': poisson_predictions.get('btts_probability', basic_percentages['btts']['yes']),
            'no': 100 - poisson_predictions.get('btts_probability', basic_percentages['btts']['yes'])
        }
        # HT 1X2 için de Poisson kullan (eğer HT Poisson hesaplaması varsa)
        final_ht_1x2 = {
            'home': ht_poisson_predictions.get('ht_home_win_probability', basic_percentages['ht_1x2']['home']),
            'draw': ht_poisson_predictions.get('ht_draw_probability', basic_percentages['ht_1x2']['draw']),
            'away': ht_poisson_predictions.get('ht_away_win_probability', basic_percentages['ht_1x2']['away'])
        }
        # HT gol yüzdeleri için Poisson ağırlıklı
        final_ht_goals = combine_ht_with_poisson(ht_frequency_goals, ht_poisson_predictions)
        # Team scoring için Poisson ağırlıklı
        final_team_scoring = combine_team_scoring_with_poisson(basic_percentages['team_scoring'], poisson_predictions, team_based_avg_goals)
    else:
        # Yeterli veri yoksa frequency kullan
        final_1x2 = basic_percentages['1x2']
        final_btts = basic_percentages['btts']
        final_ht_1x2 = basic_percentages['ht_1x2']
        final_ht_goals = ht_frequency_goals
        final_team_scoring = basic_percentages['team_scoring']

    return {
        'final_predictions': {
            '1x2': final_1x2,
            'ht_1x2': final_ht_1x2,
            'btts': final_btts,
            'ht_btts': ht_btts,
            'team_scoring': final_team_scoring,
            'goal_lines': final_over_under,
            'ht_goals': final_ht_goals
        }
    }


def calculate_intensity_based_over_under(stats):
    """
    Gol sayısı şiddetini baz alarak over/under yüzdeleri hesaplar.

    Args:
        stats (dict): İstatistikler

    Returns:
        dict: Şiddet bazlı over/under yüzdeleri
    """
    total_matches = stats['match_count']
    total_goals = stats['home_goals_total'] + stats['away_goals_total']

    if total_matches == 0:
        return {'over_2_5': 0, 'under_2_5': 0}

    avg_goals = total_goals / total_matches

    # Şiddet faktörü: ortalama gol sayısı ne kadar yüksekse over ihtimali o kadar artar
    intensity_over_2_5 = min(100, max(0, (avg_goals / 2.5) * 50))  # 2.5'in üstünde olma ihtimali
    intensity_under_2_5 = 100 - intensity_over_2_5

    # 1.5 için
    intensity_over_1_5 = min(100, max(0, (avg_goals / 1.5) * 40))
    intensity_under_1_5 = 100 - intensity_over_1_5

    # 3.5 için
    intensity_over_3_5 = min(100, max(0, (avg_goals / 3.5) * 30))
    intensity_under_3_5 = 100 - intensity_over_3_5

    return {
        'over_1_5': round(intensity_over_1_5, 1),
        'under_1_5': round(intensity_under_1_5, 1),
        'over_2_5': round(intensity_over_2_5, 1),
        'under_2_5': round(intensity_under_2_5, 1),
        'over_3_5': round(intensity_over_3_5, 1),
        'under_3_5': round(intensity_under_3_5, 1)
    }


def combine_frequency_intensity(frequency, intensity):
    """
    Frekans ve şiddet bazlı hesaplamaları birleştirir.

    Args:
        frequency (dict): Frekans bazlı yüzdeler
        intensity (dict): Şiddet bazlı yüzdeler

    Returns:
        dict: Kombine edilmiş final yüzdeler
    """
    # Ağırlıklar: %60 frekans, %40 şiddet
    freq_weight = 0.6
    intensity_weight = 0.4

    combined = {}
    for key in ['over_1_5', 'under_1_5', 'over_2_5', 'under_2_5', 'over_3_5', 'under_3_5']:
        if key in frequency and key in intensity:
            combined[key] = round(
                frequency[key] * freq_weight + intensity[key] * intensity_weight,
                1
            )

    return combined


def combine_with_poisson(frequency, intensity, poisson):
    """
    Frekans, şiddet ve Poisson bazlı hesaplamaları birleştirir.

    Args:
        frequency (dict): Frekans bazlı yüzdeler
        intensity (dict): Şiddet bazlı yüzdeler
        poisson (dict): Poisson bazlı yüzdeler

    Returns:
        dict: Poisson ağırlıklı final yüzdeler
    """
    # Ağırlıklar: Poisson %50, Frequency %30, Intensity %20
    poisson_weight = 0.5
    freq_weight = 0.3
    intensity_weight = 0.2

    combined = {}

    # Poisson anahtarları farklı, mapping yapalım
    poisson_mapping = {
        'over_1_5': 'over_1_5_probability',
        'under_1_5': 'under_1_5_probability',
        'over_2_5': 'over_2_5_probability',
        'under_2_5': 'under_2_5_probability',
        'over_3_5': 'over_3_5_probability',
        'under_3_5': 'under_3_5_probability'
    }

    for key in ['over_1_5', 'under_1_5', 'over_2_5', 'under_2_5', 'over_3_5', 'under_3_5']:
        freq_val = frequency.get(key, 0)
        intensity_val = intensity.get(key, 0)
        poisson_key = poisson_mapping.get(key)
        poisson_val = poisson.get(poisson_key, freq_val)  # Poisson yoksa frequency kullan

        combined[key] = round(
            poisson_val * poisson_weight +
            freq_val * freq_weight +
            intensity_val * intensity_weight,
            1
        )

    return combined


def calculate_ht_poisson_predictions(avg_goals):
    """
    Half-Time için Poisson dağılımı kullanarak tahminler yapar.

    Args:
        avg_goals (dict): Gol ortalamaları (HT dahil)

    Returns:
        dict: HT Poisson tabanlı tahminler
    """
    try:
        ht_home_avg = avg_goals['ht_home_avg_goals']
        ht_away_avg = avg_goals['ht_away_avg_goals']
        ht_total_avg = ht_home_avg + ht_away_avg

        # Poisson olasılık hesaplama fonksiyonu
        def poisson_prob(lam, k):
            """Poisson olasılığı hesaplar"""
            if k == 0:
                return math.exp(-lam)
            result = math.exp(-lam)
            for i in range(1, k + 1):
                result *= lam / i
            return result

        # HT Over/Under hesaplamaları
        ht_over_0_5_prob = 1.0 - poisson_prob(ht_total_avg, 0)
        ht_over_1_5_prob = 1.0 - sum(poisson_prob(ht_total_avg, k) for k in range(2))

        # HT BTTS hesabı: P(home >= 1) * P(away >= 1)
        ht_btts_prob = (1 - poisson_prob(ht_home_avg, 0)) * (1 - poisson_prob(ht_away_avg, 0))

        # HT 1X2 hesaplaması (Poisson convolution)
        ht_home_win_prob = 0
        ht_draw_prob = 0
        ht_away_win_prob = 0

        # Convolution: iki bağımsız Poisson'un toplamının olasılıkları
        max_goals = 8  # HT için daha düşük limit yeterli
        for h_goals in range(max_goals + 1):
            for a_goals in range(max_goals + 1):
                prob = poisson_prob(ht_home_avg, h_goals) * poisson_prob(ht_away_avg, a_goals)
                if h_goals > a_goals:
                    ht_home_win_prob += prob
                elif h_goals == a_goals:
                    ht_draw_prob += prob
                else:
                    ht_away_win_prob += prob

        return {
            'ht_home_goals_expectation': round(ht_home_avg, 2),
            'ht_away_goals_expectation': round(ht_away_avg, 2),
            'ht_total_goals_expectation': round(ht_total_avg, 2),
            'ht_over_0_5_probability': round(ht_over_0_5_prob * 100, 1),
            'ht_over_1_5_probability': round(ht_over_1_5_prob * 100, 1),
            'ht_under_0_5_probability': round((1 - ht_over_0_5_prob) * 100, 1),
            'ht_under_1_5_probability': round((1 - ht_over_1_5_prob) * 100, 1),
            'ht_btts_probability': round(ht_btts_prob * 100, 1),
            'ht_home_win_probability': round(ht_home_win_prob * 100, 1),
            'ht_draw_probability': round(ht_draw_prob * 100, 1),
            'ht_away_win_probability': round(ht_away_win_prob * 100, 1)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"HT Poisson calculation error: {str(e)}")
        return {
            'error': 'HT Poisson calculation failed'
        }


def combine_team_scoring_with_poisson(team_scoring_freq, poisson, team_based_avg_goals):
    """
    Team scoring frekans ve Poisson tabanlı hesaplamaları birleştirir.

    Args:
        team_scoring_freq (dict): Frequency bazlı team scoring yüzdeleri
        poisson (dict): Poisson bazlı hesaplamalar

    Returns:
        dict: Poisson ağırlıklı team scoring yüzdeleri
    """
    # Team scoring için ağırlıklar: Poisson %50, Frequency %50
    # (Team scoring daha çok geçmiş performans odaklı)
    poisson_weight = 0.5
    freq_weight = 0.5

    combined = {}

    # Poisson'dan gol atma olasılıkları
    home_scoring_prob = 100 - poisson.get('home_goals_expectation', 0) * 10  # Yaklaşık hesaplama
    away_scoring_prob = 100 - poisson.get('away_goals_expectation', 0) * 10

    # Daha doğru: 1 - P(0 gol) = gol atma olasılığı
    # P(0 gol) = e^(-λ)
    import math
    home_lambda = team_based_avg_goals['home_avg_goals']  # current_home_team ortalaması
    away_lambda = team_based_avg_goals['away_avg_goals']  # current_away_team ortalaması

    home_scoring_poisson = (1 - math.exp(-home_lambda)) * 100
    away_scoring_poisson = (1 - math.exp(-away_lambda)) * 100

    # Frekans değerleri
    home_scoring_freq = team_scoring_freq.get('home_team_scores', 75)
    away_scoring_freq = team_scoring_freq.get('away_team_scores', 75)

    # Birleştir
    combined['home_team_scores'] = round(
        home_scoring_poisson * poisson_weight +
        home_scoring_freq * freq_weight,
        1
    )
    combined['away_team_scores'] = round(
        away_scoring_poisson * poisson_weight +
        away_scoring_freq * freq_weight,
        1
    )

    return combined


def combine_ht_with_poisson(ht_frequency, ht_poisson):
    """
    HT frekans ve Poisson tabanlı hesaplamaları birleştirir.

    Args:
        ht_frequency (dict): HT frekans bazlı yüzdeler
        ht_poisson (dict): HT Poisson bazlı yüzdeler

    Returns:
        dict: HT için Poisson ağırlıklı final yüzdeler
    """
    # HT için ağırlıklar: Poisson %60, Frequency %40 (HT daha tahmin edilebilir)
    poisson_weight = 0.6
    freq_weight = 0.4

    combined = {}

    # HT gol tahminleri
    ht_mappings = {
        'ht_over_0_5': 'ht_over_0_5_probability',
        'ht_under_0_5': 'ht_under_0_5_probability',
        'ht_over_1_5': 'ht_over_1_5_probability',
        'ht_under_1_5': 'ht_under_1_5_probability'
    }

    for key in ['ht_over_0_5', 'ht_under_0_5', 'ht_over_1_5', 'ht_under_1_5']:
        freq_val = ht_frequency.get(key, 0)
        poisson_key = ht_mappings.get(key)
        poisson_val = ht_poisson.get(poisson_key, freq_val)  # Poisson yoksa frequency kullan

        combined[key] = round(
            poisson_val * poisson_weight +
            freq_val * freq_weight,
            1
        )

    return combined


def calculate_poisson_predictions(avg_goals):
    """
    Poisson dağılımı kullanarak gelecek maç tahminleri yapar.

    Args:
        avg_goals (dict): Gol ortalamaları

    Returns:
        dict: Poisson tabanlı tahminler
    """
    try:
        home_avg = avg_goals['home_avg_goals']
        away_avg = avg_goals['away_avg_goals']
        total_avg = home_avg + away_avg

        # Poisson olasılık hesaplama fonksiyonu
        def poisson_prob(lam, k):
            """Poisson olasılığı hesaplar"""
            if k == 0:
                return math.exp(-lam)
            result = math.exp(-lam)
            for i in range(1, k + 1):
                result *= lam / i
            return result

        # Over/Under hesaplamaları
        over_1_5_prob = 1.0 - poisson_prob(total_avg, 0) - poisson_prob(total_avg, 1)
        over_2_5_prob = 1.0 - sum(poisson_prob(total_avg, k) for k in range(3))
        over_3_5_prob = 1.0 - sum(poisson_prob(total_avg, k) for k in range(4))

        # BTTS hesabı: P(home >= 1) * P(away >= 1)
        btts_prob = (1 - poisson_prob(home_avg, 0)) * (1 - poisson_prob(away_avg, 0))

        # 1X2 hesaplaması (Poisson convolution)
        home_win_prob = 0
        draw_prob = 0
        away_win_prob = 0

        # Convolution: iki bağımsız Poisson'un toplamının olasılıkları
        max_goals = 10  # Yeterli precision için
        for h_goals in range(max_goals + 1):
            for a_goals in range(max_goals + 1):
                prob = poisson_prob(home_avg, h_goals) * poisson_prob(away_avg, a_goals)
                if h_goals > a_goals:
                    home_win_prob += prob
                elif h_goals == a_goals:
                    draw_prob += prob
                else:
                    away_win_prob += prob

        return {
            'home_goals_expectation': round(home_avg, 2),
            'away_goals_expectation': round(away_avg, 2),
            'total_goals_expectation': round(total_avg, 2),
            'over_1_5_probability': round(over_1_5_prob * 100, 1),
            'over_2_5_probability': round(over_2_5_prob * 100, 1),
            'over_3_5_probability': round(over_3_5_prob * 100, 1),
            'under_1_5_probability': round((1 - over_1_5_prob) * 100, 1),
            'under_2_5_probability': round((1 - over_2_5_prob) * 100, 1),
            'under_3_5_probability': round((1 - over_3_5_prob) * 100, 1),
            'btts_probability': round(btts_prob * 100, 1),
            'home_win_probability': round(home_win_prob * 100, 1),
            'draw_probability': round(draw_prob * 100, 1),
            'away_win_probability': round(away_win_prob * 100, 1)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Poisson calculation error: {str(e)}")
        return {
            'error': 'Poisson calculation failed',
            'home_goals_expectation': round(avg_goals.get('home_avg_goals', 0), 2),
            'away_goals_expectation': round(avg_goals.get('away_avg_goals', 0), 2)
        }
