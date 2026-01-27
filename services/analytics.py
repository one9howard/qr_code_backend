
"""
Analytics Service Layer (Phase 5)

Single source of truth for agent retention metrics.
Aggregates data from:
- qr_scans (Physical engagement)
- property_views (Digital engagement)
- leads (Conversion)
- app_events (Intent/CTA)

Key Functions:
- per_property_metrics(property_id, range_days)
- per_agent_rollup(user_id, range_days)
"""
from datetime import datetime
from database import get_db
from utils.timestamps import minutes_ago, utc_now

def per_property_metrics(property_id: int, range_days: int = 7, compare_days: int = 7) -> dict:
    """
    Get aggregated metrics for a single property with WoW comparison.
    """
    db = get_db()
    
    # helper for intervals
    def get_count(table, date_col, pid, days_offset=0, days_span=7, extra_where=""):
        # standard postgres interval syntax
        query = f"""
            SELECT COUNT(*) FROM {table} 
            WHERE property_id = %s 
            AND {date_col} >= NOW() - INTERVAL '{days_offset + days_span} days'
            AND {date_col} < NOW() - INTERVAL '{days_offset} days'
            {extra_where}
        """
        return db.execute(query, (pid,)).fetchone()[0]

    # 1. Scans (Physical)
    scans_curr = get_count('qr_scans', 'scanned_at', property_id, 0, range_days)
    scans_prev = get_count('qr_scans', 'scanned_at', property_id, range_days, compare_days)
    
    # 2. Views (Digital)
    # Exclude internal views for purity? Usually yes, property_views has is_internal column
    views_curr = get_count('property_views', 'viewed_at', property_id, 0, range_days, "AND is_internal = 0")
    views_prev = get_count('property_views', 'viewed_at', property_id, range_days, compare_days, "AND is_internal = 0")
    
    # 3. Leads (Conversion)
    leads_curr = get_count('leads', 'created_at', property_id, 0, range_days)
    leads_prev = get_count('leads', 'created_at', property_id, range_days, compare_days)
    
    # 4. Contact Intents (CTA Clicks)
    # app_events table, event_type = 'cta_click'
    cta_curr = get_count('app_events', 'occurred_at', property_id, 0, range_days, "AND event_type = 'cta_click'")
    cta_prev = get_count('app_events', 'occurred_at', property_id, range_days, compare_days, "AND event_type = 'cta_click'")

    # Calculate Deltas
    def calc_delta(curr, prev):
        if prev == 0:
            return 100 if curr > 0 else 0
        return int(((curr - prev) / prev) * 100)

    # Last Activity timestamps
    last_scan = db.execute("SELECT MAX(scanned_at) FROM qr_scans WHERE property_id = %s", (property_id,)).fetchone()[0]
    last_view = db.execute("SELECT MAX(viewed_at) FROM property_views WHERE property_id = %s", (property_id,)).fetchone()[0]
    last_lead = db.execute("SELECT MAX(created_at) FROM leads WHERE property_id = %s", (property_id,)).fetchone()[0]
    
    # Generate Insights
    insights = []
    
    # Insight: Cold Listing
    if scans_curr == 0 and range_days >= 7:
        insights.append("Cold listing: check sign placement and share link")
    
    # Insight: Momentum
    if scans_curr > 5 and calc_delta(scans_curr, scans_prev) > 20:
        insights.append("Momentum increasing: consider open house / boost")
        
    # Insight: High Traffic, Low Conv
    if (scans_curr + views_curr) > 20 and leads_curr == 0:
        insights.append("Traffic without conversion: improve CTA / photos")
        
    # Insight: High Intent, Low Conv
    if cta_curr > 3 and leads_curr == 0:
         insights.append("Friction: form too long / mobile UX issue")

    return {
        "scans": {
            "total": scans_curr, # Labelled total but actually range count for the table? 
                                 # Dashboard usually wants 'Total' lifetime vs '7d' range. 
                                 # Let's provide range metrics mostly here, maybe add lifetime lookup if needed.
                                 # Requirement says "7d Scans", "7d Views" for list.
            "prev": scans_prev,
            "delta": calc_delta(scans_curr, scans_prev)
        },
        "views": {
            "total": views_curr,
            "prev": views_prev,
            "delta": calc_delta(views_curr, views_prev)
        },
        "leads": {
            "total": leads_curr,
            "prev": leads_prev,
            "delta": calc_delta(leads_curr, leads_prev)
        },
        "ctas": {
            "total": cta_curr,
            "prev": cta_prev,
            "delta": calc_delta(cta_curr, cta_prev)
        },
        "last_activity": {
            "scan": last_scan,
            "view": last_view,
            "lead": last_lead,
            "summary": max(filter(None, [last_scan, last_view, last_lead]), default=None)
        },
        "insights": insights
    }

def per_agent_rollup(user_id: int, range_days: int = 7) -> dict:
    """
    Aggregate metrics across all properties for an agent.
    Used for Main Dashboard Cards.
    """
    db = get_db()
    
    # Get agent properties
    agent_id = db.execute("SELECT id FROM agents WHERE user_id = %s", (user_id,)).fetchone()
    if not agent_id:
        return {}
    agent_id = agent_id['id']
    
    # Helper for aggregate counts
    def get_agg(table, date_col, extra_join="", extra_where=""):
        # Count rows where property belongs to agent
        query = f"""
            SELECT COUNT(t.id) 
            FROM {table} t
            JOIN properties p ON t.property_id = p.id
            {extra_join}
            WHERE p.agent_id = %s
            {extra_where}
        """
        return db.execute(query, (agent_id,)).fetchone()[0]

    def get_agg_range(table, date_col, days_offset=0, days_span=7, extra_join="", extra_where=""):
        query = f"""
            SELECT COUNT(t.id) 
            FROM {table} t
            JOIN properties p ON t.property_id = p.id
            {extra_join}
            WHERE p.agent_id = %s
            AND t.{date_col} >= NOW() - INTERVAL '{days_offset + days_span} days'
            AND t.{date_col} < NOW() - INTERVAL '{days_offset} days'
            {extra_where}
        """
        return db.execute(query, (agent_id,)).fetchone()[0]

    # 1. Total Scans (Lifetime)
    scans_lifetime = get_agg('qr_scans', 'scanned_at')
    
    # 2. Total Views (Lifetime, Public)
    views_lifetime = get_agg('property_views', 'viewed_at', extra_where="AND t.is_internal = 0")
    
    # 3. Leads (Lifetime & 30d)
    leads_lifetime = get_agg('leads', 'created_at')
    leads_30d = get_agg_range('leads', 'created_at', 0, 30)
    
    # 4. Contact Intents (7d & delta)
    ctas_7d = get_agg_range('app_events', 'occurred_at', 0, 7, extra_where="AND t.event_type = 'cta_click'")
    ctas_prev_7d = get_agg_range('app_events', 'occurred_at', 7, 7, extra_where="AND t.event_type = 'cta_click'")
    
    # Scan/View 7d for Deltas (Optional for cards, users usually like WoW there too)
    scans_7d = get_agg_range('qr_scans', 'scanned_at', 0, 7)
    scans_prev_7d = get_agg_range('qr_scans', 'scanned_at', 7, 7)
    
    views_7d = get_agg_range('property_views', 'viewed_at', 0, 7, extra_where="AND t.is_internal = 0")
    views_prev_7d = get_agg_range('property_views', 'viewed_at', 7, 7, extra_where="AND t.is_internal = 0")
    
    leads_7d = get_agg_range('leads', 'created_at', 0, 7)
    leads_prev_7d = get_agg_range('leads', 'created_at', 7, 7)
    
    def calc_delta(curr, prev):
        if prev == 0: return 100 if curr > 0 else 0
        return int(((curr - prev) / prev) * 100)

    return {
        "scans": { 
            "lifetime": scans_lifetime,
            "7d": scans_7d,
            "delta": calc_delta(scans_7d, scans_prev_7d)
        },
        "views": { 
            "lifetime": views_lifetime, 
            "7d": views_7d,
            "delta": calc_delta(views_7d, views_prev_7d)
        },
        "leads": { 
            "lifetime": leads_lifetime, 
            "30d": leads_30d,
            "7d": leads_7d,
            "delta": calc_delta(leads_7d, leads_prev_7d)
        },
        "ctas": { 
            "7d": ctas_7d, 
            "delta": calc_delta(ctas_7d, ctas_prev_7d)
        }
    }
