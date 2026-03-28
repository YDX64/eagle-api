"""
Correct Score Analysis Module
Handles correct score odds analysis and derived predictions
"""

import logging


def analyze_correct_score_predictions(match_data):
    """
    Correct score odds'lardan gerçek olasılıkları hesaplar ve türetilmiş tahminler üretir.

    Args:
        match_data (dict): Maç verisi

    Returns:
        dict: Analiz sonuçları
    """
    try:
        # Correct score odds var mı kontrol et
        if 'correct_score_odds' not in match_data or not match_data['correct_score_odds']:
            return {"error": "Correct score odds data not available"}

        correct_score_data = match_data['correct_score_odds']

        if 'correct_score_odds' not in correct_score_data or not correct_score_data['correct_score_odds']:
            return {"error": "No correct score odds found"}

        companies = correct_score_data['correct_score_odds']

        # Geçerli company'leri bul (boş olmayan odds'ları olan)
        valid_companies = []
        for company in companies:
            if company.get('odds'):
                # En az bir odds değeri dolu mu kontrol et
                has_valid_odds = any(odds_value and odds_value.strip() for odds_value in company['odds'].values())
                if has_valid_odds:
                    valid_companies.append(company)

        if not valid_companies:
            return {"error": "No valid correct score odds found"}

        # İlk geçerli company'yi kullan (şimdilik)
        # TODO: Birden fazla company varsa ortalama al
        company_odds = valid_companies[0]['odds']

        # Skor olasılıklarını hesapla
        score_probabilities = {}
        total_probability = 0

        for score_key, odds_str in company_odds.items():
            if not odds_str or not odds_str.strip():
                continue

            try:
                # Decimal odds'ı float'a çevir
                odds = float(odds_str)

                # Gerçek olasılık = 1 / odds
                probability = 1.0 / odds
                score_probabilities[score_key] = probability
                total_probability += probability

            except (ValueError, ZeroDivisionError):
                continue

        if not score_probabilities:
            return {"error": "No valid score probabilities calculated"}

        # Marjı hesapla ve normalize et
        margin = total_probability - 1.0 if total_probability > 1.0 else 0.0
        normalized_probabilities = {}

        # Normalize edilmiş olasılıklar (marj çıkarılarak)
        for score, prob in score_probabilities.items():
            if total_probability > 0:
                normalized_probabilities[score] = (prob / total_probability) * 100  # Yüzde olarak
            else:
                normalized_probabilities[score] = 0.0

        # Türetülmüş tahminler hesapla
        derived_predictions = calculate_derived_predictions(normalized_probabilities)

        return {
            "correct_score_predictions": {
                "derived_predictions": derived_predictions
            }
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in analyze_correct_score_predictions: {str(e)}")
        return {"error": f"Analysis failed: {str(e)}"}


def calculate_derived_predictions(score_probabilities):
    """
    Skor olasılıklarından türetilmiş tahminleri hesaplar.

    Args:
        score_probabilities (dict): Normalize edilmiş skor olasılıkları (yüzde)

    Returns:
        dict: Türetülmüş tahminler
    """
    # 1X2 hesaplaması
    home_win_prob = 0
    draw_prob = 0
    away_win_prob = 0

    for score_key, probability in score_probabilities.items():
        if score_key == 'Other':
            # Other'ı 1X2'ye eşit dağıt (üç kategoriye)
            other_prob = probability / 3
            home_win_prob += other_prob
            draw_prob += other_prob
            away_win_prob += other_prob
            continue

        try:
            home_goals, away_goals = map(int, score_key.split(':'))

            if home_goals > away_goals:
                home_win_prob += probability
            elif home_goals == away_goals:
                draw_prob += probability
            else:  # home_goals < away_goals
                away_win_prob += probability

        except (ValueError, IndexError):
            # Geçersiz skor formatı - 1X2'ye eşit dağıt
            invalid_prob = probability / 3
            home_win_prob += invalid_prob
            draw_prob += invalid_prob
            away_win_prob += invalid_prob

    # BTTS hesaplaması (Both Teams To Score)
    btts_yes_prob = 0
    btts_no_prob = 0

    for score_key, probability in score_probabilities.items():
        if score_key == 'Other':
            # Other'ı BTTS'ye eşit dağıt
            other_prob = probability / 2
            btts_yes_prob += other_prob
            btts_no_prob += other_prob
            continue

        try:
            home_goals, away_goals = map(int, score_key.split(':'))

            if home_goals > 0 and away_goals > 0:
                btts_yes_prob += probability
            else:
                btts_no_prob += probability

        except (ValueError, IndexError):
            # Geçersiz skor formatı - BTTS'ye eşit dağıt
            invalid_prob = probability / 2
            btts_yes_prob += invalid_prob
            btts_no_prob += invalid_prob

    # Over/Under hesaplamaları - tüm skor olasılıklarını topla
    total_prob = sum(score_probabilities.values())

    over_1_5_prob = 0  # 2+ gol
    under_1_5_prob = 0  # 0-1 gol

    over_2_5_prob = 0  # 3+ gol
    under_2_5_prob = 0  # 0-2 gol

    over_3_5_prob = 0  # 4+ gol
    under_3_5_prob = 0  # 0-3 gol

    # Tüm skorları dolaşarak kategorilere ayır
    for score_key, probability in score_probabilities.items():
        if score_key == 'Other':
            # Other'ı tüm kategorilere dağıt (her kategoriye eşit olasılık)
            other_prob = probability / 6  # 3 over + 3 under kategorisi
            over_1_5_prob += other_prob
            under_1_5_prob += other_prob
            over_2_5_prob += other_prob
            under_2_5_prob += other_prob
            over_3_5_prob += other_prob
            under_3_5_prob += other_prob
            continue

        try:
            home_goals, away_goals = map(int, score_key.split(':'))
            total_goals = home_goals + away_goals

            if total_goals >= 2:
                over_1_5_prob += probability
            else:  # total_goals <= 1
                under_1_5_prob += probability

            if total_goals >= 3:
                over_2_5_prob += probability
            else:  # total_goals <= 2
                under_2_5_prob += probability

            if total_goals >= 4:
                over_3_5_prob += probability
            else:  # total_goals <= 3
                under_3_5_prob += probability

        except (ValueError, IndexError):
            # Geçersiz skor formatı - tüm kategorilere dağıt
            invalid_prob = probability / 6
            over_1_5_prob += invalid_prob
            under_1_5_prob += invalid_prob
            over_2_5_prob += invalid_prob
            under_2_5_prob += invalid_prob
            over_3_5_prob += invalid_prob
            under_3_5_prob += invalid_prob

    return {
        "1x2": {
            "home": round(home_win_prob, 1),
            "draw": round(draw_prob, 1),
            "away": round(away_win_prob, 1)
        },
        "both_teams_to_score": {
            "yes": round(btts_yes_prob, 1),
            "no": round(btts_no_prob, 1)
        },
        "goal_lines": {
            "over_1_5": round(over_1_5_prob, 1),
            "under_1_5": round(under_1_5_prob, 1),
            "over_2_5": round(over_2_5_prob, 1),
            "under_2_5": round(under_2_5_prob, 1),
            "over_3_5": round(over_3_5_prob, 1),
            "under_3_5": round(under_3_5_prob, 1)
        }
    }
