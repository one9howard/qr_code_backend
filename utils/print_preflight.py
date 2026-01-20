"""
Print Preflight Validation.
Enforces print-on-demand (POD) requirements for sign layouts.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
import os

from reportlab.lib.pagesizes import inch

@dataclass
class PreflightResult:
    ok: bool
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, float]

class PreflightError(Exception):
    """Raised when critical preflight checks fail."""
    def __init__(self, result: PreflightResult):
        self.result = result
        super().__init__(f"Preflight failed: {'; '.join(result.errors)}")

def validate_sign_layout(layout, sign_size: str, qr_size_pts: float, quiet_zone_pts: float) -> PreflightResult:
    """
    Validate a sign layout against POD production requirements.
    
    Args:
        layout: LayoutSpec object containing dimensions and font sizes
        sign_size: String key (e.g. '18x24')
        qr_size_pts: Actual computed size of the QR code in points
        quiet_zone_pts: Actual computed quiet zone in points
        
    Returns:
        PreflightResult: Validation status and messages
    """
    errors = []
    warnings = []
    metrics = {}
    
    # 1. Bleed Check (Critical)
    # Standard bleed is 0.125" (9 points)
    MIN_BLEED_PTS = 0.125 * inch
    if layout.bleed < MIN_BLEED_PTS - 0.1:  # small epsilon for float comparison
        errors.append(f"Bleed too small: {layout.bleed/inch:.3f}\" (min {MIN_BLEED_PTS/inch:.3f}\")")
    metrics['bleed_in'] = layout.bleed / inch
    
    # 2. Safe Margin Check (Critical)
    # Vital content must be inside safe zone (usually 0.25" INSIDE the trim line)
    MIN_MARGIN_PTS = 0.25 * inch
    if layout.margin < MIN_MARGIN_PTS - 0.1:
        errors.append(f"Safe margin too small: {layout.margin/inch:.3f}\" (min {MIN_MARGIN_PTS/inch:.3f}\")")
    metrics['margin_in'] = layout.margin / inch
    
    # 3. QR Code Size Check
    # Must be scanable from distance. Absolute minimum 2.0", preferred 2.5"+
    MIN_QR_PTS = 2.0 * inch
    WARN_QR_PTS = 2.5 * inch
    
    if qr_size_pts < MIN_QR_PTS - 0.1:
        errors.append(f"QR code too small: {qr_size_pts/inch:.2f}\" (min 2.0\")")
    elif qr_size_pts < WARN_QR_PTS - 0.1:
        warnings.append(f"QR code smaller than recommended: {qr_size_pts/inch:.2f}\" (preferred 2.5\"+)")
    
    metrics['qr_size_in'] = qr_size_pts / inch
    
    # 4. Quiet Zone Check
    # Must be at least 4 modules or 0.25", whichever is larger.
    # We enforce 0.25" minimum for print safety.
    MIN_QUIET_PTS = 0.25 * inch
    if quiet_zone_pts < MIN_QUIET_PTS - 0.1:
        errors.append(f"QR quiet zone too small: {quiet_zone_pts/inch:.3f}\" (min 0.25\")")
    metrics['quiet_zone_in'] = quiet_zone_pts / inch
    
    return PreflightResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metrics=metrics
    )
