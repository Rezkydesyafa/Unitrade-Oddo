/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

const MAX_PRICE_K = 10000;
const MIN_GAP_K = 10;
const AUTO_APPLY_DELAY_MS = 500;
const DEFAULT_LAT = -7.7956;
const DEFAULT_LON = 110.3695;
const SORT_KEYS = new Set(["terkait", "terlaris", "terbaru", "termurah", "termahal"]);
const LOCATION_KEYS = new Set(["terdekat", "kabupaten", "diy"]);

function intOrDefault(value, fallback) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function floatOrDefault(value, fallback) {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function clampK(value, fallback = 0) {
    return Math.min(Math.max(intOrDefault(value, fallback), 0), MAX_PRICE_K);
}

function normalizeKondisi(value) {
    const map = { new: "baru", used: "bekas" };
    return map[value] || value || "";
}

function toServerKondisi(value) {
    const map = { baru: "new", bekas: "used" };
    return map[value] || value || "";
}

function cloneFilterState(state) {
    return {
        lokasi: state.lokasi || "",
        kondisi: state.kondisi || "",
        sort: SORT_KEYS.has(state.sort) ? state.sort : "terkait",
        minK: clampK(state.minK, 0),
        maxK: clampK(state.maxK, MAX_PRICE_K),
        userLat: floatOrDefault(state.userLat, 0),
        userLon: floatOrDefault(state.userLon, 0),
    };
}

export class UnitradeShopFilter extends Component {
    static template = "unitrade_theme.ShopFilter";
    static props = {
        initialResultsHtml: { type: String, optional: true },
        search: { type: String, optional: true },
        categoryId: { type: String, optional: true },
        ppg: { type: String, optional: true },
        initialSearchCount: { type: String, optional: true },
        initialPage: { type: String, optional: true },
        initialPageCount: { type: String, optional: true },
        initialHasMore: { type: String, optional: true },
        initialNextPage: { type: String, optional: true },
    };
    static defaultProps = {
        initialResultsHtml: "",
        search: "",
        categoryId: "",
        ppg: "",
        initialSearchCount: "0",
        initialPage: "1",
        initialPageCount: "0",
        initialHasMore: "false",
        initialNextPage: "",
    };

    setup() {
        this.resultsRef = useRef("results");
        this.sentinelRef = useRef("sentinel");
        this.requestSeq = 0;
        this.basePath = this._basePathFromLocation();
        this.observer = null;
        this.autoApplyTimer = null;
        this.onPopState = () => this.restoreFromUrl({ load: true });

        const currentFilters = this._filterStateFromCurrentUrl();
        const initialPage = intOrDefault(this.props.initialPage, this._pageFromCurrentPath());
        const initialPageCount = intOrDefault(this.props.initialPageCount, 0);
        const initialNextPage = intOrDefault(this.props.initialNextPage, 0);

        this.state = useState({
            draft: cloneFilterState(currentFilters),
            applied: cloneFilterState(currentFilters),
            loading: false,
            loadingMore: false,
            geoLoading: false,
            resultsHtml: this.props.initialResultsHtml,
            searchCount: intOrDefault(this.props.initialSearchCount, 0),
            page: initialPage,
            pageCount: initialPageCount,
            hasMore: this.props.initialHasMore === "true" || (initialPageCount > 0 && initialPage < initialPageCount),
            nextPage: initialNextPage || (initialPageCount > initialPage ? initialPage + 1 : 0),
        });

        onMounted(() => {
            this._writeResultsHtml();
            this._setupInfiniteScroll();
            window.addEventListener("popstate", this.onPopState);
        });

        onWillUnmount(() => {
            window.removeEventListener("popstate", this.onPopState);
            this._clearAutoApplyTimer();
            if (this.observer) {
                this.observer.disconnect();
            }
        });

        useEffect(
            () => {
                this._writeResultsHtml();
            },
            () => [this.state.resultsHtml]
        );
    }

    _defaultFilterState() {
        return {
            lokasi: "",
            kondisi: "",
            sort: "terkait",
            minK: 0,
            maxK: MAX_PRICE_K,
            userLat: 0,
            userLon: 0,
        };
    }

    _basePathFromLocation() {
        return window.location.pathname.replace(/\/page\/\d+\/?$/, "") || "/shop";
    }

    _filterStateFromCurrentUrl() {
        const params = new URLSearchParams(window.location.search);
        const minPrice = intOrDefault(params.get("ut_min_price"), 0);
        const maxPrice = intOrDefault(params.get("ut_max_price"), 0);
        const minK = minPrice > 0 ? clampK(Math.round(minPrice / 1000), 0) : 0;
        let maxK = maxPrice > 0 ? clampK(Math.round(maxPrice / 1000), MAX_PRICE_K) : MAX_PRICE_K;
        if (maxK <= minK) {
            maxK = Math.min(MAX_PRICE_K, minK + MIN_GAP_K);
        }
        const lokasi = params.get("lokasi") || "";
        const sort = params.get("sort") || "terkait";
        return {
            lokasi: LOCATION_KEYS.has(lokasi) ? lokasi : "",
            kondisi: normalizeKondisi(params.get("kondisi")),
            sort: SORT_KEYS.has(sort) ? sort : "terkait",
            minK,
            maxK,
            userLat: floatOrDefault(params.get("lat"), 0),
            userLon: floatOrDefault(params.get("lon"), 0),
        };
    }

    _setDraft(next) {
        Object.assign(this.state.draft, cloneFilterState(next));
    }

    _setApplied(next) {
        Object.assign(this.state.applied, cloneFilterState(next));
    }

    _writeResultsHtml() {
        if (this.resultsRef.el) {
            this.resultsRef.el.innerHTML = this.state.resultsHtml || "";
        }
    }

    _setupInfiniteScroll() {
        if (!this.sentinelRef.el || !("IntersectionObserver" in window)) {
            return;
        }
        this.observer = new IntersectionObserver((entries) => {
            const visible = entries.some((entry) => entry.isIntersecting);
            if (visible) {
                this.loadMore();
            }
        }, { rootMargin: "600px 0px" });
        this.observer.observe(this.sentinelRef.el);
    }

    get minPct() {
        return (this.state.draft.minK / MAX_PRICE_K) * 100;
    }

    get maxPct() {
        return (this.state.draft.maxK / MAX_PRICE_K) * 100;
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
        const active = this.state.draft[group] === value;
        const loading = group === "lokasi" && value === "terdekat" && this.state.geoLoading;
        return [
            "ut-pill",
            active ? "ut-pill-active" : "ut-pill-inactive",
            loading ? "ut-pill-loading" : "",
        ].filter(Boolean).join(" ");
    }

    sortClass(value) {
        const base = "tw-px-5 tw-h-[36px] tw-rounded-full tw-font-['Urbanist'] tw-text-[14px] tw-flex tw-items-center tw-justify-center tw-cursor-pointer tw-transition-colors";
        if (this.state.applied.sort === value) {
            return `${base} tw-bg-[#1a1a1a] tw-text-white tw-font-semibold`;
        }
        return `${base} tw-font-medium tw-text-gray-600 hover:tw-bg-gray-100 hover:tw-text-black`;
    }

    _clearAutoApplyTimer() {
        if (this.autoApplyTimer) {
            window.clearTimeout(this.autoApplyTimer);
            this.autoApplyTimer = null;
        }
    }

    _scheduleAutoApply() {
        this._clearAutoApplyTimer();
        this.autoApplyTimer = window.setTimeout(() => {
            this.autoApplyTimer = null;
            this._autoApplyFilters({ replace: true });
        }, AUTO_APPLY_DELAY_MS);
    }

    async _autoApplyFilters(options = {}) {
        this._clearAutoApplyTimer();
        return this.loadResults({
            filterState: cloneFilterState(this.state.draft),
            page: 1,
            replace: options.replace !== false,
            commitApplied: true,
            syncDraft: true,
        });
    }

    async togglePill(group, value) {
        this.state.draft[group] = this.state.draft[group] === value ? "" : value;
        if (group === "lokasi" && this.state.draft.lokasi === "terdekat") {
            const position = await this.requestGeolocation({ alertOnDenied: false });
            this.state.draft.userLat = position.lat;
            this.state.draft.userLon = position.lon;
        }
        await this._autoApplyFilters({ replace: true });
    }

    onMinInput(ev) {
        let value = clampK(ev.target.value, 0);
        if (value >= this.state.draft.maxK) {
            value = Math.max(0, this.state.draft.maxK - MIN_GAP_K);
        }
        this.state.draft.minK = value;
        ev.target.value = value;
        this._scheduleAutoApply();
    }

    onMaxInput(ev) {
        let value = clampK(ev.target.value, MAX_PRICE_K);
        if (value <= this.state.draft.minK) {
            value = Math.min(MAX_PRICE_K, this.state.draft.minK + MIN_GAP_K);
        }
        this.state.draft.maxK = value;
        ev.target.value = value;
        this._scheduleAutoApply();
    }

    async changeSort(sortKey) {
        this._clearAutoApplyTimer();
        const nextApplied = cloneFilterState({ ...this.state.draft, sort: sortKey });
        const success = await this.loadResults({
            filterState: nextApplied,
            page: 1,
            replace: true,
            commitApplied: true,
            syncDraft: true,
        });
        if (success) {
            this.state.draft.sort = sortKey;
        }
    }

    async resetFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this._clearAutoApplyTimer();
        const defaults = this._defaultFilterState();
        await this.loadResults({
            filterState: defaults,
            page: 1,
            replace: true,
            commitApplied: true,
            syncDraft: true,
        });
    }

    async restoreFromUrl(options = {}) {
        this._clearAutoApplyTimer();
        const next = this._filterStateFromCurrentUrl();
        this.basePath = this._basePathFromLocation();
        this._setDraft(next);
        this._setApplied(next);
        if (options.load) {
            await this.loadResults({
                filterState: next,
                page: this._pageFromCurrentPath(),
                replace: true,
                commitApplied: true,
                syncDraft: true,
            });
        }
    }

    async requestGeolocation(options = {}) {
        if (!navigator.geolocation) {
            if (options.alertOnDenied) {
                window.alert("Browser Anda tidak mendukung Geolocation. Menggunakan lokasi default (Yogyakarta).");
            }
            return { lat: DEFAULT_LAT, lon: DEFAULT_LON };
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
            return {
                lat: position.coords.latitude,
                lon: position.coords.longitude,
            };
        } catch (error) {
            if (options.alertOnDenied && error && error.code === 1) {
                window.alert("Izin lokasi ditolak. Menggunakan lokasi default (Yogyakarta).");
            }
            return { lat: DEFAULT_LAT, lon: DEFAULT_LON };
        } finally {
            this.state.geoLoading = false;
        }
    }

    async _ensureLocation(filterState, options = {}) {
        if (filterState.lokasi !== "terdekat" || (filterState.userLat && filterState.userLon)) {
            return filterState;
        }
        const position = await this.requestGeolocation(options);
        filterState.userLat = position.lat;
        filterState.userLon = position.lon;
        if (this.state.draft.lokasi === "terdekat") {
            this.state.draft.userLat = position.lat;
            this.state.draft.userLon = position.lon;
        }
        return filterState;
    }

    _currentSearch() {
        return new URLSearchParams(window.location.search).get("search") || this.props.search || "";
    }

    _buildParams(filterState) {
        const state = cloneFilterState(filterState);
        const params = new URLSearchParams();
        const search = this._currentSearch();
        if (search) {
            params.set("search", search);
        }
        if (state.sort && state.sort !== "terkait") {
            params.set("sort", state.sort);
        }
        if (state.lokasi) {
            params.set("lokasi", state.lokasi);
        }
        if (state.lokasi === "terdekat" && state.userLat && state.userLon) {
            params.set("lat", state.userLat.toFixed(6));
            params.set("lon", state.userLon.toFixed(6));
        }
        if (state.minK > 0) {
            params.set("ut_min_price", String(state.minK * 1000));
        }
        if (state.maxK < MAX_PRICE_K) {
            params.set("ut_max_price", String(state.maxK * 1000));
        }
        if (state.kondisi) {
            params.set("kondisi", toServerKondisi(state.kondisi));
        }
        return params;
    }

    _payloadFromParams(params, page) {
        const payload = Object.fromEntries(params.entries());
        payload.page = page || 1;
        payload.search = this._currentSearch();
        payload.category_id = this.props.categoryId || "";
        payload.ppg = this.props.ppg || "";
        return payload;
    }

    async loadResults(options = {}) {
        const append = Boolean(options.append);
        if (append && (this.state.loadingMore || this.state.loading || !this.state.hasMore || !this.state.nextPage)) {
            return false;
        }

        const filterState = cloneFilterState(options.filterState || this.state.applied);
        await this._ensureLocation(filterState, { alertOnDenied: true });

        const page = options.page || 1;
        const params = this._buildParams(filterState);
        const payload = this._payloadFromParams(params, page);
        const requestId = ++this.requestSeq;

        if (append) {
            this.state.loadingMore = true;
        } else {
            this.state.loading = true;
        }

        try {
            const result = await jsonrpc("/unitrade/shop/filter", payload);
            if (requestId !== this.requestSeq) {
                return false;
            }
            if (result.error) {
                throw new Error(result.error);
            }

            if (append) {
                this._appendResultsHtml(result.html || "");
            } else {
                this.state.resultsHtml = result.html || "";
            }
            this._applyResultMeta(result);
            this._updateUrl(params, result.page || page, options.replace);

            if (options.commitApplied) {
                this._setApplied(filterState);
            }
            if (options.syncDraft) {
                this._setDraft(filterState);
            }
            return true;
        } catch (error) {
            console.error("UniTrade shop filter error:", error);
            window.alert("Filter belum bisa dimuat. Silakan coba lagi.");
            return false;
        } finally {
            if (requestId === this.requestSeq) {
                this.state.loading = false;
                this.state.loadingMore = false;
            }
        }
    }

    _applyResultMeta(result) {
        this.state.searchCount = intOrDefault(result.search_count, 0);
        this.state.page = intOrDefault(result.page, 1);
        this.state.pageCount = intOrDefault(result.page_count, 0);
        this.state.hasMore = Boolean(result.has_more);
        this.state.nextPage = intOrDefault(result.next_page, 0);
    }

    _appendResultsHtml(html) {
        if (!this.resultsRef.el || !html) {
            return;
        }
        const template = document.createElement("template");
        template.innerHTML = html;
        const currentGrid = this.resultsRef.el.querySelector(".ut-product-card-grid");
        const nextGrid = template.content.querySelector(".ut-product-card-grid");
        if (!currentGrid || !nextGrid) {
            this.state.resultsHtml = html;
            return;
        }

        Array.from(nextGrid.children).forEach((child) => currentGrid.appendChild(child));

        const currentPager = this.resultsRef.el.querySelector(".products_pager");
        const nextPager = template.content.querySelector(".products_pager");
        if (currentPager && nextPager) {
            currentPager.replaceWith(nextPager);
        } else if (currentPager) {
            currentPager.remove();
        } else if (nextPager) {
            this.resultsRef.el.appendChild(nextPager);
        }
        this.state.resultsHtml = this.resultsRef.el.innerHTML;
    }

    async loadMore() {
        await this.loadResults({
            filterState: cloneFilterState(this.state.applied),
            page: this.state.nextPage,
            append: true,
            replace: true,
        });
    }

    async onResultsClick(ev) {
        const pagerLink = ev.target.closest(".products_pager a[href]");
        if (pagerLink) {
            ev.preventDefault();
            const page = this._pageFromHref(pagerLink.href);
            await this.loadResults({
                filterState: cloneFilterState(this.state.applied),
                page,
            });
        }
    }

    _pageFromHref(href) {
        const url = new URL(href, window.location.origin);
        const match = url.pathname.match(/\/page\/(\d+)\/?$/);
        if (match) {
            return intOrDefault(match[1], 1);
        }
        return intOrDefault(url.searchParams.get("page"), 1);
    }

    _pageFromCurrentPath() {
        const match = window.location.pathname.match(/\/page\/(\d+)\/?$/);
        return match ? intOrDefault(match[1], 1) : 1;
    }

    _updateUrl(params, page, replace = false) {
        let path = this.basePath || "/shop";
        if (page && page > 1) {
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
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const results = this.el.querySelector("#ut-shop-results");
        const fallbackHtml = this.el.innerHTML;
        const props = {
            initialResultsHtml: results ? results.innerHTML : "",
            search: this.el.dataset.search || "",
            categoryId: this.el.dataset.categoryId || "",
            ppg: this.el.dataset.ppg || "",
            initialSearchCount: this.el.dataset.searchCount || "0",
            initialPage: this.el.dataset.page || "1",
            initialPageCount: this.el.dataset.pageCount || "0",
            initialHasMore: this.el.dataset.hasMore || "false",
            initialNextPage: this.el.dataset.nextPage || "",
        };

        try {
            this.el.innerHTML = "";
            this.component = await mount(UnitradeShopFilter, this.el, { props, templates });
        } catch (error) {
            console.error("UniTrade shop filter mount error:", error);
            this.el.innerHTML = fallbackHtml;
        }
        return superPromise;
    },

    destroy() {
        if (this.component && this.component.destroy) {
            this.component.destroy();
        }
        if (this._super) {
            this._super.apply(this, arguments);
        }
    },
});
