/**
 * UniTrade Shop Filter & Sort — Interactive Logic
 * 
 * Reads/writes URL parameters to persist filter & sort state across page loads.
 * Works with the sidebar filter UI and top sort bar on /shop.
 */
document.addEventListener('DOMContentLoaded', function () {
    // Only run on the /shop page
    if (!window.location.pathname.startsWith('/shop')) return;

    const params = new URLSearchParams(window.location.search);

    // ─────────────────────────────────────────────
    // 1. RESTORE FILTER STATE FROM URL
    // ─────────────────────────────────────────────

    // Lokasi
    const lokasiVal = params.get('lokasi') || '';
    if (lokasiVal) {
        const radio = document.querySelector('input[name="lokasi"][value="' + lokasiVal + '"]');
        if (radio) radio.checked = true;
    }

    // Kondisi (URL uses 'new'/'used', radio values are 'baru'/'bekas')
    const kondisiVal = params.get('kondisi') || '';
    if (kondisiVal) {
        var reverseKondisi = { 'new': 'baru', 'used': 'bekas' };
        var radioVal = reverseKondisi[kondisiVal] || kondisiVal;
        const radio = document.querySelector('input[name="kondisi"][value="' + radioVal + '"]');
        if (radio) {
            radio.checked = true;
        }
    }
    // If no kondisi in URL, uncheck all so nothing is pre-selected
    if (!kondisiVal) {
        document.querySelectorAll('input[name="kondisi"]').forEach(function (r) { r.checked = false; });
    }

    // Price slider
    const minSlider = document.getElementById('min-price');
    const maxSlider = document.getElementById('max-price');
    const minTooltip = document.getElementById('min-tooltip');
    const maxTooltip = document.getElementById('max-tooltip');
    const sliderTrack = document.getElementById('slider-track');
    const odooMin = document.getElementById('odoo-min-price');
    const odooMax = document.getElementById('odoo-max-price');

    if (minSlider && maxSlider) {
        // Restore from URL (values are in Rupiah, slider is in K)
        const urlMin = parseInt(params.get('ut_min_price') || '0');
        const urlMax = parseInt(params.get('ut_max_price') || '0');
        if (urlMin > 0) minSlider.value = Math.round(urlMin / 1000);
        if (urlMax > 0) maxSlider.value = Math.round(urlMax / 1000);

        function updateSlider(e) {
            var minVal = parseInt(minSlider.value);
            var maxVal = parseInt(maxSlider.value);

            if (minVal >= maxVal) {
                if (e && e.target && e.target.id === 'min-price') {
                    minSlider.value = maxVal - 1;
                    minVal = maxVal - 1;
                } else {
                    maxSlider.value = minVal + 1;
                    maxVal = minVal + 1;
                }
            }

            var minPercent = (minVal / parseInt(minSlider.max)) * 100;
            var maxPercent = (maxVal / parseInt(maxSlider.max)) * 100;

            if (sliderTrack) {
                sliderTrack.style.left = minPercent + '%';
                sliderTrack.style.right = (100 - maxPercent) + '%';
            }
            if (minTooltip) {
                minTooltip.style.left = minPercent + '%';
                minTooltip.innerText = minVal + ' K';
            }
            if (maxTooltip) {
                maxTooltip.style.left = maxPercent + '%';
                maxTooltip.innerText = maxVal + ' K';
            }
            if (odooMin) odooMin.value = minVal * 1000;
            if (odooMax) odooMax.value = maxVal * 1000;
        }

        minSlider.addEventListener('input', updateSlider);
        maxSlider.addEventListener('input', updateSlider);
        updateSlider(); // Initial render
    }

    // ─────────────────────────────────────────────
    // 2. SORT BAR — Make pills interactive
    // ─────────────────────────────────────────────
    const sortBar = document.getElementById('ut-sort-bar');
    const currentSort = params.get('sort') || 'terkait';

    if (sortBar) {
        var pills = sortBar.querySelectorAll('[data-sort]');
        pills.forEach(function (pill) {
            var sortKey = pill.getAttribute('data-sort');

            // Highlight active
            if (sortKey === currentSort) {
                pill.classList.add('tw-bg-[#1a1a1a]', 'tw-text-white', 'tw-shadow-sm', 'tw-font-semibold');
                pill.classList.remove('tw-text-gray-600');
            } else {
                pill.classList.remove('tw-bg-[#1a1a1a]', 'tw-text-white', 'tw-shadow-sm', 'tw-font-semibold');
                pill.classList.add('tw-text-gray-600');
            }

            pill.addEventListener('click', function () {
                var p = new URLSearchParams(window.location.search);
                p.set('sort', sortKey);
                window.location.href = '/shop?' + p.toString();
            });
        });
    }

    // ─────────────────────────────────────────────
    // 3. "SIMPAN" BUTTON — Collect filter state & navigate
    // ─────────────────────────────────────────────
    var simpanBtn = document.getElementById('ut-btn-simpan');
    if (simpanBtn) {
        simpanBtn.addEventListener('click', function (e) {
            e.preventDefault();

            var p = new URLSearchParams();

            // Keep existing search term
            var search = params.get('search');
            if (search) p.set('search', search);

            // Keep existing sort
            var sort = params.get('sort');
            if (sort) p.set('sort', sort);

            // Lokasi
            var lokasiChecked = document.querySelector('input[name="lokasi"]:checked');
            if (lokasiChecked && lokasiChecked.value) {
                p.set('lokasi', lokasiChecked.value);
            }

            // Price
            var minP = odooMin ? parseInt(odooMin.value) : 0;
            var maxP = odooMax ? parseInt(odooMax.value) : 0;
            if (minP > 0) p.set('ut_min_price', minP);
            if (maxP > 0) p.set('ut_max_price', maxP);

            // Kondisi
            var kondisiChecked = document.querySelector('input[name="kondisi"]:checked');
            if (kondisiChecked && kondisiChecked.value) {
                var kondisiMap = { 'baru': 'new', 'bekas': 'used' };
                p.set('kondisi', kondisiMap[kondisiChecked.value] || kondisiChecked.value);
            }

            window.location.href = '/shop?' + p.toString();
        });
    }

    // ─────────────────────────────────────────────
    // 4. "BATAL" BUTTON — Revert to current URL state (cancel pending changes)
    // ─────────────────────────────────────────────
    var batalBtn = document.getElementById('ut-btn-batal');
    if (batalBtn) {
        batalBtn.addEventListener('click', function () {
            window.location.reload();
        });
    }

    // ─────────────────────────────────────────────
    // 5. "RESET FILTERS" BUTTON — Clear all filters
    // ─────────────────────────────────────────────
    var resetBtn = document.getElementById('ut-btn-reset');
    if (resetBtn) {
        resetBtn.addEventListener('click', function () {
            var p = new URLSearchParams();
            // Keep search term only
            var search = params.get('search');
            if (search) p.set('search', search);
            var qs = p.toString();
            window.location.href = '/shop' + (qs ? '?' + qs : '');
        });
    }
});
