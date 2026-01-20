/**
 * submit.js
 * Handles interaction logic for the sign submission form
 */

document.addEventListener('DOMContentLoaded', () => {
    // Color selection logic
    const colorOptions = document.querySelectorAll('.color-option');

    colorOptions.forEach(option => {
        // Add click handler to the entire option container
        option.addEventListener('click', (e) => {
            // Find the radio button within this option
            const radio = option.querySelector('input[type="radio"]');

            // If clicking the label or swatch, manually check the radio
            // (The radio itself handles its own check, so we avoid double-toggling)
            if (e.target !== radio) {
                radio.checked = true;

                // Trigger change event manually if needed, though CSS :checked handles visual state
                // radio.dispatchEvent(new Event('change'));
            }
        });
    });
    // Button loading state
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', (e) => {
            const btn = form.querySelector('.generate-btn');
            if (btn) {
                // Change text immediately
                btn.textContent = 'Generating Sign...';
                // Optional: add loading spinner class if styles exist
                btn.classList.add('loading');
            }
        });
    }
});
