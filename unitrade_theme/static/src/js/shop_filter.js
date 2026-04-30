/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.UnitradeShopFilter = publicWidget.Widget.extend({
    selector: '.o_wsale_products_main_row',
    events: {
        'click #ut-btn-simpan': '_onSimpan',
        'click #ut-btn-batal': '_onBatal',
        'click #ut-btn-reset': '_onReset',
        'input #min-price': '_onSliderInput',
        'input #max-price': '_onSliderInput',
        'click [data-sort]': '_onSort',
        'click .ut-pill': '_onPillClick',
    },

    start() {
        this.params = new URLSearchParams(window.location.search);
        this.minSlider = this.el.querySelector('#min-price');
        this.maxSlider = this.el.querySelector('#max-price');
        this.minTooltip = this.el.querySelector('#min-tooltip');
        this.maxTooltip = this.el.querySelector('#max-tooltip');
        this.sliderTrack = this.el.querySelector('#slider-track');
        this.odooMin = this.el.querySelector('#odoo-min-price');
        this.odooMax = this.el.querySelector('#odoo-max-price');
        this.lokasiInput = this.el.querySelector('#ut-lokasi-val');
        this.kondisiInput = this.el.querySelector('#ut-kondisi-val');
        // Store user geolocation if available
        this.userLat = parseFloat(this.params.get('lat') || '0');
        this.userLon = parseFloat(this.params.get('lon') || '0');
        this._restoreFilters();
        this._updateSlider();
        return this._super.apply(this, arguments);
    },

    // ─── PILL TOGGLE (Lokasi & Kondisi) ─────────────────────
    _onPillClick(ev) {
        var pill = ev.currentTarget;
        var group = pill.getAttribute('data-group');
        var value = pill.getAttribute('data-value');

        // Find all pills in same group
        var siblings = this.el.querySelectorAll('.ut-pill[data-group="' + group + '"]');
        for (var i = 0; i < siblings.length; i++) {
            siblings[i].classList.remove('ut-pill-active');
            siblings[i].classList.add('ut-pill-inactive');
        }

        // Toggle: if clicking already-selected, deselect
        var hiddenInput = this.el.querySelector('#ut-' + group + '-val');
        if (hiddenInput && hiddenInput.value === value) {
            hiddenInput.value = '';
        } else {
            pill.classList.remove('ut-pill-inactive');
            pill.classList.add('ut-pill-active');
            if (hiddenInput) hiddenInput.value = value;

            // If "terdekat" selected, request geolocation
            if (group === 'lokasi' && value === 'terdekat') {
                this._requestGeolocation();
            }
        }
    },

    // ─── GEOLOCATION ────────────────────────────────────────
    _requestGeolocation() {
        var self = this;
        if (!navigator.geolocation) {
            alert('Browser Anda tidak mendukung Geolocation. Filter "Terdekat" akan menampilkan semua produk.');
            return;
        }

        // Show loading indicator on the pill
        var pill = this.el.querySelector('.ut-pill[data-value="terdekat"]');
        if (pill) pill.innerText = 'Mencari...';

        navigator.geolocation.getCurrentPosition(
            function(position) {
                self.userLat = position.coords.latitude;
                self.userLon = position.coords.longitude;
                if (pill) pill.innerText = 'Terdekat ✓';
            },
            function(error) {
                // Fallback: use Yogyakarta city center coordinates
                self.userLat = -7.7956;
                self.userLon = 110.3695;
                if (pill) pill.innerText = 'Terdekat';
                var msg = 'Izin lokasi ditolak. Menggunakan lokasi default (Yogyakarta).';
                if (error.code === 1) {
                    // Permission denied
                    alert(msg);
                }
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
        );
    },

    // ─── RESTORE FILTERS ────────────────────────────────────
    _restoreFilters() {
        // Restore lokasi
        var lokasi = this.params.get('lokasi') || '';
        if (lokasi && this.lokasiInput) {
            this.lokasiInput.value = lokasi;
            var pill = this.el.querySelector('.ut-pill[data-group="lokasi"][data-value="' + lokasi + '"]');
            if (pill) {
                pill.classList.remove('ut-pill-inactive');
                pill.classList.add('ut-pill-active');
                if (lokasi === 'terdekat' && this.userLat) {
                    pill.innerText = 'Terdekat ✓';
                }
            }
        }

        // Restore kondisi (URL uses new/used, pills use baru/bekas)
        var kondisi = this.params.get('kondisi') || '';
        if (kondisi && this.kondisiInput) {
            var map = { 'new': 'baru', 'used': 'bekas' };
            var val = map[kondisi] || kondisi;
            this.kondisiInput.value = val;
            var kpill = this.el.querySelector('.ut-pill[data-group="kondisi"][data-value="' + val + '"]');
            if (kpill) {
                kpill.classList.remove('ut-pill-inactive');
                kpill.classList.add('ut-pill-active');
            }
        }

        // Restore price slider from URL
        if (this.minSlider && this.maxSlider) {
            var urlMin = parseInt(this.params.get('ut_min_price') || '0');
            var urlMax = parseInt(this.params.get('ut_max_price') || '0');
            if (urlMin > 0) this.minSlider.value = Math.round(urlMin / 1000);
            if (urlMax > 0) this.maxSlider.value = Math.round(urlMax / 1000);
        }

        // Restore sort highlight
        var sort = this.params.get('sort') || 'terkait';
        var pills = this.el.querySelectorAll('[data-sort]');
        for (var j = 0; j < pills.length; j++) {
            if (pills[j].getAttribute('data-sort') === sort) {
                pills[j].style.backgroundColor = '#1a1a1a';
                pills[j].style.color = '#fff';
                pills[j].style.fontWeight = '600';
            }
        }
    },

    // ─── SLIDER ─────────────────────────────────────────────
    _onSliderInput(ev) { this._updateSlider(ev); },

    _updateSlider(ev) {
        if (!this.minSlider || !this.maxSlider) return;
        var minVal = parseInt(this.minSlider.value);
        var maxVal = parseInt(this.maxSlider.value);
        if (minVal >= maxVal) {
            if (ev && ev.target && ev.target.id === 'min-price') {
                this.minSlider.value = maxVal - 10; minVal = maxVal - 10;
            } else {
                this.maxSlider.value = minVal + 10; maxVal = minVal + 10;
            }
        }
        var sliderMax = parseInt(this.minSlider.max);
        var minPct = (minVal / sliderMax) * 100;
        var maxPct = (maxVal / sliderMax) * 100;
        if (this.sliderTrack) {
            this.sliderTrack.style.left = minPct + '%';
            this.sliderTrack.style.right = (100 - maxPct) + '%';
        }
        if (this.minTooltip) {
            this.minTooltip.style.left = minPct + '%';
            this.minTooltip.innerText = this._formatK(minVal);
        }
        if (this.maxTooltip) {
            this.maxTooltip.style.left = maxPct + '%';
            this.maxTooltip.innerText = this._formatK(maxVal);
        }
        if (this.odooMin) this.odooMin.value = minVal * 1000;
        if (this.odooMax) this.odooMax.value = maxVal * 1000;
    },

    _formatK(valK) {
        if (valK >= 1000) {
            var jt = valK / 1000;
            return (jt % 1 === 0 ? jt.toFixed(0) : jt.toFixed(1)) + ' Jt';
        }
        return valK + ' K';
    },

    // ─── SORT ───────────────────────────────────────────────
    _onSort(ev) {
        var sortKey = ev.currentTarget.getAttribute('data-sort');
        var p = new URLSearchParams(window.location.search);
        p.set('sort', sortKey);
        window.location.href = '/shop?' + p.toString();
    },

    // ─── SIMPAN ─────────────────────────────────────────────
    _onSimpan(ev) {
        ev.preventDefault();
        var p = new URLSearchParams();
        var s = this.params.get('search');
        if (s) p.set('search', s);
        var so = this.params.get('sort');
        if (so) p.set('sort', so);

        // Lokasi
        var lokasi = this.lokasiInput ? this.lokasiInput.value : '';
        if (lokasi) p.set('lokasi', lokasi);

        // If terdekat, include coordinates
        if (lokasi === 'terdekat') {
            if (this.userLat && this.userLon) {
                p.set('lat', this.userLat.toFixed(6));
                p.set('lon', this.userLon.toFixed(6));
            } else {
                // Try to get geolocation synchronously-ish
                var self = this;
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(
                        function(pos) {
                            p.set('lat', pos.coords.latitude.toFixed(6));
                            p.set('lon', pos.coords.longitude.toFixed(6));
                            self._navigateWithParams(p);
                        },
                        function() {
                            // Fallback to Yogyakarta
                            p.set('lat', '-7.795600');
                            p.set('lon', '110.369500');
                            self._navigateWithParams(p);
                        },
                        { timeout: 5000 }
                    );
                    return; // Wait for async geolocation
                }
            }
        }

        // Price
        var mnP = this.odooMin ? parseInt(this.odooMin.value) : 0;
        var mxP = this.odooMax ? parseInt(this.odooMax.value) : 0;
        if (mnP > 0) p.set('ut_min_price', mnP);
        if (mxP > 0 && mxP < 5000000) p.set('ut_max_price', mxP);

        // Kondisi (baru→new, bekas→used)
        var kondisi = this.kondisiInput ? this.kondisiInput.value : '';
        if (kondisi) {
            var km = { 'baru': 'new', 'bekas': 'used' };
            p.set('kondisi', km[kondisi] || kondisi);
        }

        this._navigateWithParams(p);
    },

    _navigateWithParams(p) {
        window.location.href = '/shop?' + p.toString();
    },

    // ─── BATAL & RESET ──────────────────────────────────────
    _onBatal() { window.location.reload(); },

    _onReset() {
        var p = new URLSearchParams();
        var s = this.params.get('search');
        if (s) p.set('search', s);
        var qs = p.toString();
        window.location.href = '/shop' + (qs ? '?' + qs : '');
    },
});
