"""
Tactics Engine - Taktik eşleştirme ve analiz motoru
Maç verilerini taktiklerle karşılaştırır ve en uygun tahminleri üretir
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from .tactics_data import (
    KG_VAR_TACTICS, OVER_2_5_TACTICS, UNDER_2_5_TACTICS,
    MS1_TACTICS, MS2_TACTICS, MSX_TACTICS,
    HT_OVER_0_5_TACTICS, HT_1_TACTICS, HT_2_TACTICS, HT_X_TACTICS,
    OVER_1_5_TACTICS, OVER_3_5_TACTICS, HT_OVER_1_5_TACTICS,
    MS1_1_5_UST_TACTICS, MS2_1_5_UST_TACTICS,
    CIFT_1X_TACTICS, CIFT_X2_TACTICS, CIFT_12_TACTICS,
    FIELD_MAPPINGS
)

logger = logging.getLogger(__name__)


def get_nested_value(data: Dict, path: List[str]) -> Optional[float]:
    """
    Nested dictionary'den değer al
    
    Args:
        data: Ana veri dictionary'si
        path: Değere ulaşmak için path listesi
        
    Returns:
        float veya None
    """
    try:
        current = data
        for key in path:
            if current is None:
                return None
            current = current.get(key)
        return float(current) if current is not None else None
    except (KeyError, TypeError, ValueError):
        return None


def extract_match_features(analysis_data: Dict[str, Any]) -> Dict[str, float]:
    """
    API yanıtından taktik kontrolü için gerekli özellikleri çıkar
    
    Args:
        analysis_data: data.analysis içeriği
        
    Returns:
        dict: Alan adı -> değer eşleştirmeleri
    """
    features = {}
    
    for field_name, path in FIELD_MAPPINGS.items():
        value = get_nested_value(analysis_data, path)
        if value is not None:
            features[field_name] = value
    
    return features


def check_condition(features: Dict[str, float], condition: Tuple[str, str, float]) -> bool:
    """
    Tek bir koşulu kontrol et
    
    Args:
        features: Maç özellikleri
        condition: (alan_adı, operatör, değer) tuple'ı
        
    Returns:
        bool: Koşul sağlanıyor mu?
    """
    field, operator, threshold = condition
    
    # Alan yoksa koşul sağlanmaz
    if field not in features:
        return False
    
    value = features[field]
    
    # Operatöre göre karşılaştırma
    if operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == "==":
        return value == threshold
    else:
        return False


def match_tactic(features: Dict[str, float], tactic: Dict) -> bool:
    """
    Bir taktiğin tüm koşullarını kontrol et
    
    Args:
        features: Maç özellikleri
        tactic: Taktik dictionary'si
        
    Returns:
        bool: Tüm koşullar sağlanıyor mu?
    """
    for condition in tactic["conditions"]:
        if not check_condition(features, condition):
            return False
    return True


def find_best_tactic(features: Dict[str, float], tactics: List[Dict], 
                     min_samples: int = 20) -> Optional[Dict]:
    """
    En iyi eşleşen taktiği bul
    
    Öncelik sırası:
    1. En yüksek başarı oranı
    2. En fazla örnek sayısı
    
    Args:
        features: Maç özellikleri
        tactics: Taktik listesi
        min_samples: Minimum örnek sayısı
        
    Returns:
        dict veya None: En iyi taktik
    """
    matched_tactics = []
    
    # Eşleşen taktikleri bul
    for tactic in tactics:
        # Minimum örnek kontrolü
        if tactic["samples"] < min_samples:
            continue
            
        # Koşul kontrolü
        if match_tactic(features, tactic):
            matched_tactics.append(tactic)
    
    # Eşleşme yoksa
    if not matched_tactics:
        return None
    
    # En iyi taktiği seç (önce başarı oranı, sonra örnek sayısı)
    best_tactic = max(matched_tactics, key=lambda t: (t["success"], t["samples"]))
    
    return best_tactic


def calculate_confidence_stars(success_rate: float) -> int:
    """
    Başarı oranına göre güven yıldızı hesapla (1-5)
    
    Args:
        success_rate: Başarı oranı (%)
        
    Returns:
        int: 1-5 arası yıldız sayısı
    """
    if success_rate >= 90:
        return 5
    elif success_rate >= 85:
        return 4
    elif success_rate >= 80:
        return 3
    elif success_rate >= 70:
        return 2
    else:
        return 1


def generate_tip_from_tactic(tactic: Dict, prediction: str, tip_type: str) -> Dict:
    """
    Taktikten tip objesi oluştur
    
    Args:
        tactic: Eşleşen taktik
        prediction: Tahmin (örn: "KG VAR", "2.5 ÜST")
        tip_type: Tip tipi (örn: "kg", "alt_ust")
        
    Returns:
        dict: Tip objesi
    """
    return {
        "prediction": prediction,
        "confidence": calculate_confidence_stars(tactic["success"]),
        "success_rate": tactic["success"],
        "sample_size": tactic["samples"],
        "strategy": tactic["strategy"]
    }


def analyze_tactics(analysis_data: Dict[str, Any]) -> Dict:
    """
    Maç verileri için tüm taktikleri analiz et ve tip önerileri oluştur
    
    Args:
        analysis_data: data.analysis içeriği
        
    Returns:
        dict: Tips objesi
    """
    try:
        # Maç özelliklerini çıkar
        features = extract_match_features(analysis_data)
        
        if not features:
            logger.warning("No features extracted from match data")
            return create_empty_tips()
        
        tips = {}
        
        # KG VAR/YOK analizi
        kg_tactic = find_best_tactic(features, KG_VAR_TACTICS)
        if kg_tactic:
            tips["kg"] = generate_tip_from_tactic(kg_tactic, "KG VAR", "kg")
        else:
            tips["kg"] = None
        
        # ALT/ÜST analizi - Öncelik sırası ile
        # 1. 3.5 ÜST
        over_35_tactic = find_best_tactic(features, OVER_3_5_TACTICS)
        if over_35_tactic:
            tips["alt_ust"] = generate_tip_from_tactic(over_35_tactic, "3.5 ÜST", "alt_ust")
        else:
            # 2. 2.5 ÜST
            over_25_tactic = find_best_tactic(features, OVER_2_5_TACTICS)
            if over_25_tactic:
                tips["alt_ust"] = generate_tip_from_tactic(over_25_tactic, "2.5 ÜST", "alt_ust")
            else:
                # 3. 1.5 ÜST
                over_15_tactic = find_best_tactic(features, OVER_1_5_TACTICS)
                if over_15_tactic:
                    tips["alt_ust"] = generate_tip_from_tactic(over_15_tactic, "1.5 ÜST", "alt_ust")
                else:
                    # 4. 2.5 ALT
                    under_25_tactic = find_best_tactic(features, UNDER_2_5_TACTICS)
                    if under_25_tactic:
                        tips["alt_ust"] = generate_tip_from_tactic(under_25_tactic, "2.5 ALT", "alt_ust")
                    else:
                        tips["alt_ust"] = None

        # ALT/ÜST RISKY kontrolü - strategy alanını güncelle
        if tips["alt_ust"]:
            risky_status = validate_risky_alt_ust(tips["alt_ust"]["prediction"], features, analysis_data)
            if risky_status:
                tips["alt_ust"]["strategy"] = risky_status
        
        # MS (Maç Sonucu) analizi - Öncelik sırası ile
        # 1. Önce klasik MS tahminlerine bak
        ms1_tactic = find_best_tactic(features, MS1_TACTICS)
        ms2_tactic = find_best_tactic(features, MS2_TACTICS)
        msx_tactic = find_best_tactic(features, MSX_TACTICS)

        ms_tactics = []
        if ms1_tactic:
            ms_tactics.append((ms1_tactic, "MS1"))
        if ms2_tactic:
            ms_tactics.append((ms2_tactic, "MS2"))
        if msx_tactic:
            ms_tactics.append((msx_tactic, "MSX"))

        # 2. MS çıkmadıysa 1.5 ÜST tahminlerine bak
        if not ms_tactics:
            ms1_15_tactic = find_best_tactic(features, MS1_1_5_UST_TACTICS)
            ms2_15_tactic = find_best_tactic(features, MS2_1_5_UST_TACTICS)

            if ms1_15_tactic:
                ms_tactics.append((ms1_15_tactic, "Ev 1.5 ÜST"))
            if ms2_15_tactic:
                ms_tactics.append((ms2_15_tactic, "Dep 1.5 ÜST"))

        # 3. Onlar da yoksa çifte şanslara bak
        if not ms_tactics:
            cift_1x_tactic = find_best_tactic(features, CIFT_1X_TACTICS)
            cift_x2_tactic = find_best_tactic(features, CIFT_X2_TACTICS)
            cift_12_tactic = find_best_tactic(features, CIFT_12_TACTICS)

            if cift_1x_tactic:
                ms_tactics.append((cift_1x_tactic, "1X"))
            if cift_x2_tactic:
                ms_tactics.append((cift_x2_tactic, "X2"))
            if cift_12_tactic:
                ms_tactics.append((cift_12_tactic, "12"))

        # En iyi MS tahminini seç
        if ms_tactics:
            best_ms = max(ms_tactics, key=lambda x: (x[0]["success"], x[0]["samples"]))
            tips["ms"] = generate_tip_from_tactic(best_ms[0], best_ms[1], "ms")

            # RISKY kontrolü - strategy alanını güncelle
            risky_status = validate_risky_ms(best_ms[1], features)
            if risky_status:
                tips["ms"]["strategy"] = risky_status
        else:
            tips["ms"] = None
        
        # İY GOL analizi - Öncelik sırası ile
        # Önce İY 1.5 ÜST'e bak, yoksa İY 0.5 ÜST'e bak
        ht_goal_tactic = find_best_tactic(features, HT_OVER_1_5_TACTICS)
        if ht_goal_tactic:
            tips["iy_gol"] = generate_tip_from_tactic(ht_goal_tactic, "İY 1.5 ÜST", "iy_gol")
        else:
            ht_goal_tactic = find_best_tactic(features, HT_OVER_0_5_TACTICS)
            if ht_goal_tactic:
                tips["iy_gol"] = generate_tip_from_tactic(ht_goal_tactic, "İY 0.5 ÜST", "iy_gol")
            else:
                tips["iy_gol"] = None
        
        # İY (İlk Yarı Maç Sonucu) analizi
        ht1_tactic = find_best_tactic(features, HT_1_TACTICS)
        ht2_tactic = find_best_tactic(features, HT_2_TACTICS)
        htx_tactic = find_best_tactic(features, HT_X_TACTICS)
        
        # En iyi İY tahminini seç (3 seçenek arasında)
        ht_tactics = []
        if ht1_tactic:
            ht_tactics.append((ht1_tactic, "İY1"))
        if ht2_tactic:
            ht_tactics.append((ht2_tactic, "İY2"))
        if htx_tactic:
            ht_tactics.append((htx_tactic, "İYX"))
        
        if ht_tactics:
            best_ht = max(ht_tactics, key=lambda x: (x[0]["success"], x[0]["samples"]))
            tips["iy"] = generate_tip_from_tactic(best_ht[0], best_ht[1], "iy")

            # RISKY kontrolü - strategy alanını güncelle
            risky_status = validate_risky_iy(best_ht[1], features)
            if risky_status:
                tips["iy"]["strategy"] = risky_status
        else:
            tips["iy"] = None
        
        logger.info(f"Generated tips with {sum(1 for v in tips.values() if v)} successful matches")
        
        return tips
        
    except Exception as e:
        logger.error(f"Error analyzing tactics: {str(e)}", exc_info=True)
        return create_empty_tips()


def create_empty_tips() -> Dict:
    """Boş tips objesi oluştur"""
    return {
        "ms": None,
        "iy": None,
        "iy_gol": None,
        "alt_ust": None,
        "kg": None
    }


def validate_risky_ms(prediction: str, features: Dict[str, float]) -> Optional[str]:
    """
    MS tahminlerinde RISKY durumlarını kontrol et

    Kurallar (risky.txt):
    1. VERY RISKY: En yüksek MS yüzdesi bir tarafa ama tips başka tarafa
    2. RISKY: En yüksek yüzde ile ikinci yüzde arasındaki fark < 4.00
    3. VERY RISKY: MSX tahmini ama Ev/Deplasman > 40.0

    Args:
        prediction: Tahmin (MS1, MS2, MSX)
        features: Maç özellikleri

    Returns:
        "VERY RISKY", "RISKY" veya None
    """
    # MS yüzdelerini al (FIELD_MAPPINGS'de "home", "draw", "away" olarak tanımlı)
    ms_home = features.get("home", 0)
    ms_draw = features.get("draw", 0)
    ms_away = features.get("away", 0)

    # En yüksek ve ikinci yüksek yüzdeleri bul
    percentages = [
        ("home", ms_home),
        ("draw", ms_draw),
        ("away", ms_away)
    ]
    percentages_sorted = sorted(percentages, key=lambda x: x[1], reverse=True)
    highest_team, highest_pct = percentages_sorted[0]
    second_pct = percentages_sorted[1][1]

    # Kural 1: En yüksek yüzde ile tahmin uyuşmuyor mu?
    if highest_team == "home" and prediction not in ["MS1", "Ev 1.5 ÜST", "1X"]:
        return "VERY RISKY"
    elif highest_team == "away" and prediction not in ["MS2", "Dep 1.5 ÜST", "X2"]:
        return "VERY RISKY"
    elif highest_team == "draw" and prediction not in ["MSX", "1X", "X2"]:
        return "VERY RISKY"

    # Kural 2: En yüksek ile ikinci arasındaki fark < 4.00
    diff = highest_pct - second_pct
    if diff < 4.0:
        return "RISKY"

    # Kural 3: MSX tahmini ama Ev/Deplasman > 40.0
    if prediction == "MSX":
        if ms_home > 40.0 or ms_away > 40.0:
            return "VERY RISKY"

    return None


def validate_risky_iy(prediction: str, features: Dict[str, float]) -> Optional[str]:
    """
    İY tahminlerinde RISKY durumlarını kontrol et

    Aynı kurallar MS için geçerli (risky.txt)

    Args:
        prediction: Tahmin (İY1, İY2, İYX)
        features: Maç özellikleri

    Returns:
        "VERY RISKY", "RISKY" veya None
    """
    # İY yüzdelerini al (FIELD_MAPPINGS'de "ht_home", "ht_draw", "ht_away" olarak tanımlı)
    iy_home = features.get("ht_home", 0)
    iy_draw = features.get("ht_draw", 0)
    iy_away = features.get("ht_away", 0)

    # En yüksek ve ikinci yüksek yüzdeleri bul
    percentages = [
        ("home", iy_home),
        ("draw", iy_draw),
        ("away", iy_away)
    ]
    percentages_sorted = sorted(percentages, key=lambda x: x[1], reverse=True)
    highest_team, highest_pct = percentages_sorted[0]
    second_pct = percentages_sorted[1][1]

    # Kural 1: En yüksek yüzde ile tahmin uyuşmuyor mu?
    if highest_team == "home" and prediction != "İY1":
        return "VERY RISKY"
    elif highest_team == "away" and prediction != "İY2":
        return "VERY RISKY"
    elif highest_team == "draw" and prediction != "İYX":
        return "VERY RISKY"

    # Kural 2: En yüksek ile ikinci arasındaki fark < 4.00
    diff = highest_pct - second_pct
    if diff < 4.0:
        return "RISKY"

    # Kural 3: İYX tahmini ama Ev/Deplasman > 40.0
    if prediction == "İYX":
        if iy_home > 40.0 or iy_away > 40.0:
            return "VERY RISKY"

    return None


def validate_risky_alt_ust(prediction: str, features: Dict[str, float], analysis_data: Dict) -> Optional[str]:
    """
    Alt/Üst tahminlerinde RISKY durumlarını kontrol et

    Kural (risky.txt):
    - 2.5 ALT tahmini varsa
    - Kapanış goal line değeri > Prematch goal line (2.5)
    - O zaman RISKY

    Args:
        prediction: Tahmin (2.5 ALT, 2.5 ÜST, vb.)
        features: Maç özellikleri
        analysis_data: Tüm analiz verisi (odds için)

    Returns:
        "RISKY" veya None
    """
    # 2.5 ALT tahmini mi?
    if "2.5 ALT" not in prediction:
        return None

    # Odds analysis'den goal line bilgisini almaya çalış
    try:
        odds_analysis = analysis_data.get("odds_analysis", {})
        ou_analysis = odds_analysis.get("ou_analysis", {})

        # Prematch ve closing goal line değerleri
        prematch_line = ou_analysis.get("prematch_line", 2.5)
        closing_line = ou_analysis.get("closing_line", 2.5)

        # Kapanış > Prematch ise RISKY
        if closing_line > prematch_line:
            return "RISKY"

    except Exception as e:
        logger.warning(f"Could not validate alt/ust risky: {e}")

    return None


def get_tactic_summary(tips: Dict) -> str:
    """
    Tips özetini string olarak döndür (loglama için)

    Args:
        tips: Tips objesi

    Returns:
        str: Özet text
    """
    summary_parts = []

    for tip_type, tip_data in tips.items():
        if tip_data:
            stars = "⭐" * tip_data["confidence"]
            strategy = tip_data.get('strategy', '')
            summary_parts.append(
                f"{tip_type.upper()}: {tip_data['prediction']} "
                f"({tip_data['success_rate']:.1f}% {stars}) [{strategy}]"
            )

    return " | ".join(summary_parts) if summary_parts else "No tips generated"

