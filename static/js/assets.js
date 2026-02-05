/**
 * assets.js
 * Handles order processing, size resizing, and UI interaction for the assets page
 */

// Store original size for revert on error
let originalSize = null;

function getConfig() {
    const configEl = document.getElementById('assets-page-config');
    if (!configEl) {
        console.error("Configuration element #assets-page-config not found!");
        return null;
    }
    return {
        orderId: configEl.dataset.orderId,
        guestToken: configEl.dataset.guestToken,
        csrfToken: configEl.dataset.csrfToken,
        orderUrl: configEl.dataset.orderUrl,
        resizeUrl: configEl.dataset.resizeUrl,
        orderStatus: configEl.dataset.orderStatus,
        isLocked: configEl.dataset.isLocked === 'true',
        isGuest: configEl.dataset.isGuest === 'true'
    };
}


function getAllowedSizesForMaterial(material) {
    // Yard sign matrix
    if (material === 'aluminum_040') {
        return ['18x24', '24x36', '36x24'];
    }
    // Default: coroplast_4mm
    return ['12x18', '18x24', '24x36'];
}

function applyMaterialConstraints(material) {
    const sizeSelector = document.getElementById('size-selector');
    if (!sizeSelector) return;

    const allowed = new Set(getAllowedSizesForMaterial(material));

    // Enable/disable options
    Array.from(sizeSelector.options).forEach(opt => {
        opt.disabled = !allowed.has(opt.value);
        // If current selection becomes disabled, clear it so we can pick a valid one
        if (opt.disabled && opt.selected) opt.selected = false;
    });

    // Auto-correct invalid selection
    if (!allowed.has(sizeSelector.value)) {
        const firstValid = Array.from(sizeSelector.options).find(o => !o.disabled);
        if (firstValid) {
            sizeSelector.value = firstValid.value;
            // Keep preview in sync
            resizeSign(firstValid.value);
        }
    }
}

function orderSign() {
    const btn = document.getElementById('order-btn');
    const originalText = btn.innerText;
    const config = getConfig();

    if (!config || !config.orderId || !config.orderUrl) {
        alert("Missing order configuration details.");
        return;
    }

    // UI Feedback
    btn.innerText = "Redirecting to Checkout...";
    btn.style.opacity = "0.7";
    btn.style.pointerEvents = "none";

    const requestBody = {
        order_id: config.orderId
    };

    // Include current selected size (prevents material/size drift)
    const sizeSelector = document.getElementById('size-selector');
    if (sizeSelector && sizeSelector.value) {
        requestBody.size = sizeSelector.value;
    }

    // Include material if selector exists
    const materialSelector = document.getElementById('material-selector');
    if (materialSelector) {
        console.log("Found material selector:", materialSelector);
        console.log("Selected material:", materialSelector.value);
        requestBody.material = materialSelector.value;
    } else {
        console.warn("Material selector not found in DOM");
    }

    // Include guest_token if present
    if (config.guestToken) {
        requestBody.guest_token = config.guestToken;
    }

    // Include guest email if present (for unauthenticated users)
    const emailInput = document.getElementById('guest-email');
    if (emailInput && emailInput.value) {
        requestBody.email = emailInput.value;
    } else if (config.isGuest && !emailInput) {
        // Fallback? DOM mismatch
        console.warn("Guest user but no email input found");
    } else if (config.isGuest && !emailInput.value) {
        btn.innerText = originalText;
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
        alert("Please enter your email address to proceed.");
        return;
    }

    fetch(config.orderUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': config.csrfToken,
        },
        body: JSON.stringify(requestBody)
    })
        .then(async response => {
            if (response.redirected) {
                window.location.href = response.url;
                return;
            }

            const isJson = response.headers.get('content-type')?.includes('application/json');
            const text = await response.text();

            if (!response.ok) {
                throw new Error(isJson ? JSON.parse(text).error : `Server Error: ${response.status}`);
            }

            if (!isJson) {
                throw new Error("Received invalid response from server");
            }

            return JSON.parse(text);
        })
        .then(data => {
            if (!data) return; // Handled by redirect above

            if (data.success && data.checkoutUrl) {
                // Redirect to Stripe
                window.location.href = data.checkoutUrl;
            } else {
                throw new Error(data.error || "Unknown error");
            }
        })
        .catch(error => {
            btn.innerText = originalText;
            btn.style.opacity = "1";
            btn.style.pointerEvents = "auto";
            console.error('Error:', error);
            alert(error.message || "An error occurred connecting to the server.");
        });
}

function resizeSign(newSize) {
    const config = getConfig();
    const sizeSelector = document.getElementById('size-selector');
    const statusEl = document.getElementById('resize-status');
    const previewImg = document.getElementById('preview-image');

    if (!config || config.isLocked) {
        // Only block if locked (paid) or invalid config
        // Guests are allowed if token is present (validated by backend)
        return;
    }

    // Show loading state
    statusEl.textContent = 'Updating...';
    statusEl.className = 'resize-status loading';
    sizeSelector.disabled = true;

    // Prevent checkout while resize is in progress
    const orderBtn = document.getElementById('order-btn');
    if (orderBtn) {
        orderBtn.style.pointerEvents = 'none';
        orderBtn.style.opacity = '0.6';
    }

    const requestBody = {
        order_id: config.orderId,
        size: newSize
    };

    if (config.guestToken) {
        requestBody.guest_token = config.guestToken;
    }

    fetch(config.resizeUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': config.csrfToken,
        },
        body: JSON.stringify(requestBody)
    })
        .then(async response => {
            const data = await response.json();

            if (!response.ok || !data.success) {
                // Handle specific error codes
                let errorMessage = 'Resize failed';
                switch (data.error) {
                    case 'invalid_size':
                        errorMessage = 'Invalid size selected';
                        break;
                    case 'unauthorized':
                        errorMessage = 'Not authorized to modify this order';
                        break;
                    case 'order_locked_paid':
                        errorMessage = 'Cannot resize a paid order';
                        break;
                    case 'render_failed':
                        errorMessage = data.message || 'Failed to generate new sign';
                        break;
                    default:
                        errorMessage = data.message || data.error || 'Unknown error';
                }
                throw new Error(errorMessage);
            }

            return data;
        })
        .then(data => {
            // Success - update preview
            if (data.preview_url) {
                previewImg.src = data.preview_url;
            }

            // Update stored original size
            originalSize = data.size;

            // Clear status
            statusEl.textContent = '';
            statusEl.className = 'resize-status';
            sizeSelector.disabled = false;
            const orderBtn2 = document.getElementById('order-btn');
            if (orderBtn2) {
                orderBtn2.style.pointerEvents = 'auto';
                orderBtn2.style.opacity = '1';
            }
        })
        .catch(error => {
            console.error('Resize error:', error);

            // Show error
            statusEl.textContent = error.message;
            statusEl.className = 'resize-status error';

            // Revert selector to original size
            if (originalSize) {
                sizeSelector.value = originalSize;
            }

            sizeSelector.disabled = false;
            const orderBtn2 = document.getElementById('order-btn');
            if (orderBtn2) {
                orderBtn2.style.pointerEvents = 'auto';
                orderBtn2.style.opacity = '1';
            }

            // Clear error after 5 seconds
            setTimeout(() => {
                if (statusEl.classList.contains('error')) {
                    statusEl.textContent = '';
                    statusEl.className = 'resize-status';
                }
            }, 5000);
        });
}

// Attach event listeners when DOM loads
document.addEventListener('DOMContentLoaded', () => {
    const orderBtn = document.getElementById('order-btn');
    if (orderBtn) {
        orderBtn.addEventListener('click', (e) => {
            e.preventDefault();
            orderSign();
        });
    }

    const sizeSelector = document.getElementById('size-selector');
    if (sizeSelector) {
        // Store original size
        originalSize = sizeSelector.value;

        sizeSelector.addEventListener('change', (e) => {
            resizeSign(e.target.value);
        });
    }


    const materialSelector = document.getElementById('material-selector');
    if (materialSelector && sizeSelector) {
        // Apply constraints on load and on material changes
        applyMaterialConstraints(materialSelector.value);
        // Ensure originalSize tracks the effective selection
        originalSize = sizeSelector.value;

        materialSelector.addEventListener('change', (e) => {
            applyMaterialConstraints(e.target.value);
        });
    }
});
