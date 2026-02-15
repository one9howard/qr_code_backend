
import pytest
from constants import PAID_STATUSES

def test_paid_statuses_completeness():
    """A1: PAID_STATUSES includes submitted_to_printer and fulfilled"""
    assert 'paid' in PAID_STATUSES
    assert 'submitted_to_printer' in PAID_STATUSES
    assert 'fulfilled' in PAID_STATUSES
