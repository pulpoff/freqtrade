/**
 * BotCrypto - Simple SPA Router
 * Manages hash-based routing and page lifecycle
 */
// Router is handled inline in App.navigate() via hash change
// This file is kept for any future advanced routing needs

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl+Shift+1-7 for quick navigation (require Shift to avoid accidental triggers)
    if (e.ctrlKey && e.shiftKey && e.key >= '1' && e.key <= '7') {
        e.preventDefault();
        const pages = ['dashboard', 'bots', 'strategy-builder', 'backtesting', 'strategy-store', 'trades', 'config'];
        const idx = parseInt(e.key) - 1;
        if (pages[idx]) App.navigate(pages[idx]);
    }
    // Escape to close modals/offcanvas
    if (e.key === 'Escape') {
        const offcanvas = document.querySelector('.offcanvas.show');
        if (offcanvas) {
            bootstrap.Offcanvas.getInstance(offcanvas)?.hide();
        }
    }
});
