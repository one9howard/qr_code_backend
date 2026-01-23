/**
 * Property Page Logic
 * Handles navigation history, lead forms, and UI interactions.
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- Close Button Logic ---
    const closeBtn = document.getElementById("close-property");
    if (closeBtn) {
        closeBtn.addEventListener("click", (e) => {
            e.preventDefault();
            exitPropertyPage();
        });
    }

    // --- Keyboard Shortcuts ---
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            const modal = document.getElementById('lead-modal');
            if (modal && modal.style.display === 'flex') {
                closeLeadModal();
            } else {
                exitPropertyPage();
            }
        }
    });

    // --- Lead Modal Triggers ---
    // Attach to any button with class 'trigger-lead-modal'
    document.querySelectorAll('.trigger-lead-modal').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            openLeadModal();
        });
    });

    // --- Mobile Action Bar: Scroll to Request Info ---
    const scrollBtn = document.getElementById('scroll-to-contact');
    if (scrollBtn) {
        scrollBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const contactSection = document.getElementById('agent-contact-section');
            if (contactSection) {
                contactSection.scrollIntoView({ behavior: 'smooth' });
            } else {
                // Fallback if section missing
                openLeadModal();
            }
        });
    }
});

/**
 * Robust Exit Strategy
 * return_to > window.opener > document.referrer > history.back > /
 */
function exitPropertyPage() {
    const urlParams = new URLSearchParams(window.location.search);
    const returnTo = urlParams.get('return_to');

    // 1. Explicit Return
    if (returnTo) {
        window.location.href = returnTo;
        return;
    }

    // 2. Script-opened window (try to close)
    if (window.opener && !window.opener.closed) {
        window.close();
        // Fallthrough if blocked
    }

    // 3. Referrer (different from current)
    const ref = document.referrer;
    if (ref && ref !== window.location.href) {
        window.location.href = ref;
        return;
    }

    // 4. History Back
    if (window.history.length > 1) {
        window.history.back();
        // Fallback in case history.back() is just a hash change or stuck
        setTimeout(() => {
            window.location.href = "/";
        }, 500);
        return;
    }

    // 5. Root Fallback
    window.location.href = "/";
}

// --- Lead Modal Functions ---

function openLeadModal() {
    const modal = document.getElementById('lead-modal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeLeadModal() {
    const modal = document.getElementById('lead-modal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Close on outside click
document.addEventListener('click', (e) => {
    if (e.target.id === 'lead-modal') closeLeadModal();
});


/**
 * Submit Lead Form
 */
async function submitLeadForm(e) {
    e.preventDefault();

    const form = document.getElementById('lead-form');
    // Sanity check
    if (!form) return;

    const errorEl = document.getElementById('lead-form-error');
    const successEl = document.getElementById('lead-form-success');
    const submitBtn = document.getElementById('lead-submit-btn');

    if (errorEl) errorEl.style.display = 'none';
    if (successEl) successEl.style.display = 'none';
    if (submitBtn) {
        submitBtn.disabled = true;
        const originalText = submitBtn.textContent;
        submitBtn.textContent = 'Submitting...';
    }

    const formData = {
        property_id: form.property_id.value,
        buyer_name: form.buyer_name.value,
        buyer_email: form.buyer_email.value,
        buyer_phone: form.buyer_phone.value,
        preferred_contact: form.preferred_contact.value,
        best_time: form.best_time.value,
        message: form.message.value,
        consent: form.consent.checked,
        website: form.website.value  // Honeypot
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
                successEl.textContent = data.message || 'Request submitted successfully!';
                successEl.style.display = 'block';
            }
            form.reset();
            setTimeout(() => closeLeadModal(), 2000);

            // Optional: Tracking
            if (window.trackEvent) window.trackEvent('lead_submitted');

        } else {
            if (errorEl) {
                errorEl.textContent = data.message || data.error || 'An error occurred';
                errorEl.style.display = 'block';
            }
        }
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = 'Network error. Please try again.';
            errorEl.style.display = 'block';
        }
        console.error(err);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Request'; // Restore text
        }
    }
}
