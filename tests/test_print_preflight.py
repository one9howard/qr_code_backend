"""
Tests for Print Preflight System.
"""
import pytest
from reportlab.lib.pagesizes import inch
from utils.print_preflight import validate_sign_layout, PreflightError, PreflightResult
from utils.pdf_generator import LayoutSpec

class MockLayout:
    def __init__(self, bleed=0.125*inch, margin=0.25*inch):
        self.bleed = bleed
        self.margin = margin

def test_validate_sign_layout_success():
    """Test that a valid layout passes validation."""
    layout = MockLayout()
    # 2.5 inch QR, 0.3 inch quiet zone
    result = validate_sign_layout(layout, "18x24", 2.5*inch, 0.3*inch)
    
    assert result.ok is True
    assert len(result.errors) == 0
    assert len(result.warnings) == 0

def test_validate_sign_layout_too_small_qr():
    """Test that QR code smaller than 2.0 inches fails."""
    layout = MockLayout()
    # 1.9 inch QR
    result = validate_sign_layout(layout, "18x24", 1.9*inch, 0.3*inch)
    
    assert result.ok is False
    assert any("QR code too small" in e for e in result.errors)

def test_validate_sign_layout_small_bleed():
    """Test that bleed smaller than 0.125 inches fails."""
    layout = MockLayout(bleed=0.1*inch)
    result = validate_sign_layout(layout, "18x24", 2.5*inch, 0.3*inch)
    
    assert result.ok is False
    assert any("Bleed too small" in e for e in result.errors)

def test_validate_sign_layout_warnings():
    """Test that QR between 2.0 and 2.5 inches emits a warning but passes."""
    layout = MockLayout()
    # 2.1 inch QR
    result = validate_sign_layout(layout, "18x24", 2.1*inch, 0.3*inch)
    
    assert result.ok is True
    assert len(result.errors) == 0
    assert len(result.warnings) > 0
    assert any("smaller than recommended" in w for w in result.warnings)
