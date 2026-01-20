document.addEventListener('DOMContentLoaded', () => {
    const menuBtn = document.getElementById('mobile-menu-btn');
    const navLinks = document.getElementById('nav-links');

    if (menuBtn && navLinks) {
        menuBtn.addEventListener('click', () => {
            navLinks.classList.toggle('active');

            // Optional: Toggle icon state or aria-expanded
            const isExpanded = navLinks.classList.contains('active');
            menuBtn.setAttribute('aria-expanded', isExpanded);
            menuBtn.innerHTML = isExpanded ? '&times;' : '&#9776;';
        });
    }
});
