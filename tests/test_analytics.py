
import pytest
from services.analytics import per_property_metrics, per_agent_rollup

def test_per_property_metrics_structure(app, mocker):
    """Verify keys and insight generation from mocked DB counts."""
    mock_db = mocker.Mock()
    mocker.patch('services.analytics.get_db', return_value=mock_db)
    
    # Mock return values for get_count calls
    # Sequence: 
    # Scans (curr, prev)
    # Views (curr, prev)
    # Leads (curr, prev)
    # CTAs (curr, prev)
    # Last Activity (Scan, View, Lead) - fetchone()[0] x 3
    
    # We must match the number of fetchone calls.
    # get_count calls: 4 pairs = 8 calls.
    # last timestamps: 3 calls.
    # Total 11 calls.
    
    # Let's mock side_effect to return specific values
    # Scenario: High traffic, zero leads -> Expect insight "Traffic without conversion"
    
    counts = [
        25, 10, # Scans (Curr=25, Prev=10) -> Delta +150%
        100, 80, # Views (Curr=100, Prev=80) 
        0, 0,    # Leads
        5, 2,    # CTAs
    ]
    timestamps = [None, None, None]
    
    # db.execute(...).fetchone()[0] pattern
    
    # Create a mock result object that returns the next value from our list
    class MockResult:
        def __init__(self, val): self.val = val
        def __getitem__(self, idx): return self.val
        
    results = [MockResult(c) for c in counts] + [MockResult(t) for t in timestamps]
    
    mock_db.execute.return_value.fetchone.side_effect = results

    metrics = per_property_metrics(1)
    
    assert metrics['scans']['total'] == 25
    assert metrics['scans']['delta'] == 150
    assert metrics['leads']['total'] == 0
    
    # Check Insights
    # Scans=25 (>5), Delta=150 (>20) -> "Momentum"
    # Traffic(125) > 20, Leads=0 -> "Traffic without conversion"
    # CTA(5) > 3, Leads=0 -> "Friction"
    
    assert any("Momentum" in i for i in metrics['insights'])
    assert any("Traffic without conversion" in i for i in metrics['insights'])
    assert any("Friction" in i for i in metrics['insights'])

def test_per_agent_rollup_structure(app, mocker):
    mock_db = mocker.Mock()
    mocker.patch('services.analytics.get_db', return_value=mock_db)
    
    # Mock agent ID lookup
    mock_db.execute.return_value.fetchone.side_effect = [
        {'id': 1}, # Agent ID
        (100,), # Scans Lifetime
        (500,), # Views Lifetime
        (10,), # Leads Lifetime
        (5,), # Leads 30d
        (20,), # CTA 7d (Moved up)
        (10,), # CTA Prev 7d (Moved up)
        (10,), # Scans 7d
        (5,),  # Scans Prev 7d
        (50,), # Views 7d
        (25,), # Views Prev
        (2,), # Leads 7d
        (1,), # Leads Prev 7d
    ]
    
    rollup = per_agent_rollup(1)
    
    assert rollup['scans']['lifetime'] == 100
    assert rollup['leads']['lifetime'] == 10
    assert rollup['ctas']['7d'] == 20
    assert rollup['ctas']['delta'] == 100 # (20-10)/10 * 100
