"""
Eagle Combiner - Ensemble prediction strategy
Combines predictions from multiple sources using weighted voting and confidence scoring.
"""
import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

from eagle.config import EagleConfig

logger = logging.getLogger(__name__)

# Canonical pick normalization map
PICK_NORMALIZE = {
    "ms1": "1", "1": "1", "home": "1", "ev": "1",
    "msx": "X", "x": "X", "draw": "X", "berabere": "X",
    "ms2": "2", "2": "2", "away": "2", "dep": "2",
    "üst 2.5": "Üst", "over 2.5": "Üst", "üst 3.5": "Üst", "over 3.5": "Üst",
    "alt 2.5": "Alt", "under 2.5": "Alt", "alt 3.5": "Alt", "under 3.5": "Alt",
    "üst": "Üst", "over": "Üst", "alt": "Alt", "under": "Alt",
    "var": "Var", "yes": "Var", "evet": "Var", "kg var": "Var",
    "yok": "Yok", "no": "Yok", "hayir": "Yok", "kg yok": "Yok",
    "iy 1": "İY 1", "iy x": "İY X", "iy 2": "İY 2",
    "iy üst 0.5": "İY Üst", "iy alt 0.5": "İY Alt",
}


def normalize_pick(pick: str) -> str:
    """Normalize a prediction pick to canonical form."""
    if not pick:
        return ""
    lower = pick.strip().lower()
    return PICK_NORMALIZE.get(lower, pick.strip())


def get_pick_direction(pick: str, market: str) -> str:
    """Get the direction of a pick (for grouping same-direction picks)."""
    norm = normalize_pick(pick)
    if market == "ms":
        return norm  # 1, X, 2
    if market in ("over25", "over35", "ht_over05"):
        if "üst" in norm.lower() or "over" in norm.lower():
            return "Üst"
        return "Alt"
    if market == "btts":
        if norm in ("Var", "Yes"):
            return "Var"
        return "Yok"
    if market == "ht_result":
        if "1" in norm:
            return "İY 1"
        if "2" in norm:
            return "İY 2"
        return "İY X"
    return norm


def combine_predictions(
    source_predictions: Dict[str, List[Tuple[str, str, Optional[float]]]],
    market: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Combine predictions from multiple sources for all markets (or a specific market).

    Args:
        source_predictions: {source_name: [(market, pick, confidence), ...]}
        market: If set, only combine for this specific market

    Returns:
        Dict of market -> {
            sources: {source: {pick, confidence, direction}},
            eagle_pick: str,
            eagle_confidence: float,
            agreement: int,
            total_sources: int,
            details: {...}
        }
    """
    # Group predictions by market
    market_preds: Dict[str, Dict[str, Tuple[str, Optional[float]]]] = {}

    for source_name, preds in source_predictions.items():
        for mkt, pick, conf in preds:
            if market and mkt != market:
                continue
            if mkt not in market_preds:
                market_preds[mkt] = {}
            market_preds[mkt][source_name] = (pick, conf)

    results = {}
    for mkt, sources in market_preds.items():
        results[mkt] = _combine_single_market(mkt, sources)

    return results


def _combine_single_market(
    market: str,
    sources: Dict[str, Tuple[str, Optional[float]]],
) -> Dict[str, Any]:
    """Combine predictions for a single market from multiple sources."""
    # Get market-specific weights
    weights_cfg = EagleConfig.MARKET_WEIGHTS.get(market, EagleConfig.SOURCE_WEIGHTS)

    # Normalize weights for available sources only
    available_sources = set(sources.keys())
    total_weight = sum(weights_cfg.get(s, 0.1) for s in available_sources)
    if total_weight == 0:
        total_weight = len(available_sources)  # equal weights fallback

    weights = {}
    for s in available_sources:
        weights[s] = weights_cfg.get(s, 0.1) / total_weight

    # Group by direction (normalized pick)
    direction_votes: Dict[str, Dict] = {}  # direction -> {weight, confidences, sources, raw_pick}

    source_details = {}
    for source_name, (pick, conf) in sources.items():
        direction = get_pick_direction(pick, market)
        source_details[source_name] = {
            "pick": pick,
            "confidence": conf,
            "direction": direction,
            "weight": round(weights.get(source_name, 0), 3),
        }

        if direction not in direction_votes:
            direction_votes[direction] = {
                "total_weight": 0.0,
                "confidences": [],
                "sources": [],
                "raw_pick": pick,
            }

        w = weights.get(source_name, 0)
        direction_votes[direction]["total_weight"] += w
        if conf is not None and conf > 0:
            direction_votes[direction]["confidences"].append(conf)
        direction_votes[direction]["sources"].append(source_name)

    if not direction_votes:
        return _empty_market_result()

    # Find winning direction (highest total weight)
    best_direction = max(direction_votes, key=lambda d: direction_votes[d]["total_weight"])
    best_info = direction_votes[best_direction]

    # Calculate agreement
    agreement = len(best_info["sources"])
    total_sources = len(sources)

    # Calculate Eagle confidence
    eagle_confidence = _calculate_eagle_confidence(
        best_info["confidences"],
        best_info["total_weight"],
        agreement,
        total_sources,
    )

    # Build the display pick
    eagle_pick = _build_eagle_pick(market, best_direction, best_info["raw_pick"])

    return {
        "sources": source_details,
        "eagle_pick": eagle_pick,
        "eagle_confidence": round(eagle_confidence, 1),
        "agreement": agreement,
        "total_sources": total_sources,
        "winning_direction": best_direction,
        "weight_score": round(best_info["total_weight"], 3),
        "all_directions": {
            d: {
                "weight": round(v["total_weight"], 3),
                "sources": v["sources"],
                "avg_confidence": round(
                    sum(v["confidences"]) / len(v["confidences"]), 1
                ) if v["confidences"] else None,
            }
            for d, v in direction_votes.items()
        },
    }


def _calculate_eagle_confidence(
    confidences: List[float],
    weight_score: float,
    agreement: int,
    total_sources: int,
) -> float:
    """
    Calculate Eagle confidence score based on:
    1. Average source confidence (40%)
    2. Weight score / agreement ratio (30%)
    3. Source agreement bonus (30%)
    """
    # 1. Average confidence from sources
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
    else:
        avg_conf = 55.0  # default when no confidence data

    # 2. Weight-based score (how much of total weight agrees)
    weight_pct = weight_score * 100  # already normalized 0-1

    # 3. Agreement bonus
    if total_sources == 0:
        agree_score = 50.0
    else:
        agree_ratio = agreement / total_sources
        if agree_ratio >= 1.0:
            agree_score = 95.0
        elif agree_ratio >= 0.75:
            agree_score = 85.0
        elif agree_ratio >= 0.5:
            agree_score = 70.0
        else:
            agree_score = 50.0

    # Weighted combination
    eagle = (avg_conf * 0.40) + (weight_pct * 0.30) + (agree_score * 0.30)

    # Clamp to 0-100
    return max(0, min(100, eagle))


def _build_eagle_pick(market: str, direction: str, raw_pick: str) -> str:
    """Build a clean display pick for Eagle."""
    if market == "ms":
        return direction  # "1", "X", "2"
    if market == "over25":
        return f"{direction} 2.5"
    if market == "over35":
        return f"{direction} 3.5"
    if market == "btts":
        return f"KG {direction}"
    if market == "ht_result":
        return direction
    if market == "ht_over05":
        return f"İY {direction} 0.5"
    if market == "corner":
        return raw_pick  # Corner picks have line info
    return direction


def _empty_market_result() -> Dict[str, Any]:
    return {
        "sources": {},
        "eagle_pick": None,
        "eagle_confidence": 0,
        "agreement": 0,
        "total_sources": 0,
        "winning_direction": None,
        "weight_score": 0,
        "all_directions": {},
    }


def calculate_best_market(markets: Dict[str, Dict]) -> Optional[str]:
    """Find the best market to bet on (highest confidence + agreement combo)."""
    best_market = None
    best_score = 0

    for mkt, data in markets.items():
        if not data.get("eagle_pick"):
            continue
        conf = data.get("eagle_confidence", 0)
        agr = data.get("agreement", 0)
        total = data.get("total_sources", 1)

        # Score = confidence * agreement_ratio * bonus
        score = conf * (agr / max(total, 1))

        # Bonus for high agreement
        if agr >= 3:
            score *= 1.2
        elif agr >= 2:
            score *= 1.1

        if score > best_score:
            best_score = score
            best_market = mkt

    return best_market


def build_eagle_summary(markets: Dict[str, Dict], match_info: Dict) -> Dict[str, Any]:
    """Build a complete Eagle prediction summary for a match."""
    best_market = calculate_best_market(markets)

    # Calculate overall Eagle confidence (average of all markets)
    market_confs = [m["eagle_confidence"] for m in markets.values() if m.get("eagle_confidence", 0) > 0]
    overall_confidence = round(sum(market_confs) / len(market_confs), 1) if market_confs else 0

    # Determine max agreement
    max_agreement = max((m.get("agreement", 0) for m in markets.values()), default=0)

    # Build BANKO indicator
    is_banko = False
    banko_market = None
    banko_pick = None

    for mkt in ["over35", "over25", "ms", "btts"]:
        if mkt not in markets:
            continue
        m = markets[mkt]
        if m.get("agreement", 0) >= 3 and m.get("eagle_confidence", 0) >= 75:
            is_banko = True
            banko_market = mkt
            banko_pick = m["eagle_pick"]
            break
        if m.get("agreement", 0) >= 2 and m.get("eagle_confidence", 0) >= 80:
            is_banko = True
            banko_market = mkt
            banko_pick = m["eagle_pick"]
            break

    return {
        "match": match_info,
        "predictions": markets,
        "best_market": best_market,
        "best_pick": markets[best_market]["eagle_pick"] if best_market and best_market in markets else None,
        "best_confidence": markets[best_market]["eagle_confidence"] if best_market and best_market in markets else 0,
        "overall_confidence": overall_confidence,
        "max_agreement": max_agreement,
        "is_banko": is_banko,
        "banko": {
            "market": banko_market,
            "pick": banko_pick,
        } if is_banko else None,
        "source_status": _get_source_status(markets),
    }


def _get_source_status(markets: Dict[str, Dict]) -> Dict[str, bool]:
    """Check which sources provided data."""
    found = set()
    for mkt_data in markets.values():
        for src in mkt_data.get("sources", {}):
            found.add(src)
    return {
        "falcon": "falcon" in found,
        "predator": "predator" in found,
        "predator_v2": "predator_v2" in found,
        "bee": "bee" in found,
    }
