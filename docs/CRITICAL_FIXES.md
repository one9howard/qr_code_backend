# Critical Fixes Summary

This document summarizes the 5 critical fixes implemented for security, correctness, and maintainability.

---

## Fix 1: Release Artifact Hygiene

**Problem**: Release ZIPs could include debug scripts, test outputs, and other non-production files.

**Solution**:
- Extended `EXCLUDE_PATTERNS` in `scripts/build_release_zip.py` to exclude:
  - `debug_*.py`, `*_output*.txt`, `landing.png`, `.agent/`
- Added `FORBIDDEN_IN_RELEASE` hard-fail check - build fails with exit code 1 if forbidden files present
- Fixed `scripts/build_release.sh` directory: `private/sign_pdfs` → `private/pdf`

**Verification**:
```bash
python scripts/build_release_zip.py
# Should complete without errors
# Check output for "No forbidden files found"
```

---

## Fix 2: Private Preview Storage

**Problem**: Preview images were served from public `/static/generated/` URLs that could be guessed.

**Solution**:
- Added `PRIVATE_PREVIEW_DIR` to `config.py`
- Created `get_private_preview_path()` in `utils/filenames.py`
- Updated `utils/pdf_preview.py` to write to private directory
- Added authenticated route `GET /orders/<id>/preview` in `routes/orders.py`
- Updated `routes/agent.py` and `templates/assets.html` to use auth URLs

**Authorization Rules**:
- Logged-in user: Must own the order (`order.user_id == current_user.id`)
- Guest: Must have valid `guest_token` in query param AND in session

**Verification**:
1. Guest flow: Submit form → Assets page → Preview loads
2. Copy preview URL to new incognito window → Should return 403
3. Logged-in user: Dashboard → Create sign → Preview loads

---

## Fix 3: Reverse Proxy Correctness (ProxyFix)

**Problem**: `request.remote_addr` showed proxy IP instead of client IP behind nginx.

**Solution**:
- Added `TRUST_PROXY_HEADERS` and `PROXY_FIX_NUM_PROXIES` to `config.py`
- Applied `ProxyFix` middleware in `app.py` (only when `IS_PRODUCTION=true` AND `TRUST_PROXY_HEADERS=true`)
- Created `utils/net.py` with `get_client_ip()` helper
- Updated `routes/leads.py` and `routes/properties.py` to use helper

**Production Setup** (add to `.env`):
```bash
TRUST_PROXY_HEADERS=true
PROXY_FIX_NUM_PROXIES=1
```

> ⚠️ **Only enable when behind trusted proxy!** Enabling without proper proxy headers creates IP spoofing risk.

---

## Fix 4: Identity Consistency

**Problem**: Dashboard used `current_user.full_name` instead of `display_name`.

**Solution**:
- Changed `templates/dashboard.html` line 11: `full_name` → `display_name`

---

## Fix 5: CSS Debt Reduction

**Problem**: `dashboard.html` and `property.html` had extensive inline styles.

**Solution**:
- Created `static/css/pages/dashboard.css` with semantic class names
- Created `static/css/pages/property.css` - extracted full `<style>` block
- Updated templates to link external CSS files

**Note**: `dashboard.html` still has inline styles for progressive migration; `property.css` fully replaced the inline `<style>` block.

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/build_release_zip.py` | Extended exclusions, added forbidden check |
| `scripts/build_release.sh` | Fixed directory path |
| `config.py` | Added `PRIVATE_PREVIEW_DIR`, proxy config |
| `utils/filenames.py` | Added private preview functions |
| `utils/pdf_preview.py` | Write to private directory |
| `utils/env.py` | Added `get_env_bool()` |
| `utils/net.py` | **NEW** - `get_client_ip()` helper |
| `app.py` | ProxyFix middleware |
| `routes/orders.py` | Added `order_preview` route, updated resize |
| `routes/agent.py` | Pass `preview_url` instead of static path |
| `routes/leads.py` | Use `get_client_ip()` |
| `routes/properties.py` | Use `get_client_ip()` |
| `templates/assets.html` | Use authenticated preview URL |
| `templates/dashboard.html` | `display_name`, added CSS link |
| `templates/property.html` | External CSS file |
| `static/css/pages/dashboard.css` | **NEW** |
| `static/css/pages/property.css` | **NEW** |
| `DEPLOYMENT.md` | Added proxy trust section |
