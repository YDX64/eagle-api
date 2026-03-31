"""
Result Resolver — fetches FINISHED match results from NowGoal.

Reuses the Eagle API's existing HTTP infrastructure (multi-source failover,
connection pooling, request headers) to pull the day's match data and extract
final scores, half-time scores, corners, and cards for finished matches.

Main entry point:
    resolve_match_results(target_date: str) -> list[dict]
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NowGoal status codes (from live_parsers.py MATCH_STATUS_MAP)
# ---------------------------------------------------------------------------
FINISHED_STATES = {-1}  # -1 = finished (normal FT, AET, PEN all map here)

# Pre-compiled patterns for parsing the A[] match arrays
RE_MATCH_ARRAY = re.compile(r"A\[(\d+)\]=\[([^\]]+)\]")

# Patterns for tech stats (corners, etc.) from detail.js
RE_TECH_STATS = re.compile(r'tc\[(\d+)\]="([^"]+)"')

# Stat IDs we care about (from live_parsers.py TECH_STATS_MAP)
STAT_ID_CORNERS = 6
STAT_ID_CORNERS_HT = 45


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_int(val: Any) -> Optional[int]:
    """Convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        s = str(val).strip().strip("'\"")
        if not s or s == "":
            return None
        return int(s)
    except (ValueError, TypeError):
        return None


def _smart_split(data_str: str) -> List[str]:
    """
    Split a JavaScript-style comma-separated string, respecting quoted values.

    Handles both single-quoted and unquoted fields, matching the parsing
    style used in parsers.py and live_parsers.py.
    """
    parts: List[str] = []
    current = ""
    in_quotes = False

    for char in data_str:
        if char == "'" and not in_quotes:
            in_quotes = True
        elif char == "'" and in_quotes:
            in_quotes = False
            parts.append(current)
            current = ""
        elif char == "," and not in_quotes:
            if current.strip():
                parts.append(current.strip())
            elif not parts or parts[-1] != current:
                # preserve empty field position
                parts.append("")
            current = ""
        else:
            current += char

    if current.strip():
        parts.append(current.strip())

    return parts


def _parse_match_from_array(data_str: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single A[n]=[...] entry from the NowGoal date response.

    NowGoal A[] format example:
        A[1]=[2859986,1,73809,31699,'Barau FC','Katsina United','2026,2,29,15,00,00',-1,0,0,0,0,0,0,1,0,'12','10','','',107,'','',0,0,0]

    We use a regex-based parser to correctly handle quoted strings with commas.
    """
    try:
        # Parse using regex: match quoted strings and bare values
        _TOKEN_RE = re.compile(r"'([^']*)'|([^,]+)")
        parts = [m.group(1) if m.group(1) is not None else m.group(2).strip()
                 for m in _TOKEN_RE.finditer(data_str)]
        if len(parts) < 13:
            return None

        # Regex parser positions (after proper quote handling):
        #  0: match_id, 1: league_id, 2: home_id, 3: away_id,
        #  4: home_name, 5: away_name, 6: datetime_str,
        #  7: state (-1=finished), 8: home_score, 9: away_score,
        # 10: ht_home, 11: ht_away, 12-13: red cards,
        # 14-15: extra, 16-17: yellow cards (quoted strings)
        state = _safe_int(parts[7])
        if state is None:
            return None

        if state not in FINISHED_STATES:
            return None

        match_id = _safe_int(parts[0])
        if not match_id:
            return None

        home_score = _safe_int(parts[8])
        away_score = _safe_int(parts[9])
        ht_home = _safe_int(parts[10])
        ht_away = _safe_int(parts[11])

        if home_score is None or away_score is None:
            return None

        total_goals = home_score + away_score

        ht_score = None
        if ht_home is not None and ht_away is not None:
            ht_score = f"{ht_home}-{ht_away}"

        ft_score = f"{home_score}-{away_score}"

        home_red = _safe_int(parts[12]) if len(parts) > 12 else 0
        away_red = _safe_int(parts[13]) if len(parts) > 13 else 0

        # Yellow cards at positions 16/17 (quoted strings on NowGoal)
        home_yellow = _safe_int(parts[16]) if len(parts) > 16 else None
        away_yellow = _safe_int(parts[17]) if len(parts) > 17 else None

        total_cards = None
        if home_yellow is not None and away_yellow is not None:
            # Total cards = yellow + red for both teams
            total_cards = (
                (home_yellow or 0)
                + (away_yellow or 0)
                + (home_red or 0)
                + (away_red or 0)
            )

        home_team = parts[4].strip() if len(parts) > 4 else ""
        away_team = parts[5].strip() if len(parts) > 5 else ""
        league_id = _safe_int(parts[1])

        return {
            "match_id": match_id,
            "league_id": league_id,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "ht_home_score": ht_home or 0,
            "ht_away_score": ht_away or 0,
            "ht_score": ht_score or "0-0",
            "ft_score": ft_score,
            "total_goals": total_goals,
            "total_corners": None,  # filled later from detail page
            "total_cards": total_cards,
            "home_red_cards": home_red or 0,
            "away_red_cards": away_red or 0,
        }

    except Exception as exc:
        logger.debug("[ResultResolver] Parse error for match array: %s", exc)
        return None


def _fetch_date_matches(target_date: str) -> List[Dict[str, Any]]:
    """
    Fetch and parse finished matches for a given date using the existing
    Eagle HTTP infrastructure.

    Uses the same NowGoal date endpoint as parsers.MatchDateParser, but only
    keeps finished matches and extracts score data.
    """
    import random
    from app_config import current_config

    # Build the NowGoal date URL (same pattern as config.py NOWGOAL_ENDPOINTS)
    endpoint_template = current_config.NOWGOAL_ENDPOINTS.get(
        "matches_by_date",
        "/ajax/SoccerAjax?type=6&date={date}&order=league&timezone=3&flesh={random}",
    )
    endpoint = endpoint_template.format(date=target_date, random=random.random())
    api_url = f"{current_config.PRIMARY_DATA_SOURCE}{endpoint}"

    logger.info("[ResultResolver] Fetching matches for %s from %s", target_date, api_url)

    # Use requests directly (bypasses Lambda which may fail with NoCredentialsError)
    import requests as _requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": current_config.PRIMARY_DATA_SOURCE + "/",
        }
        # Try primary source first, then fallbacks
        sources = [current_config.PRIMARY_DATA_SOURCE] + getattr(current_config, 'FALLBACK_DATA_SOURCES', [])
        raw_text = None
        for source in sources:
            try:
                url = f"{source}{endpoint}"
                resp = _requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200 and len(resp.text) > 100:
                    raw_text = resp.text
                    logger.info("[ResultResolver] Got %d bytes from %s", len(raw_text), source)
                    break
            except Exception as src_err:
                logger.debug("[ResultResolver] Source %s failed: %s", source, src_err)
                continue
    except Exception as exc:
        logger.error("[ResultResolver] Failed to fetch date data: %s", exc)
        return []

    if not raw_text:
        logger.warning("[ResultResolver] Empty response for %s", target_date)
        return []

    # The response is JSON with a "Data" field containing JS code with A[] arrays
    import json
    try:
        json_data = json.loads(raw_text)
        js_code = json_data.get("Data", "")
    except (json.JSONDecodeError, TypeError):
        # Might be raw JS directly
        js_code = raw_text

    if not js_code:
        logger.warning("[ResultResolver] No JS data in response for %s", target_date)
        return []

    # Parse all A[] arrays, keeping only finished matches
    finished: List[Dict[str, Any]] = []
    for m in RE_MATCH_ARRAY.finditer(js_code):
        result = _parse_match_from_array(m.group(2))
        if result is not None:
            finished.append(result)

    logger.info(
        "[ResultResolver] Found %d finished matches for %s",
        len(finished), target_date,
    )
    return finished


def _fetch_match_detail_stats(match_id: int) -> Dict[str, Optional[int]]:
    """
    Fetch technical stats (corners, cards) for a single finished match
    from NowGoal's detail endpoint.

    Returns dict with 'total_corners' and 'total_cards' keys
    (None if unavailable).
    """
    import random
    from app_config import current_config
    from http_client import get_http_session, get_request_headers, safe_get

    base_url = current_config.PRIMARY_DATA_SOURCE
    # Detail endpoint uses a different URL pattern
    # NowGoal detail.js format: /match/live-{match_id}
    # But the tech stats come from the h2h/analysis page
    # The simplest source is the odds/stats endpoint
    detail_url = f"{base_url}/match/h2h-{match_id}"

    result: Dict[str, Optional[int]] = {
        "total_corners": None,
        "total_cards": None,
    }

    try:
        session = get_http_session(base_url)
        headers = get_request_headers(base_url)
        timeout = (
            current_config.HTTP_TIMEOUT_CONNECT,
            current_config.HTTP_TIMEOUT_READ,
        )

        response = safe_get(session, detail_url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return result

        html = response.text

        # Look for tech stats in the page's JavaScript
        # NowGoal embeds tc[n]="home|away" where n is the stat ID
        corners_home = None
        corners_away = None
        cards_total = None

        for m in RE_TECH_STATS.finditer(html):
            stat_id = int(m.group(1))
            values = m.group(2).split("|")
            if len(values) < 2:
                continue

            if stat_id == STAT_ID_CORNERS:
                try:
                    corners_home = int(values[0])
                    corners_away = int(values[1])
                    result["total_corners"] = corners_home + corners_away
                except (ValueError, TypeError):
                    pass

        # Cards: parse from match event data or from the stats table
        # NowGoal shows yellow/red card counts in the match event stream
        # Look for card indicators in the HTML
        yellow_pattern = re.compile(
            r'class="[^"]*yellowcard[^"]*"[^>]*>.*?(\d+)',
            re.IGNORECASE | re.DOTALL,
        )
        red_pattern = re.compile(
            r'class="[^"]*redcard[^"]*"[^>]*>.*?(\d+)',
            re.IGNORECASE | re.DOTALL,
        )

        yellow_matches = yellow_pattern.findall(html)
        red_matches = red_pattern.findall(html)

        if yellow_matches or red_matches:
            total = 0
            for y in yellow_matches:
                try:
                    total += int(y)
                except ValueError:
                    pass
            for r in red_matches:
                try:
                    total += int(r)
                except ValueError:
                    pass
            if total > 0:
                result["total_cards"] = total

        return result

    except Exception as exc:
        logger.debug(
            "[ResultResolver] Detail fetch failed for match %d: %s", match_id, exc
        )
        return result


def _enrich_with_detail_stats(
    matches: List[Dict[str, Any]],
    max_workers: int = 5,
    timeout_seconds: int = 120,
) -> List[Dict[str, Any]]:
    """
    Enrich match results with corner/card stats from detail pages.

    Fetches detail pages concurrently, but limits concurrency to avoid
    rate-limiting from NowGoal.
    """
    if not matches:
        return matches

    # Only fetch details for matches that are missing corner/card data
    need_detail = [
        m for m in matches
        if m.get("total_corners") is None or m.get("total_cards") is None
    ]

    if not need_detail:
        return matches

    logger.info(
        "[ResultResolver] Enriching %d matches with detail stats (workers=%d)",
        len(need_detail), max_workers,
    )

    # Build lookup by match_id
    match_map = {m["match_id"]: m for m in matches}
    enriched_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {
            pool.submit(_fetch_match_detail_stats, m["match_id"]): m["match_id"]
            for m in need_detail
        }
        for future in as_completed(future_to_id, timeout=timeout_seconds):
            mid = future_to_id[future]
            try:
                stats = future.result()
                m = match_map.get(mid)
                if m and stats:
                    if stats.get("total_corners") is not None and m["total_corners"] is None:
                        m["total_corners"] = stats["total_corners"]
                        enriched_count += 1
                    if stats.get("total_cards") is not None and m["total_cards"] is None:
                        m["total_cards"] = stats["total_cards"]
            except Exception as exc:
                logger.debug(
                    "[ResultResolver] Detail enrichment failed for %d: %s", mid, exc
                )

    logger.info(
        "[ResultResolver] Enriched %d/%d matches with detail stats",
        enriched_count, len(need_detail),
    )
    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_match_results(
    target_date: str,
    *,
    enrich_details: bool = True,
    max_detail_workers: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetch finished match results for a given date.

    Args:
        target_date:        Date string in YYYY-MM-DD format.
        enrich_details:     If True (default), fetch detail pages for
                            corner and card statistics.  Set to False for
                            faster results when only score data is needed.
        max_detail_workers: Max concurrent workers for detail enrichment.

    Returns:
        List of dicts, each containing:
            match_id        int     NowGoal match identifier
            league_id       int     NowGoal league identifier
            home_team       str     Home team name
            away_team       str     Away team name
            home_score      int     Full-time home score
            away_score      int     Full-time away score
            ht_home_score   int     Half-time home score (0 if unavailable)
            ht_away_score   int     Half-time away score (0 if unavailable)
            ht_score        str     Half-time score string, e.g. "1-0"
            ft_score        str     Full-time score string, e.g. "2-1"
            total_goals     int     home_score + away_score
            total_corners   int|None  Total corners (None if unavailable)
            total_cards     int|None  Total cards (None if unavailable)
            home_red_cards  int     Home team red cards
            away_red_cards  int     Away team red cards

        Matches that cannot be resolved are silently skipped.
    """
    start_time = time.time()

    # Validate date format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        logger.error("[ResultResolver] Invalid date format: %s (expected YYYY-MM-DD)", target_date)
        return []

    # Step 1: Fetch finished match scores from date endpoint
    matches = _fetch_date_matches(target_date)
    if not matches:
        logger.info("[ResultResolver] No finished matches found for %s", target_date)
        return []

    # Step 2: Optionally enrich with detail stats (corners, cards)
    if enrich_details:
        matches = _enrich_with_detail_stats(
            matches, max_workers=max_detail_workers
        )

    elapsed = time.time() - start_time
    logger.info(
        "[ResultResolver] Resolved %d match results for %s in %.1fs",
        len(matches), target_date, elapsed,
    )
    return matches
