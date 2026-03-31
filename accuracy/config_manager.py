"""
Config Manager — reads and writes tunable parameters from algorithm Python files.

Each Eagle algorithm file contains hardcoded constants (e.g. ``HOME_CORNER_SHARE = 0.55``).
This module provides safe read/write access to those constants so that the AutoTuner can
adjust parameters without manual file editing.

Safety features:
    - Timestamped backup before every write
    - Regex-based in-place replacement (preserves file structure)
    - Validation of parameter bounds
    - Rollback support via backup files

Environment:
    ``EAGLE_ANALYSIS_DIR`` — path to the ``analysis/`` directory.
    Defaults to ``/app/analysis/`` (Docker container layout).
"""

import ast
import logging
import os
import re
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANALYSIS_DIR = os.getenv("EAGLE_ANALYSIS_DIR", "/app/analysis/")

# Algorithm name -> file path (relative to ANALYSIS_DIR)
ALGORITHM_FILE_MAP: Dict[str, str] = {
    "card_predictions": "card_predictions.py",
    "correct_score_enhanced": "correct_score_enhanced.py",
    "handicap_predictions": "handicap_predictions.py",
    "first_half_predictions": "first_half_predictions.py",
    "second_half_predictions": "second_half_predictions.py",
    "half_btts_predictions": "half_btts_predictions.py",
    "corner_predictions": "corner_predictions.py",
    "poisson_model": "poisson_model.py",
    "odds_movement": "odds_movement.py",
    "final_predictions": "final_predictions.py",
}

# Tunable parameters per algorithm.
# Each entry: parameter_name -> {type, default, min, max, description}
TUNABLE_PARAMS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "card_predictions": {
        "DEFAULT_CARD_AVERAGE": {
            "type": "dict",
            "keys": ["avg_cards", "avg_yellow", "avg_red"],
            "default": {"avg_cards": 4.5, "avg_yellow": 4.1, "avg_red": 0.16},
            "description": "Default card average for unknown leagues",
        },
    },
    "correct_score_enhanced": {
        "DEFAULT_RHO": {
            "type": "float",
            "default": -0.13,
            "min": -0.25,
            "max": 0.05,
            "description": "Dixon-Coles rho correction for low-score correlation",
        },
    },
    "handicap_predictions": {
        "KELLY_FRACTION": {
            "type": "float",
            "default": 0.25,
            "min": 0.05,
            "max": 0.50,
            "description": "Fractional Kelly criterion for bet sizing",
            "pattern_type": "function_default",
        },
    },
    "first_half_predictions": {
        "FIRST_HALF_SHARE": {
            "type": "float",
            "default": 0.42,
            "min": 0.30,
            "max": 0.55,
            "description": "Share of total goals scored in first half",
        },
    },
    "second_half_predictions": {
        "SECOND_HALF_SHARE": {
            "type": "float",
            "default": 0.58,
            "min": 0.45,
            "max": 0.70,
            "description": "Share of total goals scored in second half",
        },
    },
    "corner_predictions": {
        "HOME_CORNER_SHARE": {
            "type": "float",
            "default": 0.55,
            "min": 0.45,
            "max": 0.65,
            "description": "Home team share of total corners",
        },
        "DEFAULT_CORNER_AVG": {
            "type": "float",
            "default": 10.0,
            "min": 8.0,
            "max": 13.0,
            "description": "Default corners per match for unknown leagues",
        },
    },
    "poisson_model": {
        # The league_avg is used inline: e.g. `league_avg = 1.3`
        # Not a top-level constant — skipped for now.
    },
    "odds_movement": {
        # No simple top-level tunable constants.
    },
    "final_predictions": {
        # Source weights are inline in calculate_*_final functions.
        # Complex to tune via regex — reserved for future.
    },
}

# Pattern for function default argument: `fraction: float = 0.25`
RE_FUNC_DEFAULT = re.compile(
    r"(fraction:\s*float\s*=\s*)([\d.]+)",
)


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

def get_algorithm_file_path(algorithm: str) -> str:
    """
    Map algorithm name to its absolute file path.

    Args:
        algorithm: Algorithm identifier (e.g. ``"corner_predictions"``).

    Returns:
        Absolute path to the Python file.

    Raises:
        ValueError: If the algorithm name is unknown.
    """
    filename = ALGORITHM_FILE_MAP.get(algorithm)
    if not filename:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    return os.path.join(ANALYSIS_DIR, filename)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _parse_simple_value(raw: str) -> Any:
    """
    Parse a Python literal from a raw string extracted via regex.

    Uses ``ast.literal_eval`` which is safe — it only evaluates literals
    (strings, numbers, tuples, lists, dicts, booleans, None) and does NOT
    execute arbitrary code.  This is the standard Python approach for
    safely parsing literal values.
    """
    raw = raw.strip()

    # ast.literal_eval handles all safe Python literals:
    # int, float, str, bytes, list, tuple, dict, set, bool, None
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        pass

    # If literal_eval fails, return the raw string stripped of quotes
    if (raw.startswith("'") and raw.endswith("'")) or (
        raw.startswith('"') and raw.endswith('"')
    ):
        return raw[1:-1]

    return raw


def read_algorithm_params(algorithm: str) -> Dict[str, Any]:
    """
    Read current tunable parameters from an algorithm's Python file.

    Args:
        algorithm: Algorithm identifier.

    Returns:
        Dict mapping parameter name to its current value.
        Returns empty dict if the file or algorithm is not found.
    """
    param_defs = TUNABLE_PARAMS.get(algorithm, {})
    if not param_defs:
        logger.debug("[ConfigMgr] No tunable params defined for %s", algorithm)
        return {}

    try:
        filepath = get_algorithm_file_path(algorithm)
    except ValueError:
        return {}

    if not os.path.exists(filepath):
        logger.warning("[ConfigMgr] File not found: %s", filepath)
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as exc:
        logger.error("[ConfigMgr] Cannot read %s: %s", filepath, exc)
        return {}

    params: Dict[str, Any] = {}

    for param_name, meta in param_defs.items():
        ptype = meta.get("type", "float")
        pattern_type = meta.get("pattern_type", "assignment")

        if pattern_type == "function_default":
            # Special: extract default from function signature
            match = RE_FUNC_DEFAULT.search(content)
            if match:
                params[param_name] = _parse_simple_value(match.group(2))
            else:
                params[param_name] = meta.get("default")
            continue

        # Standard top-level assignment
        if ptype == "dict":
            pattern = re.compile(
                r"^(\s*)" + re.escape(param_name) + r"\s*=\s*(\{[^}]*\})",
                re.MULTILINE,
            )
        else:
            pattern = re.compile(
                r"^(\s*)" + re.escape(param_name) + r"\s*=\s*([^\n#]+)",
                re.MULTILINE,
            )

        match = pattern.search(content)
        if match:
            raw_value = match.group(2).strip()
            params[param_name] = _parse_simple_value(raw_value)
        else:
            params[param_name] = meta.get("default")
            logger.debug(
                "[ConfigMgr] Param %s not found in %s, using default",
                param_name, filepath,
            )

    return params


def get_all_tunable_params() -> Dict[str, Dict[str, Any]]:
    """
    Read all tunable parameters for all algorithms.

    Returns:
        Dict mapping algorithm name to its current parameter values::

            {
                "corner_predictions": {"HOME_CORNER_SHARE": 0.55, ...},
                "first_half_predictions": {"FIRST_HALF_SHARE": 0.42},
                ...
            }
    """
    result: Dict[str, Dict[str, Any]] = {}

    for algorithm in TUNABLE_PARAMS:
        params = read_algorithm_params(algorithm)
        if params:
            result[algorithm] = params

    return result


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _create_backup(filepath: str) -> str:
    """
    Create a timestamped backup of a file.

    Returns:
        Path to the backup file.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.bak.{timestamp}"
    shutil.copy2(filepath, backup_path)
    logger.info("[ConfigMgr] Backup created: %s", backup_path)
    return backup_path


def _format_value(value: Any, ptype: str) -> str:
    """
    Format a Python value as a string suitable for writing to a .py file.
    """
    if ptype == "dict" and isinstance(value, dict):
        items = ", ".join(
            f"'{k}': {v}" if isinstance(v, (int, float)) else f"'{k}': '{v}'"
            for k, v in value.items()
        )
        return "{" + items + "}"

    if ptype == "list" and isinstance(value, list):
        return str(value)

    if isinstance(value, float):
        return str(value)

    if isinstance(value, int):
        return str(value)

    if isinstance(value, bool):
        return "True" if value else "False"

    return repr(value)


def write_algorithm_params(algorithm: str, params: Dict[str, Any]) -> bool:
    """
    Write updated parameters to an algorithm's Python file.

    Creates a timestamped backup before modifying the file.  Each parameter
    is replaced in-place using regex, preserving the file's structure and
    comments.

    Args:
        algorithm: Algorithm identifier.
        params:    Dict mapping parameter name to its new value.

    Returns:
        True if all parameters were written successfully, False otherwise.
    """
    param_defs = TUNABLE_PARAMS.get(algorithm, {})
    if not param_defs:
        logger.warning("[ConfigMgr] No tunable params for %s", algorithm)
        return False

    try:
        filepath = get_algorithm_file_path(algorithm)
    except ValueError as exc:
        logger.error("[ConfigMgr] %s", exc)
        return False

    if not os.path.exists(filepath):
        logger.error("[ConfigMgr] File not found: %s", filepath)
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as exc:
        logger.error("[ConfigMgr] Cannot read %s: %s", filepath, exc)
        return False

    # Create backup
    try:
        backup_path = _create_backup(filepath)
    except IOError as exc:
        logger.error("[ConfigMgr] Backup failed for %s: %s", filepath, exc)
        return False

    modified = content
    changes_made = 0

    for param_name, new_value in params.items():
        meta = param_defs.get(param_name)
        if not meta:
            logger.warning(
                "[ConfigMgr] Param %s not in tunable list for %s",
                param_name, algorithm,
            )
            continue

        ptype = meta.get("type", "float")
        pattern_type = meta.get("pattern_type", "assignment")

        # Validate bounds for numeric types
        if ptype == "float" and isinstance(new_value, (int, float)):
            param_min = meta.get("min")
            param_max = meta.get("max")
            if param_min is not None and new_value < param_min:
                logger.warning(
                    "[ConfigMgr] %s=%s below min=%s, clamping",
                    param_name, new_value, param_min,
                )
                new_value = param_min
            if param_max is not None and new_value > param_max:
                logger.warning(
                    "[ConfigMgr] %s=%s above max=%s, clamping",
                    param_name, new_value, param_max,
                )
                new_value = param_max

        formatted = _format_value(new_value, ptype)

        if pattern_type == "function_default":
            new_modified = RE_FUNC_DEFAULT.sub(
                rf"\g<1>{formatted}",
                modified,
                count=1,
            )
            if new_modified != modified:
                modified = new_modified
                changes_made += 1
                logger.info(
                    "[ConfigMgr] Updated %s.%s -> %s (function default)",
                    algorithm, param_name, formatted,
                )
            else:
                logger.warning(
                    "[ConfigMgr] Could not find function default for %s in %s",
                    param_name, algorithm,
                )
            continue

        # Standard assignment replacement
        if ptype == "dict":
            pattern = re.compile(
                r"^(\s*)" + re.escape(param_name) + r"\s*=\s*\{[^}]*\}",
                re.MULTILINE,
            )
        else:
            pattern = re.compile(
                r"^(\s*)" + re.escape(param_name) + r"\s*=\s*[^\n#]+",
                re.MULTILINE,
            )

        replacement = rf"\g<1>{param_name} = {formatted}"
        new_modified, count = pattern.subn(replacement, modified, count=1)
        if count > 0:
            modified = new_modified
            changes_made += 1
            logger.info(
                "[ConfigMgr] Updated %s.%s -> %s",
                algorithm, param_name, formatted,
            )
        else:
            logger.warning(
                "[ConfigMgr] Pattern not found for %s in %s",
                param_name, filepath,
            )

    if changes_made == 0:
        logger.info("[ConfigMgr] No changes applied for %s", algorithm)
        try:
            os.remove(backup_path)
        except OSError:
            pass
        return False

    # Write the modified content
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(modified)
        logger.info(
            "[ConfigMgr] Wrote %d parameter changes to %s (backup: %s)",
            changes_made, filepath, backup_path,
        )
        return True
    except IOError as exc:
        logger.error(
            "[ConfigMgr] Write failed for %s: %s -- restoring backup",
            filepath, exc,
        )
        try:
            shutil.copy2(backup_path, filepath)
            logger.info("[ConfigMgr] Restored %s from backup", filepath)
        except IOError as restore_exc:
            logger.critical(
                "[ConfigMgr] CRITICAL: Could not restore %s: %s",
                filepath, restore_exc,
            )
        return False


def rollback_algorithm(algorithm: str, backup_path: str) -> bool:
    """
    Rollback an algorithm file to a previous backup.

    Args:
        algorithm:   Algorithm identifier.
        backup_path: Full path to the backup file.

    Returns:
        True if rollback succeeded.
    """
    try:
        filepath = get_algorithm_file_path(algorithm)
    except ValueError as exc:
        logger.error("[ConfigMgr] %s", exc)
        return False

    if not os.path.exists(backup_path):
        logger.error("[ConfigMgr] Backup not found: %s", backup_path)
        return False

    try:
        shutil.copy2(backup_path, filepath)
        logger.info(
            "[ConfigMgr] Rolled back %s from %s", filepath, backup_path,
        )
        return True
    except IOError as exc:
        logger.error("[ConfigMgr] Rollback failed: %s", exc)
        return False


def list_backups(algorithm: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    List available backup files for an algorithm, most recent first.

    Args:
        algorithm: Algorithm identifier.
        limit:     Maximum number of backups to return.

    Returns:
        List of dicts with ``path``, ``timestamp``, and ``size`` keys.
    """
    try:
        filepath = get_algorithm_file_path(algorithm)
    except ValueError:
        return []

    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    prefix = f"{basename}.bak."

    backups = []
    try:
        for name in os.listdir(directory):
            if name.startswith(prefix):
                full_path = os.path.join(directory, name)
                timestamp_str = name[len(prefix):]
                try:
                    ts = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                except ValueError:
                    ts = None
                backups.append({
                    "path": full_path,
                    "timestamp": ts.isoformat() if ts else timestamp_str,
                    "size": os.path.getsize(full_path),
                })
    except OSError:
        return []

    backups.sort(key=lambda b: b["timestamp"], reverse=True)
    return backups[:limit]
