/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

const MAX_PRICE_K = 5000;
const MIN_GAP_K = 10;
const DEFAULT_LAT = -7.7956;
const DEFAULT_LON = 110.3695;

function intOrDefault(value, fallback) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function floatOrDefault(value, fallback) {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeKondisi(value) {
    const map = { new: "baru", used: "bekas" };
    return map[value] || value || "";
}

function toServerKondisi(value) {
    const map = { baru: "new", bekas: "used" };
    return map[value] || value || "";
}

export class UnitradeShopFilter extends Component {
    static template = "unitrade_theme.ShopFilter";
    static props = {
        initialResultsHtml: { type: String, optional: true },
        search: { type: String, optional: true },
        categoryId: { type: String, optional: true },
        ppg: { type: String, optional: true },
    };
    static defaultProps = {
        initialResultsHtml: "",
        search: "",
        categoryId: "",
        ppg: "",
    };

    setup() {
        this.resultsRef = useRef("results");
        this.requestSeq = 0;
        this.onPopState = () => this.restoreFromUrl({ load: true });
        this.basePath = window.location.pathname.replace(/\/page\/\d+\/?$/, "") || "/shop";

        this.state = useState(this._stateFromCurrentUrl());

        onMounted(() => {
            this._writeResultsHtml();
            window.addEventListener("popstate", this.onPopState);
        });

        onWillUnmount(() => {
            window.removeEventListener("popstate", this.onPopState);
        });

        useEffect(
            () => {
                this._writeResultsHtml();
            },
            () => [this.state.resultsHtml]
        );
    }

    _stateFromCurrentUrl() {
        const params = new URLSearchParams(window.location.search);
        const minPrice = intOrDefault(params.get("ut_min_price"), 0);
        const maxPrice = intOrDefault(params.get("ut_max_price"), 0);
        return {
            lokasi: params.get("lokasi") || "",
            kondisi: normalizeKondisi(params.get("kondisi")),
            sort: params.get("sort") || "terkait",
            minK: minPrice > 0 ? Math.round(minPrice / 1000) : 0,
            maxK: maxPrice > 0 ? Math.round(maxPrice / 1000) : MAX_PRICE_K,
            userLat: floatOrDefault(params.get("lat"), 0),
            userLon: floatOrDefault(params.get("lon"), 0),
            loading: false,
            geoLoading: false,
            resultsHtml: this.props.initialResultsHtml,
        };
    }

    _applyStateFromUrl() {
        const next = this._stateFromCurrentUrl();
        this.state.lokasi = next.lokasi;
        this.state.kondisi = next.kondisi;
        this.state.sort = next.sort;
        this.state.minK = next.minK;
        this.state.maxK = next.maxK;
        this.state.userLat = next.userLat;
        this.state.userLon = next.userLon;
    }

    _writeResultsHtml() {
        if (this.resultsRef.el) {
            this.resultsRef.el.innerHTML = this.state.resultsHtml || "";
        }
    }

    get minPct() {
        return (this.state.minK / MAX_PRICE_K) * 100;
    }

    get maxPct() {
        return (this.state.maxK / MAX_PRICE_K) * 100;
    }

    get trackStyle() {
        return [
            "position:absolute",
            "top:50%",
            "transform:translateY(-50%)",
            "height:10px",
            "background:#d0d0d0",
            "border-radius:999px",
            "z-index:2",
            "pointer-events:none",
            `left:${this.minPct}%`,
            `right:${100 - this.maxPct}%`,
        ].join(";") + ";";
    }

    get minTooltipStyle() {
        return [
            "position:absolute",
            "top:100%",
            "margin-top:4px",
            "z-index:5",
            "pointer-events:none",
            "transform:translateX(-50%)",
            `left:${this.minPct}%`,
        ].join(";") + ";";
    }

    get maxTooltipStyle() {
        return [
            "position:absolute",
            "bottom:100%",
            "margin-bottom:4px",
            "z-index:5",
            "pointer-events:none",
            "transform:translateX(-50%)",
            `left:${this.maxPct}%`,
        ].join(";") + ";";
    }

    formatK(valueK) {
        if (valueK >= 1000) {
            const jt = valueK / 1000;
            return `${jt % 1 === 0 ? jt.toFixed(0) : jt.toFixed(1)} Jt`;
        }
        return `${valueK} K`;
    }

    pillClass(group, value) {
        const active = this.state[group] === value;
        const loading = group === "lokasi" && value === "terdekat" && this.state.geoLoading;
        return [
            "ut-pill",
            active ? "ut-pill-active" : "ut-pill-inactive",
            loading ? "ut-pill-loading" : "",
        ].filter(Boolean).join(" ");
    }

    sortClass(value) {
        const base = "tw-px-5 tw-h-[36px] tw-rounded-full tw-font-['Urbanist'] tw-text-[14px] tw-flex tw-items-center tw-justify-center tw-cursor-pointer tw-transition-colors";
        if (this.state.sort === value) {
            return `${base} tw-bg-[#1a1a1a] tw-text-white tw-font-semibold`;
        }
        return `${base} tw-font-medium tw-text-gray-600 hover:tw-bg-gray-100 hover:tw-text-black`;
    }

    togglePill(group, value) {
        this.state[group] = this.state[group] === value ? "" : value;
        if (group === "lokasi" && this.state.lokasi === "terdekat") {
            this.requestGeolocation({ alertOnDenied: false });
        }
    }

    onMinInput(ev) {
        let value = intOrDefault(ev.target.value, 0);
        if (value >= this.state.maxK) {
            value = Math.max(0, this.state.maxK - MIN_GAP_K);
        }
        this.state.minK = value;
    }

    onMaxInput(ev) {
        let value = intOrDefault(ev.target.value, MAX_PRICE_K);
        if (value <= this.state.minK) {
            value = Math.min(MAX_PRICE_K, this.state.minK + MIN_GAP_K);
        }
        this.state.maxK = value;
    }

    async changeSort(sortKey) {
        this.state.sort = sortKey;
        await this.loadResults({ page: 0 });
    }

    async applyFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        await this.loadResults({ page: 0 });
    }

    async resetFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.state.lokasi = "";
        this.state.kondisi = "";
        this.state.sort = "terkait";
        this.state.minK = 0;
        this.state.maxK = MAX_PRICE_K;
        this.state.userLat = 0;
        this.state.userLon = 0;
        await this.loadResults({ page: 0 });
    }

    async restoreFromUrl(options = {}) {
        this._applyStateFromUrl();
        if (options.load) {
            await this.loadResults({ page: this._pageFromCurrentPath(), replace: true });
        }
    }

    async requestGeolocation(options = {}) {
        if (!navigator.geolocation) {
            this.state.userLat = DEFAULT_LAT;
            this.state.userLon = DEFAULT_LON;
            if (options.alertOnDenied) {
                window.alert('Browser Anda tidak mendukung Geolocation. Menggunakan lokasi default (Yogyakarta).');
            }
            return;
        }

        this.state.geoLoading = true;
        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000,
                });
            });
            this.state.userLat = position.coords.latitude;
            this.state.userLon = position.coords.longitude;
        } catch (error) {
            this.state.userLat = DEFAULT_LAT;
            this.state.userLon = DEFAULT_LON;
            if (options.alertOnDenied && error && error.code === 1) {
                window.alert("Izin lokasi ditolak. Menggunakan lokasi default (Yogyakarta).");
            }
        } finally {
            this.state.geoLoading = false;
        }
    }

    _buildParams() {
        const params = new URLSearchParams();
        const search = this.props.search || new URLSearchParams(window.location.search).get("search") || "";
        if (search) {
            params.set("search", search);
        }
        if (this.state.sort && this.state.sort !== "terkait") {
            params.set("sort", this.state.sort);
        }
        if (this.state.lokasi) {
            params.set("lokasi", this.state.lokasi);
        }
        if (this.state.lokasi === "terdekat" && this.state.userLat && this.state.userLon) {
            params.set("lat", this.state.userLat.toFixed(6));
            params.set("lon", this.state.userLon.toFixed(6));
        }
        if (this.state.minK > 0) {
            params.set("ut_min_price", String(this.state.minK * 1000));
        }
        if (this.state.maxK < MAX_PRICE_K) {
            params.set("ut_max_price", String(this.state.maxK * 1000));
        }
        if (this.state.kondisi) {
            params.set("kondisi", toServerKondisi(this.state.kondisi));
        }
        return params;
    }

    _payloadFromParams(params, page) {
        const payload = Object.fromEntries(params.entries());
        payload.page = page || 0;
        payload.search = this.props.search || payload.search || "";
        payload.category_id = this.props.categoryId || "";
        payload.ppg = this.props.ppg || "";
        return payload;
    }

    async loadResults(options = {}) {
        if (this.state.loading) {
            return;
        }
        if (this.state.lokasi === "terdekat" && (!this.state.userLat || !this.state.userLon)) {
            await this.requestGeolocation({ alertOnDenied: true });
        }

        const page = options.page || 0;
        const params = this._buildParams();
        const payload = this._payloadFromParams(params, page);
        const requestId = ++this.requestSeq;

        this.state.loading = true;
        try {
            const result = await jsonrpc("/unitrade/shop/filter", payload);
            if (requestId !== this.requestSeq) {
                return;
            }
            if (result.error) {
                throw new Error(result.error);
            }
            this.state.resultsHtml = result.html || "";
            this._updateUrl(params, page, options.replace);
        } catch (error) {
            console.error("UniTrade shop filter error:", error);
            window.alert("Filter belum bisa dimuat. Silakan coba lagi.");
        } finally {
            if (requestId === this.requestSeq) {
                this.state.loading = false;
            }
        }
    }

    async onResultsClick(ev) {
        const pagerLink = ev.target.closest(".products_pager a[href]");
        if (pagerLink) {
            ev.preventDefault();
            const page = this._pageFromHref(pagerLink.href);
            await this.loadResults({ page });
        }
    }

    _pageFromHref(href) {
        const url = new URL(href, window.location.origin);
        const match = url.pathname.match(/\/page\/(\d+)\/?$/);
        if (match) {
            return intOrDefault(match[1], 0);
        }
        return intOrDefault(url.searchParams.get("page"), 0);
    }

    _pageFromCurrentPath() {
        const match = window.location.pathname.match(/\/page\/(\d+)\/?$/);
        return match ? intOrDefault(match[1], 0) : 0;
    }

    _updateUrl(params, page, replace = false) {
        let path = this.basePath || "/shop";
        if (page) {
            path = `${path.replace(/\/$/, "")}/page/${page}`;
        }
        const query = params.toString();
        const url = `${path}${query ? `?${query}` : ""}`;
        const method = replace ? "replaceState" : "pushState";
        window.history[method]({}, "", url);
    }
}

publicWidget.registry.UnitradeShopFilter = publicWidget.Widget.extend({
    selector: "#ut-shop-owl-mount",

    async start() {
        const superPromise = this._super.apply(this, arguments);
        const results = this.el.querySelector("#ut-shop-results");
        const props = {
            initialResultsHtml: results ? results.innerHTML : "",
            search: this.el.dataset.search || "",
            categoryId: this.el.dataset.categoryId || "",
            ppg: this.el.dataset.ppg || "",
        };

        this.el.innerHTML = "";
        this.component = await mount(UnitradeShopFilter, this.el, { props, templates });
        return superPromise;
    },

    destroy() {
        if (this.component && this.component.destroy) {
            this.component.destroy();
        }
        this._super.apply(this, arguments);
    },
});
