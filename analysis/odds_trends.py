"""
Odds Trends Analysis Module
Analyzes betting odds movements and trends
"""

import logging


def analyze_odds_trends(odds_comp_data):
    """
    Odds hareketlerini analiz eder (Over/Under line movements).
    
    Args:
        odds_comp_data (dict): Odds comparison data from API
        
    Returns:
        dict: Odds trend analysis results
    """
    try:
        odds_comparison = odds_comp_data.get('odds_comparison', [])
        
        # First half odds'u al
        first_half_odds_data = odds_comp_data.get('first_half_odds', {})
        if isinstance(first_half_odds_data, dict) and 'first_half_odds' in first_half_odds_data:
            first_half_odds = first_half_odds_data['first_half_odds']
        else:
            first_half_odds = []
        
        if not odds_comparison and not first_half_odds:
            return {
                'odds_trend_analysis': {
                    'available': False,
                    'reason': 'no_odds_data'
                }
            }
        
        result = {
            'odds_trend_analysis': {
                'available': True
            }
        }
        
        # Full Time Over/Under Line Movement Analysis
        if odds_comparison:
            line_movement = analyze_over_under_line_movement(odds_comparison)
            result['odds_trend_analysis']['over_under_line_movement'] = line_movement
            
            # Asian Handicap Line Movement Analysis
            asian_movement = analyze_asian_handicap_line_movement(odds_comparison)
            result['odds_trend_analysis']['asian_handicap_line_movement'] = asian_movement
            
            # European Odds (1X2) Movement Analysis
            european_movement = analyze_european_odds_movement(odds_comparison)
            result['odds_trend_analysis']['european_odds_movement'] = european_movement
        
        # Half Time Over/Under Line Movement Analysis
        if first_half_odds:
            ht_line_movement = analyze_ht_over_under_line_movement(first_half_odds)
            result['odds_trend_analysis']['ht_over_under_line_movement'] = ht_line_movement
            
            # Half Time Asian Handicap Line Movement Analysis
            ht_asian_movement = analyze_ht_asian_handicap_line_movement(first_half_odds)
            result['odds_trend_analysis']['ht_asian_handicap_line_movement'] = ht_asian_movement
            
            # Half Time European Odds (1X2) Movement Analysis
            ht_european_movement = analyze_ht_european_odds_movement(first_half_odds)
            result['odds_trend_analysis']['ht_european_odds_movement'] = ht_european_movement
        
        return result
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in odds trends analysis: {str(e)}")
        return {
            'odds_trend_analysis': {
                'available': False,
                'error': str(e)
            }
        }


def analyze_over_under_line_movement(odds_comparison):
    """
    Over/Under line değerlerinin hareketini analiz eder.
    
    Args:
        odds_comparison (list): Company odds comparison list
        
    Returns:
        dict: Line movement statistics
    """
    logger = logging.getLogger(__name__)
    
    line_increased = 0
    line_decreased = 0
    line_unchanged = 0
    total_companies = 0
    
    # İlk geçerli line değerlerini sakla
    first_valid_first_line = None
    first_valid_pre_match_line = None
    
    for company in odds_comparison:
        try:
            over_under = company.get('over_under', {})
            
            # First odds ve pre-match odds'u al
            first_odds = over_under.get('first_odds', {})
            pre_match_odds = over_under.get('pre_match_odds', {})
            
            # Line değerlerini al
            first_line = first_odds.get('line')
            pre_match_line = pre_match_odds.get('line')
            
            # Boş kontrolü
            if first_line is None or pre_match_line is None:
                continue
            
            # String'den float'a çevir
            try:
                first_line = float(first_line)
                pre_match_line = float(pre_match_line)
            except (ValueError, TypeError):
                continue
            
            total_companies += 1
            
            # İlk geçerli değerleri sakla (sadece bir kez)
            if first_valid_first_line is None and first_valid_pre_match_line is None:
                first_valid_first_line = first_line
                first_valid_pre_match_line = pre_match_line
            
            # Karşılaştır
            if pre_match_line > first_line:
                line_increased += 1
            elif pre_match_line < first_line:
                line_decreased += 1
            else:
                line_unchanged += 1
                
        except Exception as e:
            logger.debug(f"Error processing company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if total_companies == 0:
        return {
            'available': False,
            'reason': 'no_valid_line_data'
        }
    
    result = {
        'total_companies': total_companies,
        'line_increased': line_increased,
        'line_decreased': line_decreased,
        'line_unchanged': line_unchanged
    }
    
    # İlk geçerli line değerlerini ekle
    if first_valid_first_line is not None:
        result['first_line'] = first_valid_first_line
    if first_valid_pre_match_line is not None:
        result['pre_match_line'] = first_valid_pre_match_line
    
    return result


def analyze_ht_over_under_line_movement(first_half_odds):
    """
    Half Time Over/Under line değerlerinin hareketini analiz eder.
    
    Args:
        first_half_odds (list): First half company odds comparison list
        
    Returns:
        dict: HT Line movement statistics
    """
    logger = logging.getLogger(__name__)
    
    line_increased = 0
    line_decreased = 0
    line_unchanged = 0
    total_companies = 0
    
    # İlk geçerli line değerlerini sakla
    first_valid_first_line = None
    first_valid_pre_match_line = None
    
    for company in first_half_odds:
        try:
            over_under = company.get('over_under', {})
            
            # First odds ve pre-match odds'u al
            first_odds = over_under.get('first_odds', {})
            pre_match_odds = over_under.get('pre_match_odds', {})
            
            # Line değerlerini al
            first_line = first_odds.get('line')
            pre_match_line = pre_match_odds.get('line')
            
            # Boş kontrolü
            if first_line is None or pre_match_line is None:
                continue
            
            # String'den float'a çevir
            try:
                first_line = float(first_line)
                pre_match_line = float(pre_match_line)
            except (ValueError, TypeError):
                continue
            
            total_companies += 1
            
            # İlk geçerli değerleri sakla (sadece bir kez)
            if first_valid_first_line is None and first_valid_pre_match_line is None:
                first_valid_first_line = first_line
                first_valid_pre_match_line = pre_match_line
            
            # Karşılaştır
            if pre_match_line > first_line:
                line_increased += 1
            elif pre_match_line < first_line:
                line_decreased += 1
            else:
                line_unchanged += 1
                
        except Exception as e:
            logger.debug(f"Error processing HT company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if total_companies == 0:
        return {
            'available': False,
            'reason': 'no_valid_ht_line_data'
        }
    
    result = {
        'total_companies': total_companies,
        'line_increased': line_increased,
        'line_decreased': line_decreased,
        'line_unchanged': line_unchanged
    }
    
    # İlk geçerli line değerlerini ekle
    if first_valid_first_line is not None:
        result['first_line'] = first_valid_first_line
    if first_valid_pre_match_line is not None:
        result['pre_match_line'] = first_valid_pre_match_line
    
    return result


def analyze_asian_handicap_line_movement(odds_comparison):
    """
    Asian Handicap line değerlerinin hareketini analiz eder.
    
    Args:
        odds_comparison (list): Company odds comparison list
        
    Returns:
        dict: Asian Handicap line movement statistics
    """
    logger = logging.getLogger(__name__)
    
    line_increased = 0
    line_decreased = 0
    line_unchanged = 0
    total_companies = 0
    
    # İlk geçerli line değerlerini sakla
    first_valid_first_line = None
    first_valid_pre_match_line = None
    
    for company in odds_comparison:
        try:
            asian_handicap = company.get('asian_handicap', {})
            
            # First odds ve pre-match odds'u al
            first_odds = asian_handicap.get('first_odds', {})
            pre_match_odds = asian_handicap.get('pre_match_odds', {})
            
            # Line değerlerini al
            first_line = first_odds.get('line')
            pre_match_line = pre_match_odds.get('line')
            
            # Boş kontrolü
            if first_line is None or pre_match_line is None:
                continue
            
            # String'den float'a çevir
            try:
                first_line = float(first_line)
                pre_match_line = float(pre_match_line)
            except (ValueError, TypeError):
                continue
            
            total_companies += 1
            
            # İlk geçerli değerleri sakla (sadece bir kez)
            if first_valid_first_line is None and first_valid_pre_match_line is None:
                first_valid_first_line = first_line
                first_valid_pre_match_line = pre_match_line
            
            # Karşılaştır
            if pre_match_line > first_line:
                line_increased += 1
            elif pre_match_line < first_line:
                line_decreased += 1
            else:
                line_unchanged += 1
                
        except Exception as e:
            logger.debug(f"Error processing Asian Handicap company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if total_companies == 0:
        return {
            'available': False,
            'reason': 'no_valid_asian_line_data'
        }
    
    result = {
        'total_companies': total_companies,
        'line_increased': line_increased,
        'line_decreased': line_decreased,
        'line_unchanged': line_unchanged
    }
    
    # İlk geçerli line değerlerini ekle
    if first_valid_first_line is not None:
        result['first_line'] = first_valid_first_line
    if first_valid_pre_match_line is not None:
        result['pre_match_line'] = first_valid_pre_match_line
    
    return result


def analyze_ht_asian_handicap_line_movement(first_half_odds):
    """
    Half Time Asian Handicap line değerlerinin hareketini analiz eder.
    
    Args:
        first_half_odds (list): First half company odds comparison list
        
    Returns:
        dict: HT Asian Handicap line movement statistics
    """
    logger = logging.getLogger(__name__)
    
    line_increased = 0
    line_decreased = 0
    line_unchanged = 0
    total_companies = 0
    
    # İlk geçerli line değerlerini sakla
    first_valid_first_line = None
    first_valid_pre_match_line = None
    
    for company in first_half_odds:
        try:
            asian_handicap = company.get('asian_handicap', {})
            
            # First odds ve pre-match odds'u al
            first_odds = asian_handicap.get('first_odds', {})
            pre_match_odds = asian_handicap.get('pre_match_odds', {})
            
            # Line değerlerini al
            first_line = first_odds.get('line')
            pre_match_line = pre_match_odds.get('line')
            
            # Boş kontrolü
            if first_line is None or pre_match_line is None:
                continue
            
            # String'den float'a çevir
            try:
                first_line = float(first_line)
                pre_match_line = float(pre_match_line)
            except (ValueError, TypeError):
                continue
            
            total_companies += 1
            
            # İlk geçerli değerleri sakla (sadece bir kez)
            if first_valid_first_line is None and first_valid_pre_match_line is None:
                first_valid_first_line = first_line
                first_valid_pre_match_line = pre_match_line
            
            # Karşılaştır
            if pre_match_line > first_line:
                line_increased += 1
            elif pre_match_line < first_line:
                line_decreased += 1
            else:
                line_unchanged += 1
                
        except Exception as e:
            logger.debug(f"Error processing HT Asian Handicap company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if total_companies == 0:
        return {
            'available': False,
            'reason': 'no_valid_ht_asian_line_data'
        }
    
    result = {
        'total_companies': total_companies,
        'line_increased': line_increased,
        'line_decreased': line_decreased,
        'line_unchanged': line_unchanged
    }
    
    # İlk geçerli line değerlerini ekle
    if first_valid_first_line is not None:
        result['first_line'] = first_valid_first_line
    if first_valid_pre_match_line is not None:
        result['pre_match_line'] = first_valid_pre_match_line
    
    return result


def analyze_european_odds_movement(odds_comparison):
    """
    European Odds (1X2) hareketlerini analiz eder ve yüzde değişimlerini hesaplar.
    
    Args:
        odds_comparison (list): Company odds comparison list
        
    Returns:
        dict: European odds movement with percentage changes
    """
    logger = logging.getLogger(__name__)
    
    # İlk geçerli odds'u bul
    first_valid_first_odds = None
    first_valid_pre_match_odds = None
    
    for company in odds_comparison:
        try:
            european_odds = company.get('european_odds', {})
            
            first_odds = european_odds.get('first_odds', {})
            pre_match_odds = european_odds.get('pre_match_odds', {})
            
            # Tüm değerlerin olup olmadığını kontrol et
            if not first_odds or not pre_match_odds:
                continue
            
            home_first = first_odds.get('home')
            draw_first = first_odds.get('draw')
            away_first = first_odds.get('away')
            
            home_pre = pre_match_odds.get('home')
            draw_pre = pre_match_odds.get('draw')
            away_pre = pre_match_odds.get('away')
            
            # Hepsi dolu mu kontrol et
            if not all([home_first, draw_first, away_first, home_pre, draw_pre, away_pre]):
                continue
            
            # Float'a çevir
            try:
                home_first = float(home_first)
                draw_first = float(draw_first)
                away_first = float(away_first)
                home_pre = float(home_pre)
                draw_pre = float(draw_pre)
                away_pre = float(away_pre)
            except (ValueError, TypeError):
                continue
            
            # İlk geçerli değerleri bulduk!
            first_valid_first_odds = {
                'home': home_first,
                'draw': draw_first,
                'away': away_first
            }
            first_valid_pre_match_odds = {
                'home': home_pre,
                'draw': draw_pre,
                'away': away_pre
            }
            break
            
        except Exception as e:
            logger.debug(f"Error processing European odds for company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if not first_valid_first_odds or not first_valid_pre_match_odds:
        return {
            'available': False,
            'reason': 'no_valid_european_odds'
        }
    
    # Yüzde değişimleri hesapla
    home_change = ((first_valid_pre_match_odds['home'] - first_valid_first_odds['home']) / first_valid_first_odds['home']) * 100
    draw_change = ((first_valid_pre_match_odds['draw'] - first_valid_first_odds['draw']) / first_valid_first_odds['draw']) * 100
    away_change = ((first_valid_pre_match_odds['away'] - first_valid_first_odds['away']) / first_valid_first_odds['away']) * 100
    
    result = {
        'first_odds': first_valid_first_odds,
        'pre_match_odds': first_valid_pre_match_odds,
        'changes': {
            'home': round(home_change, 1),
            'draw': round(draw_change, 1),
            'away': round(away_change, 1)
        }
    }
    
    return result


def analyze_ht_european_odds_movement(first_half_odds):
    """
    Half Time European Odds (1X2) hareketlerini analiz eder ve yüzde değişimlerini hesaplar.
    
    Args:
        first_half_odds (list): First half company odds comparison list
        
    Returns:
        dict: HT European odds movement with percentage changes
    """
    logger = logging.getLogger(__name__)
    
    # İlk geçerli odds'u bul
    first_valid_first_odds = None
    first_valid_pre_match_odds = None
    
    for company in first_half_odds:
        try:
            european_odds = company.get('european_odds', {})
            
            first_odds = european_odds.get('first_odds', {})
            pre_match_odds = european_odds.get('pre_match_odds', {})
            
            # Tüm değerlerin olup olmadığını kontrol et
            if not first_odds or not pre_match_odds:
                continue
            
            home_first = first_odds.get('home')
            draw_first = first_odds.get('draw')
            away_first = first_odds.get('away')
            
            home_pre = pre_match_odds.get('home')
            draw_pre = pre_match_odds.get('draw')
            away_pre = pre_match_odds.get('away')
            
            # Hepsi dolu mu kontrol et
            if not all([home_first, draw_first, away_first, home_pre, draw_pre, away_pre]):
                continue
            
            # Float'a çevir
            try:
                home_first = float(home_first)
                draw_first = float(draw_first)
                away_first = float(away_first)
                home_pre = float(home_pre)
                draw_pre = float(draw_pre)
                away_pre = float(away_pre)
            except (ValueError, TypeError):
                continue
            
            # İlk geçerli değerleri bulduk!
            first_valid_first_odds = {
                'home': home_first,
                'draw': draw_first,
                'away': away_first
            }
            first_valid_pre_match_odds = {
                'home': home_pre,
                'draw': draw_pre,
                'away': away_pre
            }
            break
            
        except Exception as e:
            logger.debug(f"Error processing HT European odds for company {company.get('company_id', 'unknown')}: {str(e)}")
            continue
    
    if not first_valid_first_odds or not first_valid_pre_match_odds:
        return {
            'available': False,
            'reason': 'no_valid_ht_european_odds'
        }
    
    # Yüzde değişimleri hesapla
    home_change = ((first_valid_pre_match_odds['home'] - first_valid_first_odds['home']) / first_valid_first_odds['home']) * 100
    draw_change = ((first_valid_pre_match_odds['draw'] - first_valid_first_odds['draw']) / first_valid_first_odds['draw']) * 100
    away_change = ((first_valid_pre_match_odds['away'] - first_valid_first_odds['away']) / first_valid_first_odds['away']) * 100
    
    result = {
        'first_odds': first_valid_first_odds,
        'pre_match_odds': first_valid_pre_match_odds,
        'changes': {
            'home': round(home_change, 1),
            'draw': round(draw_change, 1),
            'away': round(away_change, 1)
        }
    }
    
    return result

