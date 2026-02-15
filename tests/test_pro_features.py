from routes.dashboard import FREE_LEAD_LIMIT
from services.analytics import per_agent_rollup


def test_free_lead_limit_constant():
    """Free plan lead cap should stay at the documented value."""
    assert FREE_LEAD_LIMIT == 2


def test_csv_export_requires_authentication(client):
    """Anonymous users should not get CSV lead export data."""
    response = client.get("/api/leads/export.csv")
    assert response.status_code in {401, 302}, (
        f"Expected auth gate for CSV export, got status={response.status_code}"
    )


def test_analytics_rollup_empty_for_unknown_user(app):
    """Analytics service should be safe for unknown users and return empty rollup."""
    with app.app_context():
        result = per_agent_rollup(99999)
    assert result == {}
