"""
Analytics Service - Pro Tier Dashboard Analytics.

Provides aggregated analytics data for Pro users:
- QR scans (from qr_scans table - tracks /r/<code> visits)
- Public page views (from property_views.is_internal=0)
- Internal agent views (from property_views.is_internal=1)
- Leads over time (last 30 days)
- Lead conversion rate
- Top properties by leads
"""
from datetime import datetime, timedelta, date as date_type
from database import get_db
from utils.timestamps import days_ago


def _normalize_date(val) -> str:
    """
    Normalize a date value to YYYY-MM-DD string.
    Handles datetime.date, datetime.datetime, and string inputs.
    """
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date_type):
        return val.isoformat()
    # Assume string, return as-is
    return str(val)[:10]


def get_dashboard_analytics(agent_id: int = None, user_id: int = None) -> dict:
    """
    Fetch all analytics data for the agent's dashboard.
    Supports fetching by single agent_id OR user_id (aggregating all agents).
    
    Returns dict with:
    - leads_over_time: list of {date, count} for last 30 days
    - conversion_rate: float or None if no view data
    - top_properties: list of {property_id, address, lead_count}
    - total_leads_30d: int
    - qr_scans_30d: int (QR code scans via /r/<code>)
    - public_views_30d: int (buyer page views via /p/<slug>)
    - internal_views_30d: int (agent views via /go/<id>)
    """
    if not agent_id and not user_id:
        return {}

    db = get_db()
    thirty_days_ago = days_ago(30)
    
    # Determine filter clauses
    if user_id:
        # Filter by ALL agents belonging to user
        agent_filter = "agent_id IN (SELECT id FROM agents WHERE user_id = %s)"
        prop_agent_filter = "p.agent_id IN (SELECT id FROM agents WHERE user_id = %s)"
        param = user_id
    else:
        # Filter by specific agent
        agent_filter = "agent_id = %s"
        prop_agent_filter = "p.agent_id = %s"
        param = agent_id

    # 1. Leads over time (last 30 days, grouped by date)
    # Note: 'leads' table has 'agent_id' column
    leads_by_date = db.execute(f"""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM leads
        WHERE {agent_filter} AND created_at > %s
        GROUP BY DATE(created_at)
        ORDER BY date
    """, (param, thirty_days_ago)).fetchall()
    
    # Normalize dates to strings for Postgres compatibility
    leads_over_time = [
        {"date": _normalize_date(row['date']), "count": row['count']} 
        for row in leads_by_date
    ]
    
    # Total leads in last 30 days
    total_leads_30d = sum(item['count'] for item in leads_over_time)
    
    
    # 2. QR Scans Over Time (last 30 days)
    qr_scans_by_date = db.execute(f"""
        SELECT DATE(s.scanned_at) as date, COUNT(*) as count
        FROM qr_scans s
        JOIN properties p ON s.property_id = p.id
        WHERE {prop_agent_filter} AND s.scanned_at > %s
        GROUP BY DATE(s.scanned_at)
        ORDER BY date
    """, (param, thirty_days_ago)).fetchall()
    
    # Normalize dates to strings for Postgres compatibility
    qr_scans_over_time = [
        {"date": _normalize_date(row['date']), "count": row['count']}
        for row in qr_scans_by_date
    ]
    
    # QR Scans Total (last 30 days)
    qr_scans_30d = sum(item['count'] for item in qr_scans_over_time)
    
    # 3. Public page views (via /p/<slug>, not internal)
    public_views_result = db.execute(f"""
        SELECT COUNT(*) as cnt
        FROM property_views v
        JOIN properties p ON v.property_id = p.id
        WHERE {prop_agent_filter} AND v.viewed_at > %s AND v.is_internal = 0
    """, (param, thirty_days_ago)).fetchone()
    public_views_30d = public_views_result['cnt'] if public_views_result else 0
    
    # 4. Internal agent views (via /go/<id>)
    internal_views_result = db.execute(f"""
        SELECT COUNT(*) as cnt
        FROM property_views v
        JOIN properties p ON v.property_id = p.id
        WHERE {prop_agent_filter} AND v.viewed_at > %s AND v.is_internal = 1
    """, (param, thirty_days_ago)).fetchone()
    internal_views_30d = internal_views_result['cnt'] if internal_views_result else 0
    
    # 5. Conversion rate (leads / QR scans)
    conversion_rate = None
    if qr_scans_30d > 0:
        conversion_rate = round((total_leads_30d / qr_scans_30d) * 100, 1)
    
    # 6. Top 5 properties by lead count (all-time)
    top_properties = db.execute(f"""
        SELECT 
            p.id as property_id,
            p.address,
            COUNT(l.id) as lead_count
        FROM properties p
        LEFT JOIN leads l ON p.id = l.property_id
        WHERE {prop_agent_filter}
        GROUP BY p.id, p.address
        HAVING COUNT(l.id) > 0
        ORDER BY COUNT(l.id) DESC
        LIMIT 5
    """, (param,)).fetchall()
    
    top_properties_list = [
        {
            "property_id": row['property_id'],
            "address": row['address'],
            "lead_count": row['lead_count']
        }
        for row in top_properties
    ]
    
    # For backward compatibility, include total_views_30d as qr_scans
    return {
        "leads_over_time": leads_over_time,
        "conversion_rate": conversion_rate,
        "top_properties": top_properties_list,
        "total_leads_30d": total_leads_30d,
        "total_views_30d": qr_scans_30d,  # Backward compatibility
        "qr_scans_30d": qr_scans_30d,
        "public_views_30d": public_views_30d,
        "internal_views_30d": internal_views_30d,
        "qr_scans_over_time": qr_scans_over_time,
    }
