"""
Tips Module - Match Prediction Tips
Provides prediction tips for various betting markets based on tactical analysis
"""

import logging
from typing import Dict, Any
from .tactics import analyze_tactics, get_tactic_summary

logger = logging.getLogger(__name__)


def generate_betting_tips(data: Dict[str, Any]) -> Dict:
    """
    Generate betting tips for various markets based on analysis data.
    Uses tactical analysis engine to match match data with proven tactics.
    
    Args:
        data: Complete match data including analysis results
        
    Returns:
        dict: Betting tips structure with predictions and confidence levels
        
    Example:
        {
            "tips": {
                "kg": {
                    "prediction": "KG VAR",
                    "confidence": 4,  # 1-5 stars
                    "success_rate": 85.0,
                    "sample_size": 173,
                    "strategy": "AGRESIF"
                },
                "alt_ust": {...},
                "ms": {...},
                "iy": {...},
                "iy_gol": {...}
            }
        }
    """
    try:
        # Analysis verisini al
        analysis_data = data.get("analysis", {})
        
        if not analysis_data:
            logger.warning("No analysis data available for tips generation")
            return create_empty_tips_response()
        
        # Taktik motorunu çalıştır
        tips = analyze_tactics(analysis_data)
        
        # Özet log
        summary = get_tactic_summary(tips)
        logger.info(f"Generated tips: {summary}")
        
        return {"tips": tips}
        
    except Exception as e:
        logger.error(f"Error generating betting tips: {str(e)}", exc_info=True)
        return create_empty_tips_response()


def create_empty_tips_response() -> Dict:
    """Create empty tips response structure"""
    return {
        "tips": {
            "ms": None,      # Maç Sonucu (1, X, 2)
            "iy": None,      # İlk Yarı (1, X, 2)
            "iy_gol": None,  # İlk Yarı Gol (Var/Yok veya Alt/Üst)
            "alt_ust": None, # Alt/Üst (2.5, 3.5, etc.)
            "kg": None       # Karşılıklı Gol (Var/Yok)
        }
    }

