"""
Physical range checks and validation utilities for OSCAR Verify state.

Performs programmatic sanity checks on code execution output before
passing to the LLM-based verification.
"""

import re
from typing import Dict, List, Optional, Tuple


# Physical range definitions for Earth observation variables
PHYSICAL_RANGES = {
    "ndvi": (-1.0, 1.0),
    "ndwi": (-1.0, 1.0),
    "evi": (-1.0, 1.0),
    "savi": (-1.0, 1.0),
    "temperature_kelvin": (200.0, 350.0),
    "temperature_celsius": (-90.0, 60.0),
    "lst": (200.0, 350.0),  # Land Surface Temperature (K)
    "reflectance": (0.0, 1.0),
    "cloud_cover": (0.0, 100.0),
    "area_km2": (0.0, 1e9),  # no negative areas
    "precipitation_mm": (0.0, 1e4),
    "elevation_m": (-500.0, 9000.0),
}

# Patterns that indicate specific value types in stdout
VALUE_PATTERNS = {
    "ndvi": [
        r"[Nn][Dd][Vv][Ii][:\s=]+(-?[\d.]+)",
        r"ndvi.*?(-?[\d.]+)",
    ],
    "temperature_kelvin": [
        r"[Tt]emp(?:erature)?.*?[Kk].*?(\d+\.?\d*)",
        r"LST.*?(\d+\.?\d*)",
        r"(\d{3}\.?\d*)\s*[Kk](?:elvin)?",
    ],
    "temperature_celsius": [
        r"[Tt]emp(?:erature)?.*?[Cc].*?(-?\d+\.?\d*)",
        r"(-?\d+\.?\d*)\s*°?[Cc](?:elsius)?",
    ],
}


def extract_numeric_values(text: str) -> List[float]:
    """Extract all numeric values from text."""
    pattern = r"-?\d+\.?\d*(?:[eE][+-]?\d+)?"
    matches = re.findall(pattern, text)
    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue
    return values


def check_physical_ranges(exec_msg: str, code: str) -> Dict[str, any]:
    """
    Check if values in execution output are within physically plausible ranges.

    Returns a dict with:
      - 'passed': bool
      - 'checks': list of individual check results
      - 'summary': human-readable summary string
    """
    checks = []
    all_passed = True

    combined_text = (exec_msg or "") + "\n" + (code or "")
    combined_lower = combined_text.lower()

    for var_name, (lo, hi) in PHYSICAL_RANGES.items():
        # Only check if the variable is mentioned in the code or output
        if (
            var_name.replace("_", " ") not in combined_lower
            and var_name not in combined_lower
        ):
            continue

        if var_name in VALUE_PATTERNS:
            for pattern in VALUE_PATTERNS[var_name]:
                for match in re.finditer(pattern, exec_msg or "", re.IGNORECASE):
                    try:
                        val = float(match.group(1))
                    except (ValueError, IndexError):
                        continue
                    in_range = lo <= val <= hi
                    checks.append(
                        {
                            "variable": var_name,
                            "value": val,
                            "range": (lo, hi),
                            "in_range": in_range,
                            "source": match.group(0),
                        }
                    )
                    if not in_range:
                        all_passed = False

    # Check for explicit None / NaN in output
    none_nan_patterns = [
        r"\bNone\b",
        r"\bNaN\b",
        r"\bnan\b",
        r"\binf\b",
        r"\bInfinity\b",
    ]
    for pattern in none_nan_patterns:
        if re.search(pattern, exec_msg or ""):
            checks.append(
                {
                    "variable": "null_check",
                    "value": pattern,
                    "range": "not None/NaN",
                    "in_range": False,
                    "source": f"Found '{pattern}' in output",
                }
            )
            all_passed = False

    summary_parts = []
    for c in checks:
        status = "OK" if c["in_range"] else "FAIL"
        summary_parts.append(
            f"  [{status}] {c['variable']}: {c['value']} "
            f"(expected {c['range']}, source: '{c['source']}')"
        )

    if not checks:
        summary = "No physical range checks applicable."
    else:
        summary = "\n".join(summary_parts)

    return {
        "passed": all_passed,
        "checks": checks,
        "summary": summary,
    }


def check_execution_success(exec_returncode: int, exec_stderr: str) -> Dict[str, any]:
    """
    Check basic execution success indicators.

    Returns dict with:
      - 'success': bool (code ran without crashing)
      - 'timeout': bool
      - 'has_errors': bool
      - 'error_type': str or None
    """
    timeout = False
    has_errors = exec_returncode != 0
    error_type = None

    stderr_lower = (exec_stderr or "").lower()

    if "timed out" in stderr_lower or "timeout" in stderr_lower:
        timeout = True
        error_type = "timeout"
    elif "syntaxerror" in stderr_lower:
        error_type = "syntax_error"
    elif "nameerror" in stderr_lower:
        error_type = "name_error"
    elif "typeerror" in stderr_lower:
        error_type = "type_error"
    elif "attributeerror" in stderr_lower:
        error_type = "attribute_error"
    elif "indexerror" in stderr_lower:
        error_type = "index_error"
    elif "keyerror" in stderr_lower:
        error_type = "key_error"
    elif "httpserror" in stderr_lower or "ee.ee_exception" in stderr_lower:
        error_type = "gee_api_error"
    elif "computedobject" in stderr_lower:
        error_type = "gee_compute_error"
    elif has_errors:
        error_type = "unknown_error"

    return {
        "success": not has_errors,
        "timeout": timeout,
        "has_errors": has_errors,
        "error_type": error_type,
    }


def should_replan(
    exec_returncode: int, exec_stderr: str, exec_msg: str
) -> Tuple[bool, str]:
    """
    Determine if the execution result warrants a re-planning attempt.

    Returns:
      - (should_replan: bool, reason: str)

    Re-planning is appropriate for recoverable errors (wrong collection name,
    wrong band, timeout due to scale). It is NOT appropriate for
    fundamental issues like authentication failure.
    """
    stderr = exec_stderr or ""
    msg = exec_msg or ""
    stderr_lower = stderr.lower()

    # Non-recoverable errors — don't waste a re-plan attempt
    if "authentication" in stderr_lower or "credentials" in stderr_lower:
        return False, "Authentication error — not recoverable by re-planning."

    if exec_returncode == 0:
        # Code ran successfully — but check if it produced a recoverable answer
        # Must handle BOTH tagged (<answer>C1</answer>) and bare (C1, C1: Empty Collection) formats

        # Helper: check if an answer code appears in the output (tagged or bare)
        def _has_answer(code_str):
            """Check if the given answer code appears in stdout, in any format."""
            # Tagged: <answer>C1</answer>
            if f"<answer>{code_str}</answer>" in msg:
                return True
            # Check last few lines for bare answer (e.g., "C1", "C1: Empty Collection")
            for line in reversed(msg.strip().split("\n")[-5:]):
                line = line.strip()
                if line == code_str:
                    return True
                if line.startswith(code_str + ":") or line.startswith(code_str + " "):
                    return True
            return False

        # D: Code/API error — always replan
        if _has_answer("D"):
            return True, "Code self-reported a D (error) answer."

        # C1: Empty collection — recoverable by widening dates or switching sensors
        if _has_answer("C1"):
            return (
                True,
                "Code self-reported C1 (empty collection) — try fallback sensor or wider date range.",
            )

        # C2: No valid pixels — recoverable by relaxing cloud masking or increasing scale
        if _has_answer("C2"):
            return (
                True,
                "Code self-reported C2 (no valid pixels) — try relaxing masking or wider area.",
            )

        # C3: Calculation failure — may be recoverable with better null handling
        if _has_answer("C3"):
            return (
                True,
                "Code self-reported C3 (calculation failure) — try adding null guards.",
            )

        # Check for None/NaN in output even on success
        if re.search(r"\bNone\b|\bNaN\b", msg):
            return True, "Output contains None/NaN values — may need fix."

        # A or B — genuine success, no re-planning needed
        return False, "Execution succeeded with a valid answer."

    # Recoverable error patterns
    recoverable_patterns = [
        ("no such band", "Wrong band name — fixable."),
        ("collection not found", "Wrong collection ID — fixable."),
        ("no such collection", "Wrong collection ID — fixable."),
        ("is not defined", "Missing variable/import — fixable."),
        ("syntaxerror", "Syntax error — fixable."),
        ("indentationerror", "Indentation error — fixable."),
        ("nameerror", "Name error — fixable."),
        ("typeerror", "Type error — fixable."),
        ("attributeerror", "Attribute error — fixable."),
        ("indexerror", "Index error — fixable."),
        ("keyerror", "Key error — fixable."),
        ("timed out", "Timeout — try increasing scale or simplifying."),
        ("timeout", "Timeout — try increasing scale or simplifying."),
        ("computation timed out", "GEE computation timeout — increase scale."),
        ("too many pixels", "Too many pixels — increase scale or reduce area."),
        ("user memory limit exceeded", "Memory exceeded — simplify computation."),
    ]

    for pattern, reason in recoverable_patterns:
        if pattern in stderr_lower:
            return True, reason

    # Default: if there's a non-zero return code, try re-planning
    if exec_returncode != 0:
        return True, f"Non-zero return code ({exec_returncode}) — attempting re-plan."

    return False, "No re-planning needed."


def format_physical_validation(
    exec_msg: str, exec_stderr: str, exec_returncode: int, code: str
) -> str:
    """
    Produce a human-readable physical validation report for the Verify prompt.
    """
    exec_check = check_execution_success(exec_returncode, exec_stderr or "")
    range_check = check_physical_ranges(exec_msg or "", code or "")

    lines = []
    lines.append(f"Execution success: {exec_check['success']}")
    if exec_check["error_type"]:
        lines.append(f"Error type: {exec_check['error_type']}")
    if exec_check["timeout"]:
        lines.append("Timeout detected: yes")
    lines.append(f"Physical range checks passed: {range_check['passed']}")
    lines.append(f"Details:\n{range_check['summary']}")

    return "\n".join(lines)
