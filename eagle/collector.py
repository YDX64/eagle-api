"""
Eagle Collector - Fetches predictions from Falcon and Predator APIs
Bee (local) predictions are obtained directly from the analysis pipeline.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from eagle.config import EagleConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Falcon API
# =============================================================================

async def fetch_falcon_matches(client: httpx.AsyncClient, target_date: str) -> List[dict]:
    """Fetch match list from Falcon API. Returns list of match dicts."""
    url = f"{EagleConfig.FALCON_API_URL}/fetch-matches"
    headers = {}
    if EagleConfig.FALCON_API_KEY:
        headers["X-API-KEY"] = EagleConfig.FALCON_API_KEY

    try:
        resp = await client.post(
            url, json={"date": target_date},
            headers=headers, timeout=EagleConfig.FALCON_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("data") or data.get("matches") or []
        if not isinstance(raw, list):
            return []

        matches: List[dict] = []
        for item in raw:
            if isinstance(item, dict):
                matches.append(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                m: dict = {"id": item[0], "home_team": item[1], "away_team": item[2]}
                if len(item) > 3:
                    m["league"] = item[3] or ""
                if len(item) > 4:
                    m["match_time"] = item[4] or ""
                matches.append(m)

        logger.info(f"[Eagle] Falcon: {len(matches)} matches for {target_date}")
        return matches
    except Exception as e:
        logger.error(f"[Eagle] Falcon match list error: {e}")
        return []


async def fetch_falcon_analysis(client: httpx.AsyncClient, match_id: int) -> Optional[dict]:
    """Fetch single match analysis from Falcon API with retry on 429."""
    url = f"{EagleConfig.FALCON_API_URL}/analyze-match"
    headers = {}
    if EagleConfig.FALCON_API_KEY:
        headers["X-API-KEY"] = EagleConfig.FALCON_API_KEY

    for attempt in range(3):
        try:
            resp = await client.post(
                url, json={"match_id": match_id},
                headers=headers, timeout=EagleConfig.FALCON_TIMEOUT,
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("data", result)
            if resp.status_code == 429:
                wait = 2 ** attempt + 1
                logger.debug(f"[Eagle] Falcon 429 for {match_id}, retry {attempt+1} in {wait}s")
                await asyncio.sleep(wait)
                continue
            logger.warning(f"[Eagle] Falcon analysis {match_id}: HTTP {resp.status_code}")
            return None
        except Exception as e:
            logger.warning(f"[Eagle] Falcon analysis error {match_id}: {e}")
            if attempt < 2:
                await asyncio.sleep(1)
    return None


async def fetch_falcon_for_match(client: httpx.AsyncClient, match_id: int) -> Optional[dict]:
    """Fetch Falcon analysis for a single match by ID."""
    return await fetch_falcon_analysis(client, match_id)


# =============================================================================
# Predator API
# =============================================================================

async def fetch_predator_picks(client: httpx.AsyncClient, target_date: str) -> List[dict]:
    """Fetch all picks from Predator API."""
    url = f"{EagleConfig.PREDATOR_API_URL}/api/v1/picks/today"
    headers = {}
    if EagleConfig.PREDATOR_API_KEY:
        headers["X-API-Key"] = EagleConfig.PREDATOR_API_KEY

    try:
        resp = await client.get(url, headers=headers, timeout=EagleConfig.PREDATOR_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        picks = data.get("data", {}).get("picks", []) or data.get("picks", [])
        logger.info(f"[Eagle] Predator: {len(picks)} picks")
        return picks
    except Exception as e:
        logger.error(f"[Eagle] Predator fetch error: {e}")
        return []


async def fetch_predator_match(client: httpx.AsyncClient, match_id: int) -> Optional[dict]:
    """Fetch single match detail from Predator API."""
    url = f"{EagleConfig.PREDATOR_API_URL}/api/v1/match/{match_id}"
    headers = {}
    if EagleConfig.PREDATOR_API_KEY:
        headers["X-API-Key"] = EagleConfig.PREDATOR_API_KEY

    try:
        resp = await client.get(url, headers=headers, timeout=EagleConfig.PREDATOR_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", data)
        return None
    except Exception as e:
        logger.warning(f"[Eagle] Predator match {match_id} error: {e}")
        return None


# =============================================================================
# Predator V2 API (optional)
# =============================================================================

async def fetch_predator_v2_match(client: httpx.AsyncClient, match_id: int) -> Optional[dict]:
    """Fetch analysis from Predator V2 if configured."""
    if not EagleConfig.PREDATOR_V2_API_URL:
        return None

    url = f"{EagleConfig.PREDATOR_V2_API_URL}/api/v1/match/{match_id}"
    headers = {}
    if EagleConfig.PREDATOR_V2_API_KEY:
        headers["X-API-Key"] = EagleConfig.PREDATOR_V2_API_KEY

    try:
        resp = await client.get(url, headers=headers, timeout=EagleConfig.DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", data)
        return None
    except Exception as e:
        logger.warning(f"[Eagle] Predator V2 match {match_id} error: {e}")
        return None


# =============================================================================
# Prediction Extractors (from Mixer collector.py patterns)
# =============================================================================

def _parse_pct_string(s: str) -> Optional[Dict[str, float]]:
    """Parse Falcon percentage string like '29% - 28% - 42%' into {1: 29, X: 28, 2: 42}."""
    if not s or not isinstance(s, str):
        return None
    parts = [p.strip().replace("%", "").strip() for p in s.split("-")]
    if len(parts) == 3:
        try:
            return {"1": float(parts[0]), "X": float(parts[1]), "2": float(parts[2])}
        except (ValueError, TypeError):
            pass
    return None


def extract_falcon_predictions(data: dict) -> List[Tuple[str, str, Optional[float]]]:
    """Extract (market, prediction, confidence) from Falcon analysis data."""
    preds = []
    tahminler = data.get("tahminler") or {}
    yuzdeler = data.get("yuzdeler") or {}

    # MS from yuzdeler.ms_yuzdeleri
    ms_str = yuzdeler.get("ms_yuzdeleri", "")
    ms_parsed = _parse_pct_string(ms_str)
    if ms_parsed:
        best_key = max(ms_parsed, key=ms_parsed.get)
        label_map = {"1": "Ms1", "X": "MsX", "2": "Ms2"}
        preds.append(("ms", label_map.get(best_key, best_key), ms_parsed[best_key]))
    elif tahminler.get("ms_tahmini"):
        preds.append(("ms", str(tahminler["ms_tahmini"]), None))

    # Over/Under 2.5
    ust25_str = yuzdeler.get("ust_yuzdesi_1", "").replace("%", "").strip()
    if ust25_str:
        try:
            ust25 = float(ust25_str)
            if ust25 > 50:
                preds.append(("over25", "Üst 2.5", ust25))
            else:
                preds.append(("over25", "Alt 2.5", 100 - ust25))
        except ValueError:
            pass

    # Over/Under 3.5
    ust35_str = yuzdeler.get("ust_yuzdesi2", "").replace("%", "").strip()
    if ust35_str:
        try:
            ust35 = float(ust35_str)
            if ust35 > 50:
                preds.append(("over35", "Üst 3.5", ust35))
            else:
                preds.append(("over35", "Alt 3.5", 100 - ust35))
        except ValueError:
            pass

    # BTTS
    kg_pred = tahminler.get("kg_tahmini") or ""
    if kg_pred and str(kg_pred).strip():
        ev_gol = yuzdeler.get("ev_gol_yuzdesi", "").replace("%", "").strip()
        dep_gol = yuzdeler.get("dep_gol_yuzdesi", "").replace("%", "").strip()
        conf = None
        if ev_gol and dep_gol:
            try:
                conf = (float(ev_gol) + float(dep_gol)) / 2
            except ValueError:
                pass
        preds.append(("btts", str(kg_pred), conf))

    # HT result
    iy_str = yuzdeler.get("iy_yuzdeleri_", "")
    iy_parsed = _parse_pct_string(iy_str)
    if iy_parsed:
        best_key = max(iy_parsed, key=iy_parsed.get)
        label_map = {"1": "İY 1", "X": "İY X", "2": "İY 2"}
        preds.append(("ht_result", label_map.get(best_key, f"İY {best_key}"), iy_parsed[best_key]))

    # HT over 0.5
    ht_05_str = yuzdeler.get("ust_yuzdesi_05_ht", "").replace("%", "").strip()
    if ht_05_str:
        try:
            ht_05 = float(ht_05_str)
            if ht_05 > 50:
                preds.append(("ht_over05", "İY Üst 0.5", ht_05))
            else:
                preds.append(("ht_over05", "İY Alt 0.5", 100 - ht_05))
        except ValueError:
            pass

    # Corner
    korner = tahminler.get("korner_tahmini") or ""
    if korner and str(korner).strip():
        preds.append(("corner", str(korner), None))

    return preds


def extract_predator_predictions(pick: dict) -> List[Tuple[str, str, Optional[float]]]:
    """Extract (market, prediction, confidence) from Predator pick."""
    preds = []

    # MS
    ms = pick.get("ms_pick")
    if ms:
        tips = pick.get("tips") or {}
        ms_conf = None
        if isinstance(tips, dict) and "ms" in tips:
            ms_conf = tips["ms"].get("confidence")
        preds.append(("ms", ms, ms_conf))

    # Over/Under
    over = pick.get("over_pick")
    if over:
        tips = pick.get("tips") or {}
        ou_conf = None
        if isinstance(tips, dict) and "alt_ust" in tips:
            ou_conf = tips["alt_ust"].get("confidence")
        market = "over25" if "2.5" in str(over) or "over" in str(over).lower() else "over35"
        preds.append((market, over, ou_conf))

    # BTTS
    btts = pick.get("btts_pick")
    if btts:
        tips = pick.get("tips") or {}
        btts_conf = None
        if isinstance(tips, dict) and "kg" in tips:
            btts_conf = tips["kg"].get("confidence")
        preds.append(("btts", btts, btts_conf))

    # HT goal
    ht_goal = pick.get("ht_goal_pick") or pick.get("iy_gol_tahmini")
    if ht_goal:
        preds.append(("ht_over05", ht_goal, None))

    # Corner
    corner = pick.get("corner_pick") or pick.get("korner_pick")
    if corner:
        preds.append(("corner", corner, None))

    # HT result
    ht = pick.get("ht_pick") or pick.get("iy_tahmini")
    if ht:
        preds.append(("ht_result", ht, None))

    return preds


def extract_bee_predictions(analysis_data: dict) -> List[Tuple[str, str, Optional[float]]]:
    """Extract predictions from Bee (BumbleBee) analysis.final_predictions."""
    preds = []
    analysis = analysis_data.get("analysis") or {}
    fp = analysis.get("final_predictions") or {}
    if not fp:
        fp = analysis_data.get("final_predictions") or analysis_data.get("predictions") or {}

    # MS from 1x2
    ms = fp.get("1x2")
    if ms and isinstance(ms, dict):
        try:
            home = float(ms.get("home", 0))
            draw = float(ms.get("draw", 0))
            away = float(ms.get("away", 0))
            vals = {"Ms1": home, "MsX": draw, "Ms2": away}
            best_key = max(vals, key=vals.get)
            preds.append(("ms", best_key, vals[best_key]))
        except (ValueError, TypeError):
            pass

    # Goal lines
    gl = fp.get("goal_lines")
    if gl and isinstance(gl, dict):
        try:
            over25 = float(gl.get("over_2_5", 0))
            under25 = float(gl.get("under_2_5", 0))
            if over25 > under25:
                preds.append(("over25", "Üst 2.5", over25))
            else:
                preds.append(("over25", "Alt 2.5", under25))

            over35 = float(gl.get("over_3_5", 0))
            under35 = float(gl.get("under_3_5", 0))
            if over35 > 0 or under35 > 0:
                if over35 > under35:
                    preds.append(("over35", "Üst 3.5", over35))
                else:
                    preds.append(("over35", "Alt 3.5", under35))
        except (ValueError, TypeError):
            pass

    # BTTS
    btts = fp.get("btts")
    if btts and isinstance(btts, dict):
        try:
            yes = float(btts.get("yes", 0))
            no = float(btts.get("no", 0))
            if yes > no:
                preds.append(("btts", "Var", yes))
            else:
                preds.append(("btts", "Yok", no))
        except (ValueError, TypeError):
            pass

    # HT result
    ht = fp.get("ht_1x2")
    if ht and isinstance(ht, dict):
        try:
            home = float(ht.get("home", 0))
            draw = float(ht.get("draw", 0))
            away = float(ht.get("away", 0))
            vals = {"İY 1": home, "İY X": draw, "İY 2": away}
            best_key = max(vals, key=vals.get)
            preds.append(("ht_result", best_key, vals[best_key]))
        except (ValueError, TypeError):
            pass

    # HT over 0.5
    ht_goals = fp.get("ht_goals")
    if ht_goals and isinstance(ht_goals, dict):
        try:
            over05 = float(ht_goals.get("over_0_5", 0))
            under05 = float(ht_goals.get("under_0_5", 0))
            if over05 > under05:
                preds.append(("ht_over05", "İY Üst 0.5", over05))
            else:
                preds.append(("ht_over05", "İY Alt 0.5", under05))
        except (ValueError, TypeError):
            pass

    return preds


def extract_predator_v2_predictions(data: dict) -> List[Tuple[str, str, Optional[float]]]:
    """Extract predictions from Predator V2 (same structure as Bee)."""
    # Predator V2 uses same analysis pipeline as Bee
    return extract_bee_predictions(data)
