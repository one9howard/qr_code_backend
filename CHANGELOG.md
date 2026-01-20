# CHANGELOG

## [Unreleased] - 2026-01-06

### Analytics Tracking System (NEW)

**Routes:**
- **New** `GET /r/<code>` - QR scan redirect (logs scan, redirects to /p/<slug>)
- **New** `GET /go/<int:property_id>` - Internal agent redirect (sets cookie, requires login+ownership)
- **Modified** `GET /p/<slug>` - Now logs page views (not scans), respects internal_view cookie

**Database:**
- **New column** `properties.qr_code` - Unique 12-char URL-safe shortcode for QR URLs
- **New table** `property_views` - Tracks page views with is_internal flag and source
- Automatic backfill of qr_code for existing properties

**QR Code Generation:**
- **Modified** `routes/agent.py` - Generates qr_code shortcode on property creation
- QR codes now encode `/r/{qr_code}` instead of `/p/{slug}`

**Dashboard:**
- **Modified** View link uses `/go/<id>` for internal agent redirect
- Agent views no longer inflate buyer analytics

**Analytics:**
- **Modified** `services/analytics.py` - Separate metrics for QR scans, public views, internal views
- Pro dashboard shows accurate QR scan count vs page views

**Tests:**
- **New** `tests/test_analytics_tracking.py` - 8 acceptance tests

---

### Previous Changes (same date)

#### CSRF Configuration
- Documented CSRF exemption for leads_bp (Option A)

#### Dashboard Cleanup
- Removed unused imports, simplified agent logic
- Changed `FREE_LEAD_LIMIT` from 5 to 2

#### Pro Features
- Analytics service with real data
- CSV export endpoint for leads
- Export CSV button in dashboard

---

## Migration Notes

### Database
- `qr_code` column auto-created and backfilled
- `property_views` table auto-created
- Run app once to trigger migrations

### Breaking Changes
- New properties must have qr_code (auto-generated)
- QR codes now redirect via `/r/<code>`, canonical page remains `/p/<slug>`
- Free tier shows 2 leads (was 5)


