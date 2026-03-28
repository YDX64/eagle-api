"""
Spotlight Statistics Module

Son 10/20 maç ve H2H geçmişinden istatistiksel olarak dikkat çekici
bulguları safkan veri olarak üretir. Cümle değil, yapısal veri döndürür.

Statlar:
  - over_1_5 / over_2_5 / over_3_5 / under_1_5 / under_2_5
  - btts (kg var / her iki takım gol attı)
  - İlk yarı: ht_over_0_5 / ht_over_1_5 / ht_btts
  - Takım bazlı: team_scored, team_conceded, team_multi_goal, clean_sheet
  - Ardışık seriler (streak): over_2_5, btts, team_scoring, team_conceding
  - Oran hareketi (odds drop): favori %13+, outsider %35+

Pencereler:
  - all_games → last_10, last_20
  - home_games (ev sahibi takımın sadece iç saha maçları) → last_10
  - away_games (deplasman takımının sadece dış saha maçları) → last_10
  - h2h → last_5, last_10

Highlight eşikleri (highlights dizisine girer):
  - Oran bazlı: >= %70 veya <= %30
  - over_3_5: >= %60
  - team_multi_goal, clean_sheet, team_conceded: >= %60 / %90
  - Streak: >= 3 ardışık maç
  - Oran düşüşü: favori >= %13, outsider >= %35
"""

import logging

logger = logging.getLogger(__name__)

# ── Highlight eşikleri ──────────────────────────────────────────────────────
_THRESH_70 = 0.70   # Genel yüksek frekans (over_2_5, btts, ...)
_THRESH_60 = 0.60   # Orta frekans (over_3_5, multi_goal, clean_sheet)
_THRESH_90 = 0.90   # Çok yüksek frekans (sürekli gol atan/yiyen takım)
_THRESH_30 = 0.30   # Düşük frekans (under_2_5 tersi de dikkat çeker)
_MIN_STREAK = 3     # Minimum ardışık maç sayısı
_FAV_DROP   = 13.0  # Favorinin oran düşüş eşiği (%)
_OUT_DROP   = 35.0  # Outsider'ın oran düşüş eşiği (%)


# ── Yardımcı: skor parse ─────────────────────────────────────────────────────

def _parse_score(raw: str):
    """
    '2-1' → (2, 1)
    Geçersiz ya da boş değerlerde None döner.
    """
    try:
        if not raw:
            return None
        raw = str(raw).strip()
        if '-' not in raw:
            return None
        parts = raw.split('-')
        if len(parts) != 2:
            return None
        h, a = parts[0].strip(), parts[1].strip()
        if not h.isdigit() or not a.isdigit():
            return None
        return int(h), int(a)
    except Exception:
        return None


# ── Çekirdek: bir maç listesini analiz et ───────────────────────────────────

def _compute_window_stats(matches: list, team_name: str = None) -> dict:
    """
    Maç listesinden istatistiksel pencere verisi üretir.

    Args:
        matches:   Ham maç listesi (en yeni → en eski sıralı olmalı).
        team_name: Belirtilirse takım-spesifik gol/temiz kale istatistikleri eklenir.

    Returns:
        Yapısal istatistik dict'i.
    """
    valid = 0
    total_goals_sum = 0

    # Genel gol istatistikleri
    over_1_5 = over_2_5 = over_3_5 = 0
    under_1_5 = under_2_5 = 0
    btts = 0

    # İlk yarı istatistikleri
    ht_over_0_5 = ht_over_1_5 = ht_btts = 0

    # Takım-spesifik
    t_scored = t_conceded = t_multi = t_clean = t_scored_ht = 0

    # Ardışık seriler (en yeni maçtan başlar)
    streak_o25 = streak_btts = streak_ts = streak_tc = 0
    # Her biri "i'inci maça kadar kesintisiz devam etti mi" olarak izlenir
    _s_o25 = _s_btts = _s_ts = _s_tc = True   # hâlâ devam ediyor mu

    for i, m in enumerate(matches):
        score = _parse_score(m.get('score', ''))
        if score is None:
            continue

        valid += 1
        hg, ag = score
        total = hg + ag
        total_goals_sum += total

        is_o15 = total > 1
        is_o25 = total > 2
        is_o35 = total > 3
        is_btts = hg > 0 and ag > 0

        if is_o15: over_1_5 += 1
        else:       under_1_5 += 1
        if is_o25:  over_2_5 += 1
        else:        under_2_5 += 1
        if is_o35:  over_3_5 += 1
        if is_btts: btts += 1

        # İlk yarı
        ht = _parse_score(m.get('ht_score', ''))
        if ht:
            ht_h, ht_a = ht
            ht_total = ht_h + ht_a
            if ht_total > 0:  ht_over_0_5 += 1
            if ht_total > 1:  ht_over_1_5 += 1
            if ht_h > 0 and ht_a > 0: ht_btts += 1

        # Takım-spesifik hesaplama
        if team_name:
            if m.get('home_team') == team_name:
                tg, og = hg, ag
                ht_tg = ht[0] if ht else None
            elif m.get('away_team') == team_name:
                tg, og = ag, hg
                ht_tg = ht[1] if ht else None
            else:
                tg = og = ht_tg = None

            if tg is not None:
                if tg > 0:  t_scored += 1
                if og > 0:  t_conceded += 1
                if tg >= 2: t_multi += 1
                if og == 0: t_clean += 1
                if ht_tg is not None and ht_tg > 0: t_scored_ht += 1

                # Seriler: sadece listenin başından kesintisiz olanlar sayılır
                if _s_o25:
                    if is_o25: streak_o25 += 1
                    else:       _s_o25 = False
                if _s_btts:
                    if is_btts: streak_btts += 1
                    else:        _s_btts = False
                if _s_ts:
                    if tg > 0: streak_ts += 1
                    else:       _s_ts = False
                if _s_tc:
                    if og > 0: streak_tc += 1
                    else:       _s_tc = False
        else:
            # Takım belirtilmemişse genel seriler
            if _s_o25:
                if is_o25: streak_o25 += 1
                else:       _s_o25 = False
            if _s_btts:
                if is_btts: streak_btts += 1
                else:        _s_btts = False

    if valid == 0:
        return {'match_count': 0}

    result = {
        'match_count':      valid,
        'over_1_5_count':   over_1_5,
        'over_2_5_count':   over_2_5,
        'over_3_5_count':   over_3_5,
        'under_1_5_count':  under_1_5,
        'under_2_5_count':  under_2_5,
        'btts_count':       btts,
        'ht_over_0_5_count': ht_over_0_5,
        'ht_over_1_5_count': ht_over_1_5,
        'ht_btts_count':    ht_btts,
        'over_2_5_streak':  streak_o25,
        'btts_streak':      streak_btts,
        'avg_total_goals':  round(total_goals_sum / valid, 2),
    }

    if team_name:
        result.update({
            'team_scored_count':    t_scored,
            'team_conceded_count':  t_conceded,
            'team_multi_goal_count': t_multi,
            'team_clean_sheet_count': t_clean,
            'team_scored_ht_count': t_scored_ht,
            'team_scoring_streak':  streak_ts,
            'team_conceding_streak': streak_tc,
        })

    return result


# ── H2H: kazanma sayısı ekle ─────────────────────────────────────────────────

def _compute_h2h_window(matches: list, home_team: str, away_team: str) -> dict:
    """
    H2H maçları için genel istatistiklere ek olarak takım kazanma sayılarını hesaplar.

    result alanı: 'W'/'D'/'L' — o maçtaki EV SAHİBİ perspektifinden.
    """
    base = _compute_window_stats(matches)
    if base.get('match_count', 0) == 0:
        return base

    home_team_wins = 0
    away_team_wins = 0
    draws = 0

    for m in matches:
        score = _parse_score(m.get('score', ''))
        if score is None:
            continue
        mh, ma = m.get('home_team', ''), m.get('away_team', '')
        hg, ag = score

        # Kimin kazandığını belirle
        if hg > ag:    winner = 'home_in_match'
        elif ag > hg:  winner = 'away_in_match'
        else:          winner = 'draw'

        if winner == 'draw':
            draws += 1
        elif winner == 'home_in_match':
            if mh == home_team:   home_team_wins += 1
            elif mh == away_team: away_team_wins += 1
        else:  # away_in_match
            if ma == home_team:   home_team_wins += 1
            elif ma == away_team: away_team_wins += 1

    base['home_team_wins'] = home_team_wins
    base['away_team_wins'] = away_team_wins
    base['draws'] = draws
    return base


# ── Oran hareketi highlight'ı ────────────────────────────────────────────────

def _compute_odds_highlights(odds_comp_raw, home_team: str, away_team: str) -> dict:
    """
    1X2 oran hareketinden highlight üretir.

    Kurallar:
    - Favori (daha düşük açılış oranı olan taraf) %13+ düşüş → highlight
    - Outsider (daha yüksek açılış oranı olan taraf) %35+ düşüş → highlight
    - Düşüş: odds değerinin AZALMASI = piyasanın o tarafa güvenmesi artıyor

    Args:
        odds_comp_raw: odds_comp dict'i (içinde 'odds_comparison' listesi)
    """
    if not odds_comp_raw:
        return {'available': False}

    companies = odds_comp_raw.get('odds_comparison', [])
    if not companies:
        return {'available': False}

    home_ch, away_ch = [], []
    first_home_vals, first_away_vals = [], []

    for c in companies:
        eur = c.get('european_odds', {})
        if not eur:
            continue
        first = eur.get('first_odds') or {}
        pre   = eur.get('pre_match_odds') or {}

        try:
            fh = float(first.get('home') or 0)
            ph = float(pre.get('home') or 0)
            if fh > 1.0 and ph > 1.0:
                home_ch.append(((ph - fh) / fh) * 100)
                first_home_vals.append(fh)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

        try:
            fa = float(first.get('away') or 0)
            pa = float(pre.get('away') or 0)
            if fa > 1.0 and pa > 1.0:
                away_ch.append(((pa - fa) / fa) * 100)
                first_away_vals.append(fa)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    if not home_ch or not away_ch:
        return {'available': False}

    avg_hc = sum(home_ch) / len(home_ch)
    avg_ac = sum(away_ch) / len(away_ch)
    avg_fh = sum(first_home_vals) / len(first_home_vals)
    avg_fa = sum(first_away_vals) / len(first_away_vals)

    home_is_fav = avg_fh < avg_fa

    result = {
        'available': True,
        'home_odds_change_pct': round(avg_hc, 1),   # Negatif = oran düştü
        'away_odds_change_pct': round(avg_ac, 1),
        'home_is_favorite': home_is_fav,
        'highlights': [],
    }

    # Favori taraf oran düşüşü kontrolleri
    if home_is_fav:
        fav_team, fav_role, fav_ch = home_team, 'home', avg_hc
        out_team, out_role, out_ch = away_team, 'away', avg_ac
    else:
        fav_team, fav_role, fav_ch = away_team, 'away', avg_ac
        out_team, out_role, out_ch = home_team, 'home', avg_hc

    # Negatif değer = oran DÜŞTÜ
    if fav_ch < -_FAV_DROP:
        result['highlights'].append({
            'type': 'favorite_odds_drop',
            'team': fav_team,
            'role': fav_role,
            'change_pct': round(fav_ch, 1),
            'threshold': _FAV_DROP,
        })

    if out_ch < -_OUT_DROP:
        result['highlights'].append({
            'type': 'underdog_odds_drop',
            'team': out_team,
            'role': out_role,
            'change_pct': round(out_ch, 1),
            'threshold': _OUT_DROP,
        })

    return result


# ── Highlight üreteci ────────────────────────────────────────────────────────

def _build_highlight(type_key: str, scope: str, value: int, total: int = None):
    h = {'type': type_key, 'scope': scope, 'value': value}
    if total is not None:
        h['total'] = total
        h['pct'] = round(value / total * 100, 1)
    return h


def _generate_stat_highlights(
    home_all: dict, home_home: dict,
    away_all: dict, away_away: dict,
    h2h_last10: dict,
) -> list:
    """
    İstatistiksel eşikleri geçen bulguları highlight listesine ekler.

    Duplikasyon kuralları:
    - Seriler: son_20'de sadece değer 10'u AŞIYORSA eklenir (aksi hâlde son_10 ile aynı)
    - Sayımlar: son_20 bir stat için ancak son_10 eşiği geçemediyse eklenir (uzun vadeli trend)
      Eğer her ikisi de geçiyorsa sadece son_10 korunur.
    """
    # İlk geçiş: per-scope ayrı listeler oluştur
    _raw: dict[str, list] = {}  # scope → highlight listesi

    def _check(stats: dict, role: str, scope_label: str):
        n = stats.get('match_count', 0)
        if n < 3:
            return
        lst = _raw.setdefault(scope_label, [])

        checks = [
            # Maç sonu gol istatistikleri
            ('over_2_5_count',          'over_2_5',         _THRESH_70),
            ('under_2_5_count',         'under_2_5',        _THRESH_70),
            ('over_3_5_count',          'over_3_5',         _THRESH_60),
            ('btts_count',              'btts',             _THRESH_70),
            ('team_scored_count',       'team_scored',      _THRESH_90),
            ('team_conceded_count',     'team_conceded',    _THRESH_90),
            ('team_multi_goal_count',   'team_multi_goal',  _THRESH_70),
            ('team_clean_sheet_count',  'team_clean_sheet', _THRESH_70),
            # İlk yarı gol istatistikleri
            ('ht_over_0_5_count',       'iy_over_0_5',      _THRESH_70),   # IY 0.5 Üst
            ('ht_over_1_5_count',       'iy_over_1_5',      _THRESH_60),   # IY 1.5 Üst
            ('ht_btts_count',           'iy_btts',          _THRESH_70),   # IY KG Var
            ('team_scored_ht_count',    'iy_team_scored',   _THRESH_70),   # Takım IY gol attı
        ]

        for key, suffix, thresh in checks:
            v = stats.get(key)
            if v is None:
                continue
            if v / n >= thresh:
                lst.append(_build_highlight(f'{role}_{suffix}', scope_label, v, n))

        # Seriler (eşik: MIN_STREAK+1 = 4, daha anlamlı)
        for streak_key, suffix in [
            ('over_2_5_streak',        'over_2_5_streak'),
            ('btts_streak',            'btts_streak'),
            ('team_scoring_streak',    'team_scoring_streak'),
            ('team_conceding_streak',  'team_conceding_streak'),
        ]:
            sv = stats.get(streak_key)
            if sv is not None and sv >= _MIN_STREAK + 1:  # >= 4
                lst.append(_build_highlight(f'{role}_{suffix}', scope_label, sv))

    # ── Tüm scope'ları işle ──────────────────────────────────────────────
    _check(home_all.get('last_10', {}), 'home', 'son_10')
    _check(home_all.get('last_20', {}), 'home', 'son_20')
    _check(home_home.get('last_10', {}), 'home', 'ic_saha_son_10')
    _check(away_all.get('last_10', {}), 'away', 'son_10')
    _check(away_all.get('last_20', {}), 'away', 'son_20')
    _check(away_away.get('last_10', {}), 'away', 'dis_saha_son_10')

    # ── H2H ──────────────────────────────────────────────────────────────
    n_h2h = h2h_last10.get('match_count', 0)
    if n_h2h >= 3:
        h2h_lst = _raw.setdefault(f'h2h_son_{n_h2h}', [])
        for key, typ in [
            ('btts_count',         'h2h_btts'),
            ('over_2_5_count',     'h2h_over_2_5'),
            ('under_2_5_count',    'h2h_under_2_5'),
            ('over_3_5_count',     'h2h_over_3_5'),
            ('ht_over_0_5_count',  'h2h_iy_over_0_5'),
            ('ht_over_1_5_count',  'h2h_iy_over_1_5'),
            ('ht_btts_count',      'h2h_iy_btts'),
        ]:
            v = h2h_last10.get(key, 0)
            if v / n_h2h >= _THRESH_70:
                h2h_lst.append(_build_highlight(typ, f'h2h_son_{n_h2h}', v, n_h2h))

    # ── Duplikasyon temizliği ─────────────────────────────────────────────
    # son_10'daki stat type'larını öğren
    son10_types_home = {h['type'] for h in _raw.get('son_10', []) if h['type'].startswith('home_')}
    son10_types_away = {h['type'] for h in _raw.get('son_10', []) if h['type'].startswith('away_')}

    highlights = []

    for scope, items in _raw.items():
        for h in items:
            t   = h['type']
            sv  = h.get('value', 0)

            if scope == 'son_20':
                is_streak = 'streak' in t
                if is_streak:
                    # Seri 10'u aşmıyorsa son_10 ile aynı → atla
                    if sv <= 10:
                        continue
                else:
                    # Aynı stat son_10'da varsa → atla (son_10 yeterli)
                    if t in son10_types_home or t in son10_types_away:
                        continue

            highlights.append(h)

    return highlights


# ── Ana giriş noktası ────────────────────────────────────────────────────────

def compute_spotlight_stats(data: dict) -> dict:
    """
    Ana fonksiyon. `data` dict'i içindeki ham verileri kullanır:
      - data['h2h_details']  → head_to_head, home_team_previous_matches, away_team_previous_matches
      - data['match_info']   → home_team_name, away_team_name
      - data['odds_comp']    → 1X2 oran hareketleri

    Returns:
        {'spotlight_stats': {...}}
    """
    try:
        h2h_details = data.get('h2h_details') or {}
        match_info  = data.get('match_info') or {}
        odds_comp   = data.get('odds_comp')

        home_team = match_info.get('home_team_name', '')
        away_team = match_info.get('away_team_name', '')

        h2h_matches  = h2h_details.get('head_to_head', []) or []
        home_prev    = h2h_details.get('home_team_previous_matches', []) or []
        away_prev    = h2h_details.get('away_team_previous_matches', []) or []

        if not home_prev and not away_prev and not h2h_matches:
            return {'spotlight_stats': {'available': False}}

        # ── Ev sahibi istatistikleri ──────────────────────────────────────
        home_all = {
            'last_10': _compute_window_stats(home_prev[:10], home_team),
            'last_20': _compute_window_stats(home_prev[:20], home_team),
        }
        # Sadece ev sahibi rolündeyken oynadığı maçlar
        home_only = [m for m in home_prev if m.get('home_team') == home_team]
        home_home = {
            'last_10': _compute_window_stats(home_only[:10], home_team),
        }

        # ── Deplasman istatistikleri ──────────────────────────────────────
        away_all = {
            'last_10': _compute_window_stats(away_prev[:10], away_team),
            'last_20': _compute_window_stats(away_prev[:20], away_team),
        }
        # Sadece deplasman rolündeyken oynadığı maçlar
        away_only = [m for m in away_prev if m.get('away_team') == away_team]
        away_away = {
            'last_10': _compute_window_stats(away_only[:10], away_team),
        }

        # ── H2H istatistikleri ────────────────────────────────────────────
        h2h_stats = {
            'last_5':  _compute_h2h_window(h2h_matches[:5],  home_team, away_team),
            'last_10': _compute_h2h_window(h2h_matches[:10], home_team, away_team),
        }

        # ── Oran hareketi ─────────────────────────────────────────────────
        odds_hl = _compute_odds_highlights(odds_comp, home_team, away_team)

        # ── Highlight listesi ─────────────────────────────────────────────
        stat_highlights = _generate_stat_highlights(
            home_all, home_home,
            away_all, away_away,
            h2h_stats.get('last_10', {}),
        )

        # Oran highlight'larını başa al (daha güçlü sinyal)
        odds_items = odds_hl.get('highlights', []) if odds_hl.get('available') else []
        all_highlights = odds_items + stat_highlights

        return {
            'spotlight_stats': {
                'available': True,
                'home_team': {
                    'all_games': home_all,
                    'home_games': home_home,
                },
                'away_team': {
                    'all_games': away_all,
                    'away_games': away_away,
                },
                'h2h': h2h_stats,
                'odds': odds_hl,
                'highlights': all_highlights,
            }
        }

    except Exception as e:
        logger.warning(f"Spotlight stats computation failed: {e}", exc_info=True)
        return {'spotlight_stats': {'available': False}}
