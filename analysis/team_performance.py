"""
Team Performance Analysis Module
Analyzes individual team performance from last matches
"""

import logging
import math


def analyze_team_performance(match_data):
    """
    Takımların son maç performanslarını analiz eder ve çaprazlar.

    Args:
        match_data (dict): Maç verisi

    Returns:
        dict: Kapsamlı takım performans analizi
    """
    try:
        # Match info'dan teams'i al
        if 'match_info' not in match_data:
            return {"error": "Match info not available"}

        home_team = match_data['match_info'].get('home_team_name', '')
        away_team = match_data['match_info'].get('away_team_name', '')

        if not home_team or not away_team:
            return {"error": "Team names not found"}

        # H2H data'dan team match history'lerini al
        if 'h2h_details' not in match_data:
            return {"error": "H2H details not available"}

        h2h_data = match_data['h2h_details']

        # Home team'in TÜM son maçları (ev + deplasman)
        home_team_all_matches = []
        if 'home_team_previous_matches' in h2h_data:
            home_team_all_matches.extend(h2h_data['home_team_previous_matches'])
        if 'away_team_previous_matches' in h2h_data:
            # away_team_previous_matches'te de home_team varsa ekle
            for match in h2h_data['away_team_previous_matches']:
                if (match.get('home_team') == home_team or
                    match.get('away_team') == home_team):
                    home_team_all_matches.append(match)

        # Away team'in TÜM son maçları (ev + deplasman)
        away_team_all_matches = []
        if 'away_team_previous_matches' in h2h_data:
            away_team_all_matches.extend(h2h_data['away_team_previous_matches'])
        if 'home_team_previous_matches' in h2h_data:
            # home_team_previous_matches'te de away_team varsa ekle
            for match in h2h_data['home_team_previous_matches']:
                if (match.get('home_team') == away_team or
                    match.get('away_team') == away_team):
                    away_team_all_matches.append(match)

        # Tarih sırasına göre sırala ve son 20 maçı al
        home_team_matches = sorted(home_team_all_matches, key=lambda x: x.get('date', ''), reverse=True)[:20]
        away_team_matches = sorted(away_team_all_matches, key=lambda x: x.get('date', ''), reverse=True)[:20]

        # Home team analizi
        home_team_analysis = analyze_single_team_performance(
            home_team_matches, home_team, is_home_team=True, opponent=away_team
        )

        # Away team analizi
        away_team_analysis = analyze_single_team_performance(
            away_team_matches, away_team, is_home_team=False, opponent=home_team
        )

        # Çaprazlama ve final tahminler
        # Önce team scoring'i hesapla
        home_team_scoring = home_team_analysis.get('harmonized_predictions', {}).get('scoring_probability', 75)
        away_team_scoring = away_team_analysis.get('harmonized_predictions', {}).get('scoring_probability', 75)

        final_predictions = crosstab_team_performances(home_team_analysis, away_team_analysis, home_team_scoring, away_team_scoring)

        return {
            "team_performance_analysis": {
                "crosstab_final_predictions": final_predictions
            }
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in analyze_team_performance: {str(e)}")
        return {"error": f"Team performance analysis failed: {str(e)}"}


def analyze_single_team_performance(matches, team_name, is_home_team, opponent):
    """
    Tek bir takımın performansını analiz eder.

    Args:
        matches (list): Takımın son maçları
        team_name (str): Takım adı
        is_home_team (bool): Bu takım maçta ev sahibi mi
        opponent (str): Rakip takım adı

    Returns:
        dict: Takım performans analizi
    """
    try:
        if not matches:
            return {"match_count": 0, "error": "No matches found"}

        # Temel istatistikler
        basic_stats = calculate_basic_team_stats(matches, team_name)

        # Pozisyon bazlı istatistikler (ev/dep ayrımı)
        try:
            position_stats = calculate_position_based_team_stats(matches, team_name)
        except Exception as e:
            position_stats = {}

        # Poisson bazlı tahminler
        poisson_stats = calculate_team_poisson_stats(basic_stats, position_stats, is_home_team)

        # Harmonize edilmiş tahminler (basic + poisson)
        harmonized_predictions = harmonize_team_predictions(basic_stats, poisson_stats, position_stats, is_home_team)

        result = {
            "team_name": team_name,
            "is_home_in_current_match": is_home_team,
            "opponent": opponent,
            "match_count": len(matches),
            "basic_stats": basic_stats,
            "position_stats": position_stats,
            "poisson_stats": poisson_stats,
            "harmonized_predictions": harmonized_predictions
        }
        return result

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Analysis failed for {team_name}: {str(e)}")
        return {"error": f"Analysis failed for {team_name}: {str(e)}"}


def calculate_basic_team_stats(matches, team_name):
    """
    Takımın temel istatistiklerini hesaplar (frekans bazlı).

    Args:
        matches (list): Maç listesi
        team_name (str): Takım adı

    Returns:
        dict: Temel istatistikler
    """
    total_matches = len(matches)
    if total_matches == 0:
        return {
            'match_count': 0,
            'win_percentage': 0.0,
            'draw_percentage': 0.0,
            'loss_percentage': 0.0,
            'scoring_percentage': 0.0,
            'clean_sheet_percentage': 0.0,
            'btts_yes_percentage': 0.0,
            'btts_no_percentage': 0.0,
            'over_1_5_percentage': 0.0,
            'over_2_5_percentage': 0.0,
            'over_3_5_percentage': 0.0,
            'under_1_5_percentage': 0.0,
            'under_2_5_percentage': 0.0,
            'under_3_5_percentage': 0.0,
            'ht_win_percentage': 0.0,
            'ht_draw_percentage': 0.0,
            'ht_loss_percentage': 0.0,
            'ht_over_0_5_percentage': 0.0,
            'ht_over_1_5_percentage': 0.0,
            'ht_under_0_5_percentage': 0.0,
            'ht_under_1_5_percentage': 0.0,
            'avg_goals_scored': 0.0,
            'avg_goals_conceded': 0.0
        }

    stats = {
        'wins': 0, 'draws': 0, 'losses': 0,
        'goals_scored': 0, 'goals_conceded': 0,
        'over_1_5_games': 0, 'under_1_5_games': 0,
        'over_2_5_games': 0, 'under_2_5_games': 0,
        'over_3_5_games': 0, 'under_3_5_games': 0,
        'btts_yes_games': 0, 'btts_no_games': 0,
        'ht_wins': 0, 'ht_draws': 0, 'ht_losses': 0,
        'ht_over_0_5_games': 0, 'ht_under_0_5_games': 0,
        'ht_over_1_5_games': 0, 'ht_under_1_5_games': 0,
        'scoring_games': 0, 'clean_sheet_games': 0
    }

    for match in matches:
        try:
            home_team = match.get('home_team', '')
            away_team = match.get('away_team', '')
            score = match.get('score', '0-0')
            ht_score = match.get('ht_score', '0-0')
            result = match.get('result', '')

            # Skorları parse et
            try:
                home_score, away_score = map(int, score.split('-'))
                ht_home, ht_away = map(int, ht_score.split('-'))
            except (ValueError, IndexError):
                continue

            # Score'dan doğru result hesapla (result field'ı güvenilir değil)
            if home_score > away_score:
                actual_result = 'W'  # home win
            elif home_score < away_score:
                actual_result = 'L'  # home loss (away win)
            else:
                actual_result = 'D'  # draw

            # Bu takımın perspektifinden istatistikleri hesapla
            if home_team == team_name:
                # Bu takım ev sahibi
                team_score = home_score
                opponent_score = away_score
                ht_team_score = ht_home
                ht_opponent_score = ht_away

                # Maç sonucu (ev sahibi açısından)
                if actual_result == 'W':
                    stats['wins'] += 1
                elif actual_result == 'D':
                    stats['draws'] += 1
                elif actual_result == 'L':
                    stats['losses'] += 1

                # HT sonucu
                if ht_home > ht_away:
                    stats['ht_wins'] += 1
                elif ht_home == ht_away:
                    stats['ht_draws'] += 1
                else:
                    stats['ht_losses'] += 1

            elif away_team == team_name:
                # Bu takım deplasman
                team_score = away_score
                opponent_score = home_score
                ht_team_score = ht_away
                ht_opponent_score = ht_home

                # Maç sonucu (deplasman açısından - ev sahibi sonucunu tersine çevir)
                if actual_result == 'W':
                    stats['losses'] += 1  # Ev sahibi kazandıysa deplasman kaybetti
                elif actual_result == 'D':
                    stats['draws'] += 1
                elif actual_result == 'L':
                    stats['wins'] += 1   # Ev sahibi kaybettiyse deplasman kazandı

                # HT sonucu
                if ht_away > ht_home:
                    stats['ht_wins'] += 1
                elif ht_away == ht_home:
                    stats['ht_draws'] += 1
                else:
                    stats['ht_losses'] += 1

            else:
                continue  # Bu maçta takım oynamadı

            # Gol istatistikleri
            stats['goals_scored'] += team_score
            stats['goals_conceded'] += opponent_score

            # Over/Under
            total_goals = team_score + opponent_score
            ht_total_goals = ht_team_score + ht_opponent_score

            if total_goals >= 2:
                stats['over_1_5_games'] += 1
            else:
                stats['under_1_5_games'] += 1

            if total_goals >= 3:
                stats['over_2_5_games'] += 1
            else:
                stats['under_2_5_games'] += 1

            if total_goals >= 4:
                stats['over_3_5_games'] += 1
            else:
                stats['under_3_5_games'] += 1

            # BTTS
            if team_score > 0 and opponent_score > 0:
                stats['btts_yes_games'] += 1
            else:
                stats['btts_no_games'] += 1

            # HT Over/Under
            if ht_total_goals >= 1:
                stats['ht_over_0_5_games'] += 1
            else:
                stats['ht_under_0_5_games'] += 1

            if ht_total_goals >= 2:  # Over 1.5 = 2 veya daha fazla gol
                stats['ht_over_1_5_games'] += 1
            else:
                stats['ht_under_1_5_games'] += 1

            # Gol atma/temiz kalma
            if team_score >= 1:
                stats['scoring_games'] += 1
            if opponent_score == 0:
                stats['clean_sheet_games'] += 1

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error processing match {match}: {str(e)}")
            continue

    # Yüzdelere çevir
    percentages = {'match_count': total_matches}
    if total_matches > 0:
        percentages.update({
            'win_percentage': round((stats['wins'] / total_matches) * 100, 1),
            'draw_percentage': round((stats['draws'] / total_matches) * 100, 1),
            'loss_percentage': round((stats['losses'] / total_matches) * 100, 1),
            'avg_goals_scored': round(stats['goals_scored'] / total_matches, 2),
            'avg_goals_conceded': round(stats['goals_conceded'] / total_matches, 2),
            'over_1_5_percentage': round((stats['over_1_5_games'] / total_matches) * 100, 1),
            'under_1_5_percentage': round((stats['under_1_5_games'] / total_matches) * 100, 1),
            'over_2_5_percentage': round((stats['over_2_5_games'] / total_matches) * 100, 1),
            'under_2_5_percentage': round((stats['under_2_5_games'] / total_matches) * 100, 1),
            'over_3_5_percentage': round((stats['over_3_5_games'] / total_matches) * 100, 1),
            'under_3_5_percentage': round((stats['under_3_5_games'] / total_matches) * 100, 1),
            'btts_yes_percentage': round((stats['btts_yes_games'] / total_matches) * 100, 1),
            'btts_no_percentage': round((stats['btts_no_games'] / total_matches) * 100, 1),
            'ht_win_percentage': round((stats['ht_wins'] / total_matches) * 100, 1),
            'ht_draw_percentage': round((stats['ht_draws'] / total_matches) * 100, 1),
            'ht_loss_percentage': round((stats['ht_losses'] / total_matches) * 100, 1),
            'ht_over_0_5_percentage': round((stats['ht_over_0_5_games'] / total_matches) * 100, 1),
            'ht_under_0_5_percentage': round((stats['ht_under_0_5_games'] / total_matches) * 100, 1),
            'ht_over_1_5_percentage': round((stats['ht_over_1_5_games'] / total_matches) * 100, 1),
            'ht_under_1_5_percentage': round((stats['ht_under_1_5_games'] / total_matches) * 100, 1),
            'scoring_percentage': round((stats['scoring_games'] / total_matches) * 100, 1),
            'clean_sheet_percentage': round((stats['clean_sheet_games'] / total_matches) * 100, 1)
        })

    return percentages


def calculate_position_based_team_stats(matches, team_name):
    """
    Takımın ev sahibi/deplasman bazlı istatistiklerini hesaplar.

    Args:
        matches (list): Maç listesi
        team_name (str): Takım adı

    Returns:
        dict: Pozisyon bazlı istatistikler
    """
    try:
        home_matches = []
        away_matches = []

        # Maçları ev/dep olarak ayır
        for match in matches:
            home_team = match.get('home_team', '')
            away_team = match.get('away_team', '')

            if home_team == team_name:
                home_matches.append(match)
            elif away_team == team_name:
                away_matches.append(match)

        # Pozisyon bazlı istatistikleri hesapla
        home_stats = calculate_basic_team_stats(home_matches, team_name) if home_matches else {}
        away_stats = calculate_basic_team_stats(away_matches, team_name) if away_matches else {}

        result = {
            'home_games': home_stats,
            'away_games': away_stats,
            'home_game_count': len(home_matches),
            'away_game_count': len(away_matches)
        }
        return result

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Position stats calculation failed for {team_name}: {str(e)}")
        return {}


def calculate_team_poisson_stats(basic_stats, position_stats, is_home_team):
    """
    Takım için Poisson bazlı istatistikler hesaplar.

    Args:
        basic_stats (dict): Temel istatistikler
        position_stats (dict): Pozisyon bazlı istatistikler
        is_home_team (bool): Bu takım maçta ev sahibi mi

    Returns:
        dict: Poisson bazlı tahminler
    """
    try:
        # Gol ortalamaları
        avg_goals_scored = basic_stats.get('avg_goals_scored', 1.5)
        avg_goals_conceded = basic_stats.get('avg_goals_conceded', 1.2)

        # Pozisyon bazlı ortalamalar (varsa kullan)
        if is_home_team and position_stats['home_games']:
            home_stats = position_stats['home_games']
            if home_stats.get('avg_goals_scored'):
                avg_goals_scored = home_stats['avg_goals_scored']
            if home_stats.get('avg_goals_conceded'):
                avg_goals_conceded = home_stats['avg_goals_conceded']
        elif not is_home_team and position_stats['away_games']:
            away_stats = position_stats['away_games']
            if away_stats.get('avg_goals_scored'):
                avg_goals_scored = away_stats['avg_goals_scored']
            if away_stats.get('avg_goals_conceded'):
                avg_goals_conceded = away_stats['avg_goals_conceded']

        # Poisson hesaplamaları
        def poisson_prob(lam, k):
            """Poisson olasılığı hesaplar"""
            if k == 0:
                return math.exp(-lam)
            result = math.exp(-lam)
            for i in range(1, k + 1):
                result *= lam / i
            return result

        # Gol atma/yeme olasılıkları
        scoring_prob = 1 - poisson_prob(avg_goals_scored, 0)  # P(gol atar)
        conceding_prob = 1 - poisson_prob(avg_goals_conceded, 0)  # P(gol yer)

        # Over/Under olasılıkları
        total_lambda = avg_goals_scored + avg_goals_conceded
        over_1_5_prob = 1.0 - poisson_prob(total_lambda, 0) - poisson_prob(total_lambda, 1)
        over_2_5_prob = 1.0 - sum(poisson_prob(total_lambda, k) for k in range(3))
        over_3_5_prob = 1.0 - sum(poisson_prob(total_lambda, k) for k in range(4))

        # BTTS olasılığı: P(home >= 1) * P(away >= 1)
        btts_prob = (1 - poisson_prob(avg_goals_scored, 0)) * (1 - poisson_prob(avg_goals_conceded, 0))

        return {
            'expected_goals_scored': round(avg_goals_scored, 2),
            'expected_goals_conceded': round(avg_goals_conceded, 2),
            'expected_total_goals': round(total_lambda, 2),
            'scoring_probability': round(scoring_prob * 100, 1),
            'conceding_probability': round(conceding_prob * 100, 1),
            'over_1_5_probability': round(over_1_5_prob * 100, 1),
            'over_2_5_probability': round(over_2_5_prob * 100, 1),
            'over_3_5_probability': round(over_3_5_prob * 100, 1),
            'under_1_5_probability': round((1 - over_1_5_prob) * 100, 1),
            'under_2_5_probability': round((1 - over_2_5_prob) * 100, 1),
            'under_3_5_probability': round((1 - over_3_5_prob) * 100, 1),
            'btts_probability': round(btts_prob * 100, 1),
            'btts_no_probability': round((1 - btts_prob) * 100, 1)
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Poisson calculation error: {str(e)}")
        return {'error': 'Poisson calculation failed'}


def harmonize_team_predictions(basic_stats, poisson_stats, position_stats, is_home_team):
    """
    Basic ve Poisson istatistiklerini harmonize eder.

    Args:
        basic_stats (dict): Frekans bazlı istatistikler
        poisson_stats (dict): Poisson bazlı istatistikler
        position_stats (dict): Pozisyon bazlı istatistikler
        is_home_team (bool): Bu takım maçta ev sahibi mi

    Returns:
        dict: Harmonize edilmiş tahminler
    """
    try:
        # Ağırlıklar: Basic %60, Poisson %40
        basic_weight = 0.6
        poisson_weight = 0.4

        harmonized = {}

        # 1X2 için harmonize (basic + poisson)
        basic_win = basic_stats.get('win_percentage', 0)
        basic_draw = basic_stats.get('draw_percentage', 0)
        basic_loss = basic_stats.get('loss_percentage', 0)

        # Poisson'dan 1x2 türetme
        expected_goals_scored = poisson_stats.get('expected_goals_scored', basic_stats.get('avg_goals_scored', 1.5))
        expected_goals_conceded = poisson_stats.get('expected_goals_conceded', basic_stats.get('avg_goals_conceded', 1.2))

        # Poisson convolution ile 1x2 hesabı
        poisson_win = 0
        poisson_draw = 0
        poisson_loss = 0

        # Poisson PMF
        def poisson_pmf(k, lam):
            return math.exp(-lam) * (lam ** k) / math.factorial(k) if k >= 0 else 0

        # Convolution (max 10 gol ile sınırlı, performans için)
        max_goals = 10
        for home_goals in range(max_goals + 1):
            for away_goals in range(max_goals + 1):
                p = poisson_pmf(home_goals, expected_goals_scored) * poisson_pmf(away_goals, expected_goals_conceded)
                if home_goals > away_goals:
                    poisson_win += p
                elif home_goals == away_goals:
                    poisson_draw += p
                else:
                    poisson_loss += p

        # Normalize (toplam 1 olsun)
        total_poisson = poisson_win + poisson_draw + poisson_loss
        if total_poisson > 0:
            poisson_win = (poisson_win / total_poisson) * 100
            poisson_draw = (poisson_draw / total_poisson) * 100
            poisson_loss = (poisson_loss / total_poisson) * 100

        # Basic ve Poisson'u harmonize et
        harmonized['1x2'] = {
            'win': round(basic_win * basic_weight + poisson_win * poisson_weight, 1),
            'draw': round(basic_draw * basic_weight + poisson_draw * poisson_weight, 1),
            'loss': round(basic_loss * basic_weight + poisson_loss * poisson_weight, 1)
        }

        # HT 1X2
        harmonized['ht_1x2'] = {
            'win': basic_stats.get('ht_win_percentage', 0),
            'draw': basic_stats.get('ht_draw_percentage', 0),
            'loss': basic_stats.get('ht_loss_percentage', 0)
        }

        # Over/Under için harmonize
        for market in ['over_1_5', 'under_1_5', 'over_2_5', 'under_2_5', 'over_3_5', 'under_3_5']:
            basic_val = basic_stats.get(f'{market}_percentage', 0)
            poisson_key = f'{market}_probability'
            poisson_val = poisson_stats.get(poisson_key, basic_val)

            harmonized[market] = round(basic_val * basic_weight + poisson_val * poisson_weight, 1)

        # BTTS için harmonize
        basic_btts_yes = basic_stats.get('btts_yes_percentage', 0)
        poisson_btts_yes = poisson_stats.get('btts_probability', basic_btts_yes)

        harmonized['btts_yes'] = round(basic_btts_yes * basic_weight + poisson_btts_yes * poisson_weight, 1)
        harmonized['btts_no'] = round(100 - harmonized['btts_yes'], 1)

        # Gol atma/yeme için harmonize
        basic_scoring = basic_stats.get('scoring_percentage', 0)
        poisson_scoring = poisson_stats.get('scoring_probability', basic_scoring)

        harmonized['scoring_probability'] = round(basic_scoring * basic_weight + poisson_scoring * poisson_weight, 1)
        harmonized['conceding_probability'] = round(poisson_stats.get('conceding_probability', 0), 1)

        # HT gol tahminleri için harmonize (sadece basic var)
        harmonized['ht_over_0_5'] = basic_stats.get('ht_over_0_5_percentage', 0)
        harmonized['ht_under_0_5'] = basic_stats.get('ht_under_0_5_percentage', 0)
        harmonized['ht_over_1_5'] = basic_stats.get('ht_over_1_5_percentage', 0)
        harmonized['ht_under_1_5'] = basic_stats.get('ht_under_1_5_percentage', 0)

        return harmonized

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Harmonize error: {str(e)}")
        return {'error': 'Harmonize failed'}


def crosstab_team_performances(home_team_analysis, away_team_analysis, home_team_scoring, away_team_scoring):
    """
    İki takımın performanslarını çaprazlar ve final tahminleri üretir.

    Args:
        home_team_analysis (dict): Ev sahibi takım analizi
        away_team_analysis (dict): Deplasman takım analizi

    Returns:
        dict: Çaprazlanmış final tahminler
    """
    try:
        home_predictions = home_team_analysis.get('harmonized_predictions', {})
        away_predictions = away_team_analysis.get('harmonized_predictions', {})

        if not home_predictions or not away_predictions:
            return {'error': 'Missing prediction data'}

        # 1X2 çaprazlaması
        # Home takım kazanma ihtimali vs Away takım kaybetme ihtimali
        home_win_prob = (home_predictions.get('1x2', {}).get('win', 0) +
                        away_predictions.get('1x2', {}).get('loss', 0)) / 2
        draw_prob = (home_predictions.get('1x2', {}).get('draw', 0) +
                    away_predictions.get('1x2', {}).get('draw', 0)) / 2
        away_win_prob = (home_predictions.get('1x2', {}).get('loss', 0) +
                        away_predictions.get('1x2', {}).get('win', 0)) / 2

        # Normalize et (toplam 100 olsun)
        total_1x2 = home_win_prob + draw_prob + away_win_prob
        if total_1x2 > 0:
            home_win_prob = round((home_win_prob / total_1x2) * 100, 1)
            draw_prob = round((draw_prob / total_1x2) * 100, 1)
            away_win_prob = round((away_win_prob / total_1x2) * 100, 1)

        # HT 1X2 çaprazlaması
        ht_home_win = (home_predictions.get('ht_1x2', {}).get('win', 0) +
                      away_predictions.get('ht_1x2', {}).get('loss', 0)) / 2
        ht_draw = (home_predictions.get('ht_1x2', {}).get('draw', 0) +
                  away_predictions.get('ht_1x2', {}).get('draw', 0)) / 2
        ht_away_win = (home_predictions.get('ht_1x2', {}).get('loss', 0) +
                      away_predictions.get('ht_1x2', {}).get('win', 0)) / 2

        # HT normalize
        ht_total = ht_home_win + ht_draw + ht_away_win
        if ht_total > 0:
            ht_home_win = round((ht_home_win / ht_total) * 100, 1)
            ht_draw = round((ht_draw / ht_total) * 100, 1)
            ht_away_win = round((ht_away_win / ht_total) * 100, 1)

        # Over/Under çaprazlaması
        def crosstab_market(home_key, away_key):
            home_val = home_predictions.get(home_key, 0)
            away_val = away_predictions.get(away_key, 0)
            return round((home_val + away_val) / 2, 1)

        # Final team scoring
        final_team_scoring = {
            'home_scores': round(home_team_scoring, 1),
            'away_scores': round(away_team_scoring, 1)
        }

        # BTTS çaprazlaması - Harmonized + Team Scoring bazlı
        home_btts = home_predictions.get('btts_yes', 0)
        away_btts = away_predictions.get('btts_yes', 0)
        harmonized_btts = (home_btts + away_btts) / 2

        # Team scoring bazlı BTTS (bağımsızlık varsayımı)
        team_scoring_btts = (home_team_scoring * away_team_scoring) / 100

        # İki yaklaşımı harmonize et (%50-%50)
        btts_yes = round((harmonized_btts + team_scoring_btts) / 2, 1)

        # Gol atma çaprazlaması
        home_scoring = home_predictions.get('scoring_probability', 0)
        away_scoring = away_predictions.get('scoring_probability', 0)

        return {
            '1x2': {
                'home': home_win_prob,
                'draw': draw_prob,
                'away': away_win_prob
            },
            'ht_1x2': {
                'home': ht_home_win,
                'draw': ht_draw,
                'away': ht_away_win
            },
            'goal_lines': {
                'over_1_5': crosstab_market('over_1_5', 'over_1_5'),
                'under_1_5': crosstab_market('under_1_5', 'under_1_5'),
                'over_2_5': crosstab_market('over_2_5', 'over_2_5'),
                'under_2_5': crosstab_market('under_2_5', 'under_2_5'),
                'over_3_5': crosstab_market('over_3_5', 'over_3_5'),
                'under_3_5': crosstab_market('under_3_5', 'under_3_5')
            },
            'ht_goals': {
                'over_0_5': crosstab_market('ht_over_0_5', 'ht_over_0_5'),
                'under_0_5': crosstab_market('ht_under_0_5', 'ht_under_0_5'),
                'over_1_5': crosstab_market('ht_over_1_5', 'ht_over_1_5'),
                'under_1_5': crosstab_market('ht_under_1_5', 'ht_under_1_5')
            },
            'btts': {
                'yes': btts_yes,
                'no': round(100 - btts_yes, 1)
            },
            'team_scoring': {
                'home_scores': round(home_scoring, 1),
                'away_scores': round(away_scoring, 1)
            }
        }

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Crosstab error: {str(e)}")
        return {'error': 'Crosstab failed'}
