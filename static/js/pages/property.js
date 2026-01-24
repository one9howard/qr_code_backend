/**
 * Property Page JavaScript
 * Handles navigation, lead forms, lightbox, events, and gated content interactions.
 * 
 * NO JQUERY DEPENDENCY - Pure vanilla JS
 * All actions fail silently if elements/endpoints missing
 */

(function () {
    'use strict';

    // ============================================================
    // GLOBALS & STATE
    // ============================================================
    const DATA = window.PROPERTY_DATA || {};
    let lightboxIndex = 0;

    // ============================================================
    // INIT ON DOM READY
    // ============================================================
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        initCloseButton();
        initLeadForm();
        initMessageToggle();
        initLightbox();
        initGatedContent();
        initMobileActions();
        initMobileLeadModal();
        initKeyboardNav();
        initScrollToCTA();
    }

    // ============================================================
    // CLOSE BUTTON LOGIC
    // ============================================================
    function initCloseButton() {
        const closeBtn = document.getElementById('close-property');
        if (closeBtn) {
            closeBtn.addEventListener('click', handleClose);
        }
    }

    function handleClose(e) {
        if (e) e.preventDefault();

        // 1. Check for return_to query param
        const urlParams = new URLSearchParams(window.location.search);
        const returnTo = urlParams.get('return_to');
        if (returnTo) {
            window.location.href = returnTo;
            return;
        }

        // 2. Check if referrer is same origin
        const ref = document.referrer;
        if (ref) {
            try {
                const refUrl = new URL(ref);
                if (refUrl.origin === window.location.origin) {
                    window.location.href = ref;
                    return;
                }
            } catch (e) {
                // Invalid URL, continue
            }
        }

        // 3. Try history.back()
        if (window.history.length > 1) {
            window.history.back();
            // Fallback if back doesn't navigate away
            setTimeout(() => {
                window.location.href = '/';
            }, 500);
            return;
        }

        // 4. Final fallback
        window.location.href = '/';
    }

    // ============================================================
    // KEYBOARD NAVIGATION
    // ============================================================
    function initKeyboardNav() {
        document.addEventListener('keydown', (e) => {
            // Escape closes modals/lightbox or exits page
            if (e.key === 'Escape') {
                const lightbox = document.getElementById('lightbox');
                const upsell = document.getElementById('upsell-sheet');

                if (lightbox && lightbox.style.display !== 'none') {
                    closeLightbox();
                } else if (upsell && upsell.style.display !== 'none') {
                    closeUpsellSheet();
                } else {
                    handleClose();
                }
            }

            // Arrow keys for lightbox
            if (document.getElementById('lightbox')?.style.display !== 'none') {
                if (e.key === 'ArrowLeft') lightboxPrev();
                if (e.key === 'ArrowRight') lightboxNext();
            }
        });
    }

    // ============================================================
    // LEAD FORM
    // ============================================================
    function initLeadForm() {
        const form = document.getElementById('lead-form');
        if (!form) return;

        form.addEventListener('submit', handleLeadSubmit);
    }

    async function handleLeadSubmit(e) {
        e.preventDefault();

        const form = e.target;
        const errorEl = document.getElementById('lead-form-error');
        const successEl = document.getElementById('lead-form-success');
        const submitBtn = document.getElementById('lead-submit-btn');

        // Hide previous messages
        if (errorEl) { errorEl.style.display = 'none'; errorEl.textContent = ''; }
        if (successEl) { successEl.style.display = 'none'; successEl.textContent = ''; }

        // Disable button
        const originalText = submitBtn ? submitBtn.textContent : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
        }

        // Collect form data
        const formData = {
            property_id: form.property_id?.value || DATA.id,
            buyer_name: form.buyer_name?.value || '',
            buyer_email: form.buyer_email?.value || '',
            buyer_phone: form.buyer_phone?.value || '',
            preferred_contact: form.preferred_contact?.value || 'email',
            best_time: form.best_time?.value || '',
            message: form.message?.value || '',
            consent: form.consent?.checked || false,
            website: form.website?.value || '', // Honeypot
            request_type: form.request_type?.value || 'info'
        };

        try {
            const response = await fetch('/api/leads/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            if (data.success) {
                if (successEl) {
                    successEl.textContent = data.message || 'Request sent successfully!';
                    successEl.style.display = 'block';
                }
                form.reset();
                sendEvent('lead_submitted', { request_type: formData.request_type });
            } else {
                if (errorEl) {
                    errorEl.textContent = data.message || data.error || 'An error occurred';
                    errorEl.style.display = 'block';
                }
            }
        } catch (err) {
            console.error('Lead form error:', err);
            if (errorEl) {
                errorEl.textContent = 'Network error. Please try again.';
                errorEl.style.display = 'block';
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText || 'Send request';
            }
        }
    }

    // ============================================================
    // MESSAGE TOGGLE
    // ============================================================
    function initMessageToggle() {
        const toggle = document.getElementById('toggle-message');
        const field = document.getElementById('message-field');

        if (toggle && field) {
            toggle.addEventListener('click', () => {
                const isHidden = field.style.display === 'none';
                field.style.display = isHidden ? 'block' : 'none';
                toggle.textContent = isHidden ? '- Hide message' : '+ Add a message';
            });
        }
    }

    // ============================================================
    // SCROLL TO CTA
    // ============================================================
    function initScrollToCTA() {
        // Desktop "Request info" button scrolls to form
        const scrollBtn = document.getElementById('scroll-to-form-btn');
        if (scrollBtn) {
            scrollBtn.addEventListener('click', () => {
                const form = document.getElementById('lead-form');
                if (form) {
                    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Focus first input
                    setTimeout(() => {
                        const firstInput = form.querySelector('input[type="text"]');
                        if (firstInput) firstInput.focus();
                    }, 500);
                }
                sendEvent('cta_click', { type: 'request_info' });
            });
        }

        // "Request a tour" button
        const tourBtn = document.getElementById('request-tour');
        if (tourBtn) {
            tourBtn.addEventListener('click', () => {
                // Set request type
                const requestType = document.getElementById('request_type');
                if (requestType) requestType.value = 'tour';

                // Scroll to form
                const form = document.getElementById('lead-form');
                if (form) {
                    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(() => {
                        const firstInput = form.querySelector('input[type="text"]');
                        if (firstInput) firstInput.focus();
                    }, 500);
                }
                sendEvent('cta_click', { type: 'request_tour' });
            });
        }
    }

    // ============================================================
    // MOBILE ACTION BAR
    // ============================================================
    function initMobileActions() {
        const infoBtn = document.getElementById('mobile-request-info');
        if (infoBtn) {
            infoBtn.addEventListener('click', () => {
                // IMPORTANT: Lead capture must NOT be blocked by upsell
                // Always open the mobile lead modal for all tiers
                openMobileLeadModal();
                sendEvent('cta_click', { type: 'request_info' });
            });
        }

        // Track call/email clicks
        document.querySelectorAll('[data-action="call"]').forEach(btn => {
            btn.addEventListener('click', () => sendEvent('cta_click', { type: 'call' }));
        });

        document.querySelectorAll('[data-action="email"]').forEach(btn => {
            btn.addEventListener('click', () => sendEvent('cta_click', { type: 'email' }));
        });
    }

    // ============================================================
    // MOBILE LEAD MODAL
    // ============================================================
    function initMobileLeadModal() {
        const modal = document.getElementById('mobile-lead-modal');
        if (!modal) return;

        // Close handlers
        document.getElementById('mobile-lead-close')?.addEventListener('click', closeMobileLeadModal);
        document.getElementById('mobile-lead-backdrop')?.addEventListener('click', closeMobileLeadModal);

        // Form submission
        const form = document.getElementById('mobile-lead-form');
        if (form) {
            form.addEventListener('submit', handleMobileLeadSubmit);
        }
    }

    function openMobileLeadModal(requestType) {
        const modal = document.getElementById('mobile-lead-modal');
        if (!modal) return;

        // Set request type if provided
        if (requestType) {
            const typeField = document.getElementById('mobile_request_type');
            if (typeField) typeField.value = requestType;
        }

        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Focus first input
        setTimeout(() => {
            const firstInput = modal.querySelector('input[type="text"]');
            if (firstInput) firstInput.focus();
        }, 100);
    }

    function closeMobileLeadModal() {
        const modal = document.getElementById('mobile-lead-modal');
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
    }

    async function handleMobileLeadSubmit(e) {
        e.preventDefault();

        const form = e.target;
        const errorEl = document.getElementById('mobile-lead-error');
        const successEl = document.getElementById('mobile-lead-success');
        const submitBtn = document.getElementById('mobile-lead-submit');

        // Hide previous messages
        if (errorEl) { errorEl.style.display = 'none'; errorEl.textContent = ''; }
        if (successEl) { successEl.style.display = 'none'; successEl.textContent = ''; }

        // Disable button
        const originalText = submitBtn ? submitBtn.textContent : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
        }

        // Collect form data
        const formData = {
            property_id: form.property_id?.value || DATA.id,
            buyer_name: form.buyer_name?.value || '',
            buyer_email: form.buyer_email?.value || '',
            buyer_phone: form.buyer_phone?.value || '',
            preferred_contact: form.preferred_contact?.value || 'email',
            best_time: form.best_time?.value || '',
            message: form.message?.value || '',
            consent: form.consent?.checked || false,
            website: form.website?.value || '', // Honeypot
            request_type: form.request_type?.value || 'info'
        };

        try {
            const response = await fetch('/api/leads/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            if (data.success) {
                if (successEl) {
                    successEl.textContent = data.message || 'Request sent successfully!';
                    successEl.style.display = 'block';
                }
                form.reset();
                sendEvent('lead_submitted', { request_type: formData.request_type });

                // Close modal after success
                setTimeout(() => closeMobileLeadModal(), 2000);
            } else {
                if (errorEl) {
                    errorEl.textContent = data.message || data.error || 'An error occurred';
                    errorEl.style.display = 'block';
                }
            }
        } catch (err) {
            console.error('Lead form error:', err);
            if (errorEl) {
                errorEl.textContent = 'Network error. Please try again.';
                errorEl.style.display = 'block';
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText || 'Send request';
            }
        }
    }

    // ============================================================
    // LIGHTBOX (PAID only)
    // ============================================================
    function initLightbox() {
        if (!DATA.photos || DATA.photos.length === 0) return;

        const lightbox = document.getElementById('lightbox');
        if (!lightbox) return;

        // Open triggers
        document.getElementById('open-lightbox')?.addEventListener('click', () => openLightbox(0));
        document.getElementById('open-lightbox-more')?.addEventListener('click', () => openLightbox(5));
        document.getElementById('view-all-photos')?.addEventListener('click', () => openLightbox(0));

        // Gallery items
        document.querySelectorAll('.gallery-item').forEach(item => {
            item.addEventListener('click', () => {
                const idx = parseInt(item.dataset.index, 10) || 0;
                openLightbox(idx);
            });
        });

        // Thumbnail buttons
        document.querySelectorAll('.thumb-btn[data-index]').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index, 10) || 0;
                // Update hero image
                const heroImg = document.getElementById('hero-image');
                if (heroImg && DATA.photos[idx]) {
                    heroImg.src = DATA.photos[idx];
                }
                // Update active state
                document.querySelectorAll('.thumb-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        // Controls
        document.getElementById('lightbox-close')?.addEventListener('click', closeLightbox);
        document.getElementById('lightbox-prev')?.addEventListener('click', lightboxPrev);
        document.getElementById('lightbox-next')?.addEventListener('click', lightboxNext);

        // Close on backdrop click
        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox) closeLightbox();
        });
    }

    function openLightbox(index) {
        const lightbox = document.getElementById('lightbox');
        if (!lightbox || !DATA.photos || DATA.photos.length === 0) return;

        lightboxIndex = index;
        updateLightboxImage();
        lightbox.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }

    function closeLightbox() {
        const lightbox = document.getElementById('lightbox');
        if (lightbox) {
            lightbox.style.display = 'none';
            document.body.style.overflow = '';
        }
    }

    function lightboxPrev() {
        if (!DATA.photos) return;
        lightboxIndex = (lightboxIndex - 1 + DATA.photos.length) % DATA.photos.length;
        updateLightboxImage();
    }

    function lightboxNext() {
        if (!DATA.photos) return;
        lightboxIndex = (lightboxIndex + 1) % DATA.photos.length;
        updateLightboxImage();
    }

    function updateLightboxImage() {
        const img = document.getElementById('lightbox-img');
        const counter = document.getElementById('lightbox-counter');
        if (img && DATA.photos && DATA.photos[lightboxIndex]) {
            img.src = DATA.photos[lightboxIndex];
        }
        if (counter && DATA.photos) {
            counter.textContent = `${lightboxIndex + 1} / ${DATA.photos.length}`;
        }
    }

    // ============================================================
    // GATED CONTENT (FREE/EXPIRED)
    // ============================================================
    function initGatedContent() {
        if (DATA.tier === 'paid') return;

        // Continue reading trigger
        const continueBtn = document.querySelector('.continue-reading');
        if (continueBtn) {
            continueBtn.addEventListener('click', () => {
                sendEvent('gated_content_attempt', {
                    content_type: 'description',
                    trigger: 'continue_reading'
                });
                showUpsellSheet('continue_reading');
            });
        }

        // Gallery locked click
        const galleryLocked = document.querySelector('.gallery-locked');
        if (galleryLocked) {
            galleryLocked.addEventListener('click', () => {
                sendEvent('gated_content_attempt', {
                    content_type: 'photos',
                    trigger: 'click_gallery'
                });
                showUpsellSheet('click_gallery');
            });
        }
    }

    // ============================================================
    // UPSELL SHEET
    // ============================================================
    function showUpsellSheet(trigger) {
        const sheet = document.getElementById('upsell-sheet');
        if (!sheet) return;

        sheet.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        sendEvent('upsell_shown', { trigger });

        // Close handlers
        document.getElementById('upsell-close')?.addEventListener('click', closeUpsellSheet);
        document.getElementById('upsell-backdrop')?.addEventListener('click', closeUpsellSheet);
        document.getElementById('upsell-contact')?.addEventListener('click', () => {
            closeUpsellSheet();
            // Scroll to form or trigger contact
            const agentRail = document.getElementById('agent-rail');
            if (agentRail && window.innerWidth >= 1024) {
                agentRail.scrollIntoView({ behavior: 'smooth' });
            } else {
                // On mobile, show email option
                const email = document.querySelector('[data-action="email"]');
                if (email) email.click();
            }
        });
    }

    function closeUpsellSheet() {
        const sheet = document.getElementById('upsell-sheet');
        if (sheet) {
            sheet.style.display = 'none';
            document.body.style.overflow = '';
            sendEvent('upsell_dismissed', {});
        }
    }

    // ============================================================
    // EVENT TRACKING (Best-effort, no-throw)
    // ============================================================
    function sendEvent(eventName, data) {
        try {
            // Build payload object - NO PII allowed
            const safeData = { ...data };
            // Remove any accidentally included PII
            delete safeData.buyer_name;
            delete safeData.buyer_email;
            delete safeData.buyer_phone;
            delete safeData.message;
            delete safeData.email;
            delete safeData.phone;
            delete safeData.name;

            // Add context
            safeData.tier = DATA.tier;
            safeData.timestamp = new Date().toISOString();

            // Build request body per API contract
            const body = {
                event_type: eventName,
                property_id: DATA.id,
                payload: safeData
            };

            // Try /api/events if it exists
            fetch('/api/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            }).catch(() => {
                // Silently ignore - endpoint may not exist
            });

            // Also call global trackEvent if available
            if (typeof window.trackEvent === 'function') {
                window.trackEvent(eventName, body);
            }
        } catch (err) {
            // Silently ignore all errors
        }
    }

})();
