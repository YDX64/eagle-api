"""
Eagle Prediction Cron - LOCAL algorithms only.
Uses Eagle's own analysis pipeline (14 algorithms):
  - final_predictions (1x2, goal_lines, btts, ht)
  - poisson_model
  - odds_movement
  - streak_detector
  - h2h
  - team_performance
  - odds_analysis
  - odds_trends
  - correct_score
  - spotlight
  - tactics
  - tips

No external API dependencies (Falcon, Predator, Mixer).
"""
import os
import json
import time
import logging
import threading
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
EAGLE_CRON_INTERVAL = int(os.getenv('EAGLE_CRON_INTERVAL', '600'))  # 10 min


def get_predictions_path(target_date: str) -> str:
    return os.path.join(DATA_DIR, f'eagle_predictions_{target_date}.json')


def load_cached_predictions(target_date: str) -> dict | None:
    path = get_predictions_path(target_date)
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            return data
    except Exception as e:
        logger.warning(f"[Eagle Cron] Cache load error: {e}")
    return None


def save_predictions(target_date: str, result: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = get_predictions_path(target_date)
    result['_timestamp'] = time.time()
    result['_collected_at'] = datetime.utcnow().isoformat()
    try:
        # Write to temp file first, then rename (atomic)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(tmp, path)
        logger.info(f"[Eagle Cron] Saved {len(result.get('matches', []))} predictions")
    except Exception as e:
        logger.error(f"[Eagle Cron] Save error: {e}")


def _picks_agree(eagle_pick: str, falcon_pick: str, market: str) -> bool:
    """Check if Eagle and Falcon predictions agree."""
    e = eagle_pick.lower().replace(' ', '')
    f = falcon_pick.lower().replace(' ', '')
    
    if market == 'ms':
        # Ms1, 1, 1X all agree on home
        e_home = any(x in e for x in ['1', 'ms1', '1x'])
        f_home = any(x in f for x in ['1', 'ms1', '1x'])
        e_away = any(x in e for x in ['2', 'ms2', 'x2'])
        f_away = any(x in f for x in ['2', 'ms2', 'x2'])
        return (e_home and f_home) or (e_away and f_away) or (e == f)
    
    if market in ('over25', 'over35'):
        e_over = 'ust' in e or 'üst' in e
        f_over = 'ust' in f or 'üst' in f
        return e_over == f_over
    
    if market == 'btts':
        e_yes = 'var' in e or 'yes' in e
        f_yes = 'var' in f or 'yes' in f
        return e_yes == f_yes
    
    return e == f


# High-odds markets — kept for coupon value (low hit rate but high payout)
# correct_score: ~7% hit rate but 8-15x odds → profitable in coupons
# htft: risky HT/FT combos with 3-8x odds
SKIP_MARKETS = set()  # Nothing skipped — all markets valuable
# Minimum confidence for HT predictions (80+ = 100%, 60+ = 45%, <45 = 22%)
HT_MIN_CONFIDENCE = 0  # Keep all — frontend should flag confidence tiers


def _build_eagle_match_result(match_id: int, match_data: dict, bee_match: dict) -> dict | None:
    """Build Eagle prediction result from local analysis data."""
    analysis = match_data.get('analysis', {})
    fp = analysis.get('final_predictions', {})
    tips = analysis.get('tips', {})
    falcon = analysis.get('falcon_predictions', {})
    falcon_tahminler = falcon.get('tahminler', {}) if falcon else {}
    falcon_yuzdeler = falcon.get('yuzdeler', {}) if falcon else {}
    
    if not fp:
        return None
    
    # Extract predictions from final_predictions
    predictions = {}
    
    # MS (1x2)
    x1x2 = fp.get('1x2', {})
    if x1x2:
        home = x1x2.get('home', 0)
        draw = x1x2.get('draw', 0)
        away = x1x2.get('away', 0)
        best = max([('1', home), ('X', draw), ('2', away)], key=lambda x: x[1])
        # Check if Falcon also has MS prediction
        falcon_ms = falcon_tahminler.get('ms_tahmini', '')
        ms_agreement = 1
        ms_sources = {'eagle': {'pick': best[0], 'confidence': best[1]}}
        if falcon_ms:
            ms_sources['falcon'] = {'pick': falcon_ms, 'confidence': falcon.get('confidence', 65)}
            ms_agreement = 2 if _picks_agree(best[0], falcon_ms, 'ms') else 1
        
        predictions['ms'] = {
            'eagle_pick': best[0],
            'eagle_confidence': min(best[1] * 1.2 + (10 if ms_agreement >= 2 else 0), 99),
            'agreement': ms_agreement,
            'total_sources': len(ms_sources),
            'sources': ms_sources,
            'all_directions': {best[0]: {'avg_confidence': best[1], 'sources': ['eagle']}},
            'winning_direction': best[0],
            'weight_score': 1,
        }
    
    # Over/Under 2.5
    gl = fp.get('goal_lines', {})
    if gl:
        over25 = gl.get('over_2_5', 0)
        under25 = gl.get('under_2_5', 0)
        if over25 > under25:
            pick, conf = 'Ust 2.5', over25
        else:
            pick, conf = 'Alt 2.5', under25
        falcon_ou = falcon_tahminler.get('ust_tahmini', '')
        ou_agreement = 1
        ou_sources = {'eagle': {'pick': pick, 'confidence': conf}}
        if falcon_ou:
            ou_sources['falcon'] = {'pick': falcon_ou, 'confidence': falcon.get('confidence', 65)}
            ou_agreement = 2 if _picks_agree(pick, falcon_ou, 'over25') else 1
        
        predictions['over25'] = {
            'eagle_pick': pick,
            'eagle_confidence': min(conf * 1.15 + (10 if ou_agreement >= 2 else 0), 99),
            'agreement': ou_agreement, 'total_sources': len(ou_sources),
            'sources': ou_sources,
            'all_directions': {pick: {'avg_confidence': conf, 'sources': ['eagle']}},
            'winning_direction': pick, 'weight_score': 1,
        }
        
        # Over/Under 3.5
        over35 = gl.get('over_3_5', 0)
        under35 = gl.get('under_3_5', 0)
        if over35 > 0 or under35 > 0:
            if over35 > under35:
                pick35, conf35 = 'Ust 3.5', over35
            else:
                pick35, conf35 = 'Alt 3.5', under35
            predictions['over35'] = {
                'eagle_pick': pick35,
                'eagle_confidence': min(conf35 * 1.15, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': pick35, 'confidence': conf35}},
                'all_directions': {pick35: {'avg_confidence': conf35, 'sources': ['eagle']}},
                'winning_direction': pick35, 'weight_score': 1,
            }
    
    # BTTS
    btts = fp.get('btts', {})
    if btts:
        yes = btts.get('yes', 0)
        no = btts.get('no', 0)
        if yes > no:
            pick_b, conf_b = 'KG Var', yes
        else:
            pick_b, conf_b = 'KG Yok', no
        falcon_btts = falcon_tahminler.get('kg_tahmini', '')
        btts_agreement = 1
        btts_sources = {'eagle': {'pick': pick_b, 'confidence': conf_b}}
        if falcon_btts:
            btts_sources['falcon'] = {'pick': falcon_btts, 'confidence': falcon.get('confidence', 65)}
            btts_agreement = 2 if _picks_agree(pick_b, falcon_btts, 'btts') else 1
        
        predictions['btts'] = {
            'eagle_pick': pick_b,
            'eagle_confidence': min(conf_b * 1.15 + (10 if btts_agreement >= 2 else 0), 99),
            'agreement': btts_agreement, 'total_sources': len(btts_sources),
            'sources': btts_sources,
            'all_directions': {pick_b: {'avg_confidence': conf_b, 'sources': ['eagle']}},
            'winning_direction': pick_b, 'weight_score': 1,
        }
    
    # HT Result (filtered: only include if confidence > HT_MIN_CONFIDENCE)
    ht = fp.get('ht_1x2', {})
    if ht:
        h_home = ht.get('home', 0)
        h_draw = ht.get('draw', 0)
        h_away = ht.get('away', 0)
        ht_map = {'IY 1': h_home, 'IY X': h_draw, 'IY 2': h_away}
        ht_best = max(ht_map.items(), key=lambda x: x[1])
        if ht_best[1] >= HT_MIN_CONFIDENCE:
            predictions['ht_result'] = {
                'eagle_pick': ht_best[0],
                'eagle_confidence': min(ht_best[1] * 1.15, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': ht_best[0], 'confidence': ht_best[1]}},
                'all_directions': {ht_best[0]: {'avg_confidence': ht_best[1], 'sources': ['eagle']}},
                'winning_direction': ht_best[0], 'weight_score': 1,
            }
    
    # HT Over 0.5
    ht_goals = fp.get('ht_goals', {})
    if ht_goals:
        ht_over = ht_goals.get('over_0_5', 0)
        ht_under = ht_goals.get('under_0_5', 0)
        if ht_over > ht_under:
            ht_pick, ht_conf = 'IY Ust 0.5', ht_over
        else:
            ht_pick, ht_conf = 'IY Alt 0.5', ht_under
        predictions['ht_over05'] = {
            'eagle_pick': ht_pick,
            'eagle_confidence': min(ht_conf * 1.15, 99),
            'agreement': 1, 'total_sources': 1,
            'sources': {'eagle': {'pick': ht_pick, 'confidence': ht_conf}},
            'all_directions': {ht_pick: {'avg_confidence': ht_conf, 'sources': ['eagle']}},
            'winning_direction': ht_pick, 'weight_score': 1,
        }
    
    # Corner prediction (enhanced - from corner_predictions algorithm + Falcon)
    corner_analysis = fp.get('corner_analysis', {})
    falcon_corner = falcon_tahminler.get('korner_tahmini', '')
    if corner_analysis:
        corner_pick = corner_analysis.get('top_pick', '')
        corner_prob = corner_analysis.get('top_pick_probability', 50)
        corner_conf = corner_analysis.get('confidence', 50)
        corner_sources = {'eagle_corner': {'pick': corner_pick, 'confidence': corner_conf}}
        corner_agreement = 1
        if falcon_corner:
            corner_sources['falcon'] = {'pick': falcon_corner, 'confidence': 65}
            corner_agreement = 2
        if corner_pick:
            predictions['corner'] = {
                'eagle_pick': corner_pick,
                'eagle_confidence': min(corner_conf * 1.1 + (8 if corner_agreement >= 2 else 0), 99),
                'agreement': corner_agreement, 'total_sources': len(corner_sources),
                'sources': corner_sources,
                'all_directions': {corner_pick: {'avg_confidence': corner_prob, 'sources': list(corner_sources.keys())}},
                'winning_direction': corner_pick, 'weight_score': 1,
                'details': {
                    'expected_total': corner_analysis.get('expected_total_corners', 0),
                    'over_under': corner_analysis.get('over_under', {}),
                    'corner_handicap': corner_analysis.get('corner_handicap', {}),
                },
            }
    elif falcon_corner:
        predictions['corner'] = {
            'eagle_pick': falcon_corner,
            'eagle_confidence': 65,
            'agreement': 1, 'total_sources': 1,
            'sources': {'falcon': {'pick': falcon_corner, 'confidence': 65}},
            'all_directions': {falcon_corner: {'avg_confidence': 65, 'sources': ['falcon']}},
            'winning_direction': falcon_corner, 'weight_score': 1,
        }
    
    # ===== 6 NEW EAGLE ALGORITHM MARKETS =====

    # Card predictions
    card_data = fp.get('card', {})
    if card_data:
        card_top = card_data.get('top_pick', '')
        card_prob = card_data.get('top_pick_probability', 50)
        card_conf = card_data.get('confidence', 50)
        if card_top:
            predictions['card'] = {
                'eagle_pick': card_top,
                'eagle_confidence': min(card_conf * 1.1, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': card_top, 'confidence': card_conf}},
                'all_directions': {card_top: {'avg_confidence': card_prob, 'sources': ['eagle']}},
                'winning_direction': card_top, 'weight_score': 1,
                'details': {
                    'expected_total': card_data.get('expected_total_cards', 0),
                    'over_under': card_data.get('over_under', {}),
                },
            }

    # Enhanced correct score — high-odds market, send top 3 scores for coupons
    cs_data = fp.get('correct_score_enhanced', {})
    if cs_data and 'correct_score' not in SKIP_MARKETS:
        top_scores = cs_data.get('top_scores', [])
        cs_conf = cs_data.get('confidence', 50)
        if top_scores and len(top_scores) >= 2:
            # Skip 0-0 if it dominates and pick the most interesting score
            # If top score is 0-0 and 2nd score is different, use 2nd
            top_score = top_scores[0]
            if top_score.get('score') == '0:0' and len(top_scores) > 1:
                # Use the highest non-0-0 score (more valuable for coupons)
                for s in top_scores[1:4]:
                    if s.get('score') != '0:0':
                        top_score = s
                        break
            score_str = top_score.get('score', '1:0').replace(':', '-')
            score_prob = top_score.get('probability', 0)
            # Normalize probability if it's > 100 (bug: raw odds instead of probability)
            if score_prob > 100:
                score_prob = min(score_prob / 100, 99)
            predictions['correct_score'] = {
                'eagle_pick': 'Skor ' + score_str,
                'eagle_confidence': min(cs_conf * 0.9, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': score_str, 'confidence': score_prob}},
                'all_directions': {score_str: {'avg_confidence': score_prob, 'sources': ['eagle']}},
                'winning_direction': score_str, 'weight_score': 1,
                'details': {
                    'top_scores': top_scores[:5],
                    'model_type': cs_data.get('model_info', {}).get('model_type', ''),
                },
            }

    # Handicap predictions
    hcp_data = fp.get('handicap', {})
    if hcp_data:
        rec_line = hcp_data.get('recommended_line', 0)
        rec_side = hcp_data.get('recommended_side', 'home')
        rec_prob = hcp_data.get('recommended_prob', 50)
        hcp_conf = hcp_data.get('confidence', 50)
        side_label = 'Ev' if rec_side == 'home' else 'Dep'
        hcp_pick = 'AH %+.1f %s' % (rec_line, side_label)
        predictions['handicap'] = {
            'eagle_pick': hcp_pick,
            'eagle_confidence': min(hcp_conf * 1.1, 99),
            'agreement': 1, 'total_sources': 1,
            'sources': {'eagle': {'pick': hcp_pick, 'confidence': rec_prob}},
            'all_directions': {hcp_pick: {'avg_confidence': rec_prob, 'sources': ['eagle']}},
            'winning_direction': hcp_pick, 'weight_score': 1,
            'details': {
                'value_bets': hcp_data.get('value_bets', [])[:3],
                'goal_diff_expected': hcp_data.get('goal_difference_expected', 0),
            },
        }

    # First half predictions
    fh_data = fp.get('first_half', {})
    if fh_data:
        fh_pick = fh_data.get('top_pick', '')
        fh_prob = fh_data.get('top_pick_probability', 50)
        fh_conf = fh_data.get('confidence', 50)
        if fh_pick:
            predictions['first_half'] = {
                'eagle_pick': fh_pick,
                'eagle_confidence': min(fh_conf * 1.1, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': fh_pick, 'confidence': fh_prob}},
                'all_directions': {fh_pick: {'avg_confidence': fh_prob, 'sources': ['eagle']}},
                'winning_direction': fh_pick, 'weight_score': 1,
                'details': {
                    'ht_correct_score': fh_data.get('ht_correct_score', [])[:5],
                    'ht_xg': fh_data.get('ht_expected_goals', {}),
                },
            }

    # Second half predictions
    sh_data = fp.get('second_half', {})
    if sh_data:
        sh_pick = sh_data.get('top_pick', '')
        sh_prob = sh_data.get('top_pick_probability', 50)
        sh_conf = sh_data.get('confidence', 50)
        if sh_pick:
            predictions['second_half'] = {
                'eagle_pick': sh_pick,
                'eagle_confidence': min(sh_conf * 1.1, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': sh_pick, 'confidence': sh_prob}},
                'all_directions': {sh_pick: {'avg_confidence': sh_prob, 'sources': ['eagle']}},
                'winning_direction': sh_pick, 'weight_score': 1,
                'details': {
                    'which_half_more': sh_data.get('which_half_more_goals', {}),
                    'sh_xg': sh_data.get('sh_expected_goals', {}),
                },
            }

    # Half-based BTTS
    hb_data = fp.get('half_btts', {})
    if hb_data:
        hb_pick = hb_data.get('top_pick', '')
        hb_prob = hb_data.get('top_pick_probability', 50)
        hb_conf = hb_data.get('confidence', 50)
        if hb_pick:
            predictions['half_btts'] = {
                'eagle_pick': hb_pick,
                'eagle_confidence': min(hb_conf * 1.1, 99),
                'agreement': 1, 'total_sources': 1,
                'sources': {'eagle': {'pick': hb_pick, 'confidence': hb_prob}},
                'all_directions': {hb_pick: {'avg_confidence': hb_prob, 'sources': ['eagle']}},
                'winning_direction': hb_pick, 'weight_score': 1,
                'details': {
                    'combinations': hb_data.get('combinations', {}),
                    'fh_btts': hb_data.get('first_half_btts', {}),
                    'sh_btts': hb_data.get('second_half_btts', {}),
                },
            }

    # Risky HT/FT combination - SKIPPED (in SKIP_MARKETS)
    falcon_risky = falcon_tahminler.get('riskli_tahmin', '')
    if falcon_risky and 'htft' not in SKIP_MARKETS:
        predictions['htft'] = {
            'eagle_pick': falcon_risky,
            'eagle_confidence': 55,
            'agreement': 1, 'total_sources': 1,
            'sources': {'falcon': {'pick': falcon_risky, 'confidence': 55}},
            'all_directions': {falcon_risky: {'avg_confidence': 55, 'sources': ['falcon']}},
            'winning_direction': falcon_risky, 'weight_score': 1,
        }
    
    if not predictions:
        return None
    
    # Find best prediction
    best_market = max(predictions.items(), key=lambda x: x[1]['eagle_confidence'])
    overall_conf = sum(p['eagle_confidence'] for p in predictions.values()) / len(predictions)
    
    # Match info
    league = bee_match.get('league', '')
    if isinstance(league, dict):
        league = league.get('name', '')
    
    return {
        'match': {
            'match_id': match_id,
            'home_team': bee_match.get('home_team', ''),
            'away_team': bee_match.get('away_team', ''),
            'home_team_id': bee_match.get('home_team_id') or (match_data.get('match_info') or {}).get('home_team_id'),
            'away_team_id': bee_match.get('away_team_id') or (match_data.get('match_info') or {}).get('away_team_id'),
            'home_logo': (match_data.get('match_info') or {}).get('home_team_logo_url', ''),
            'away_logo': (match_data.get('match_info') or {}).get('away_team_logo_url', ''),
            'league': league,
            'match_time': bee_match.get('match_time', ''),
            'match_date': bee_match.get('match_date', ''),
        },
        'predictions': predictions,
        'best_pick': best_market[1]['eagle_pick'],
        'best_market': best_market[0],
        'best_confidence': best_market[1]['eagle_confidence'],
        'overall_confidence': overall_conf,
        'max_agreement': 1,
        'is_banko': overall_conf >= 80,
        'banko': None,
        'source_status': {'eagle': True},
    }


def run_eagle_collection(target_date: str = None):
    """Run Eagle prediction collection using LOCAL algorithms only."""
    if not target_date:
        target_date = date.today().strftime('%Y-%m-%d')

    # File lock
    lock_path = os.path.join(DATA_DIR, f'.eagle_lock_{target_date}')
    if os.path.exists(lock_path):
        lock_age = time.time() - os.path.getmtime(lock_path)
        if lock_age < 600:
            logger.info(f"[Eagle Cron] Skipping - lock exists ({lock_age:.0f}s old)")
            return
        os.remove(lock_path)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(lock_path, 'w') as f:
        f.write(str(os.getpid()))

    logger.info(f"[Eagle Cron] Starting LOCAL collection for {target_date}")
    start = time.time()

    try:
        from routes.utils import fetch_date_matches_cached, fetch_match_data_with_analysis_cached

        # 1. Get match list (local Bee data)
        matches_data = fetch_date_matches_cached(target_date)
        bee_matches = matches_data.get('matches', []) if matches_data else []
        logger.info(f"[Eagle Cron] {len(bee_matches)} matches for {target_date}")

        if not bee_matches:
            save_predictions(target_date, {
                'date': target_date, 'matches': [],
                'meta': {'total': 0, 'sources': {'eagle': 0}}
            })
            try: os.remove(lock_path)
            except: pass
            return

        # 2. Analyze each match locally (concurrent, no external API calls)
        results = []
        analyzed = 0
        errors = 0

        def analyze_match(bee_match):
            mid = bee_match.get('match_id') or bee_match.get('id')
            if not mid:
                return None
            try:
                data = fetch_match_data_with_analysis_cached(mid)
                if data:
                    return _build_eagle_match_result(mid, data, bee_match)
            except Exception as e:
                logger.debug(f"[Eagle Cron] Match {mid} error: {e}")
            return None

        with ThreadPoolExecutor(max_workers=10) as pool:
            future_map = {pool.submit(analyze_match, m): m for m in bee_matches}
            for future in as_completed(future_map, timeout=300):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        analyzed += 1
                    if analyzed % 50 == 0 and analyzed > 0:
                        logger.info(f"[Eagle Cron] Progress: {analyzed} analyzed")
                except Exception:
                    errors += 1

        results.sort(key=lambda m: m.get('overall_confidence', 0), reverse=True)
        banko_count = sum(1 for m in results if m.get('is_banko'))

        output = {
            'date': target_date,
            'matches': results,
            'meta': {
                'total': len(results),
                'banko_count': banko_count,
                'high_confidence': sum(1 for m in results if m.get('overall_confidence', 0) >= 70),
                'sources': {'eagle': analyzed},
                'errors': errors,
            },
        }
        save_predictions(target_date, output)
        elapsed = time.time() - start
        logger.info(f"[Eagle Cron] Done: {analyzed} predictions in {elapsed:.1f}s ({errors} errors)")

    except Exception as e:
        logger.error(f"[Eagle Cron] Failed: {e}", exc_info=True)
    finally:
        try: os.remove(lock_path)
        except: pass


class EagleCronThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name='EagleCronThread')
        self.running = True

    def run(self):
        logger.info(f"[Eagle Cron] Started (interval: {EAGLE_CRON_INTERVAL}s)")
        time.sleep(10)  # Initial delay
        while self.running:
            try:
                run_eagle_collection()
            except Exception as e:
                logger.error(f"[Eagle Cron] Error: {e}")
            for _ in range(EAGLE_CRON_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
        logger.info("[Eagle Cron] Stopped")

    def stop(self):
        self.running = False


_cron_thread = None

def start_eagle_cron():
    global _cron_thread
    if _cron_thread and _cron_thread.is_alive():
        return
    _cron_thread = EagleCronThread()
    _cron_thread.start()

def stop_eagle_cron():
    global _cron_thread
    if _cron_thread:
        _cron_thread.stop()
        _cron_thread = None
