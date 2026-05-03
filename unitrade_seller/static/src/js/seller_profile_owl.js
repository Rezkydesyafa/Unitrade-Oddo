/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

const ALLOWED_TABS = ["home", "latest", "sold", "reviews"];

function normalizeTab(value) {
    return ALLOWED_TABS.includes(value) ? value : "home";
}

function normalizeRating(value) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= 5 ? parsed : 0;
}

export class SellerProfileTabs extends Component {
    static template = "unitrade_seller.SellerProfileTabs";
    static props = {
        profileRef: String,
        initialTab: { type: String, optional: true },
        initialRating: { type: String, optional: true },
        search: { type: String, optional: true },
        initialResultsHtml: { type: String, optional: true },
    };
    static defaultProps = {
        initialTab: "home",
        initialRating: "",
        search: "",
        initialResultsHtml: "",
    };

    setup() {
        this.rootRef = useRef("root");
        this.resultsRef = useRef("results");
        this.requestSeq = 0;
        this.searchForm = null;
        this.searchInput = null;
        this.searchTabInput = null;
        this.searchDebounceTimer = null;
        this.onPopState = () => this.restoreFromUrl();
        this.onSearchInput = (ev) => this.handleSearchInput(ev);
        this.onSearchSubmit = (ev) => this.handleSearchSubmit(ev);
        this.state = useState({
            tab: normalizeTab(this.props.initialTab),
            rating: normalizeRating(this.props.initialRating),
            search: this.props.search || "",
            resultsHtml: this.props.initialResultsHtml || "",
            loading: false,
        });

        onMounted(() => {
            this._writeResultsHtml();
            this._bindSidebarSearch();
            window.addEventListener("popstate", this.onPopState);
        });

        onWillUnmount(() => {
            window.removeEventListener("popstate", this.onPopState);
            this._unbindSidebarSearch();
            this._clearSearchDebounce();
        });

        useEffect(
            () => {
                this._writeResultsHtml();
            },
            () => [this.state.resultsHtml]
        );
    }

    get tabs() {
        return [
            { key: "home", label: "Home" },
            { key: "latest", label: "terbaru" },
            { key: "sold", label: "Produk terjual" },
            { key: "reviews", label: "Ulasan" },
        ];
    }

    tabClass(key) {
        const base = [
            "tw-flex",
            "tw-h-[36px]",
            "tw-items-center",
            "tw-justify-center",
            "tw-rounded-full",
            "tw-border-0",
            "tw-px-5",
            "tw-text-[15px]",
            "tw-leading-6",
            "tw-transition-colors",
            "tw-whitespace-nowrap",
        ].join(" ");
        if (this.state.tab === key) {
            return `${base} tw-bg-[#212529] tw-font-semibold tw-text-white`;
        }
        return `${base} tw-bg-transparent tw-font-normal tw-text-[#939393] hover:tw-bg-[#f5f5f7] hover:tw-text-[#212529]`;
    }

    _writeResultsHtml() {
        if (this.resultsRef.el) {
            this.resultsRef.el.innerHTML = this.state.resultsHtml || "";
        }
    }

    _bindSidebarSearch() {
        const root = this.rootRef.el;
        const page = (root && root.closest(".ut-seller-profile-page")) || document;
        this.searchForm = page.querySelector("#ut-seller-sidebar-search-form");
        this.searchInput = page.querySelector("#ut-seller-sidebar-search-input");
        this.searchTabInput = page.querySelector("#ut-seller-sidebar-search-tab");
        this._syncSidebarSearch();
        if (this.searchInput) {
            this.searchInput.addEventListener("input", this.onSearchInput);
        }
        if (this.searchForm) {
            this.searchForm.addEventListener("submit", this.onSearchSubmit);
        }
    }

    _unbindSidebarSearch() {
        if (this.searchInput) {
            this.searchInput.removeEventListener("input", this.onSearchInput);
        }
        if (this.searchForm) {
            this.searchForm.removeEventListener("submit", this.onSearchSubmit);
        }
        this.searchForm = null;
        this.searchInput = null;
        this.searchTabInput = null;
    }

    _syncSidebarSearch() {
        if (this.searchInput && this.searchInput.value !== this.state.search) {
            this.searchInput.value = this.state.search || "";
        }
        if (this.searchTabInput) {
            this.searchTabInput.value = this.state.tab;
        }
    }

    _clearSearchDebounce() {
        if (this.searchDebounceTimer) {
            window.clearTimeout(this.searchDebounceTimer);
            this.searchDebounceTimer = null;
        }
    }

    _scheduleSearchLoad() {
        this._clearSearchDebounce();
        this.searchDebounceTimer = window.setTimeout(() => {
            this.searchDebounceTimer = null;
            this.loadTab(this.state.tab, { replace: true });
        }, 300);
    }

    async selectTab(tab) {
        const nextTab = normalizeTab(tab);
        if (this.state.loading || nextTab === this.state.tab) {
            return;
        }
        if (nextTab !== "reviews") {
            this.state.rating = 0;
        }
        await this.loadTab(nextTab);
    }

    async restoreFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const nextTab = normalizeTab(params.get("tab") || "home");
        this.state.search = params.get("search") || "";
        this.state.rating = nextTab === "reviews" ? normalizeRating(params.get("rating")) : 0;
        this._syncSidebarSearch();
        await this.loadTab(nextTab, { replace: true });
    }

    handleSearchInput(ev) {
        const nextSearch = ev.target.value || "";
        if (nextSearch === this.state.search) {
            return;
        }
        this.state.search = nextSearch;
        if (this.state.tab === "reviews") {
            this.state.tab = "home";
            this.state.rating = 0;
        }
        this._syncSidebarSearch();
        this._scheduleSearchLoad();
    }

    handleSearchSubmit(ev) {
        ev.preventDefault();
        this._clearSearchDebounce();
        if (this.state.tab === "reviews") {
            this.state.tab = "home";
            this.state.rating = 0;
        }
        this._syncSidebarSearch();
        this.loadTab(this.state.tab, { replace: true });
    }

    async onResultsClick(ev) {
        const filterButton = ev.target.closest(".ut-seller-review-filter");
        if (!filterButton) {
            return;
        }
        ev.preventDefault();
        if (this.state.tab !== "reviews" || this.state.loading) {
            return;
        }
        const nextRating = normalizeRating(filterButton.dataset.rating);
        if (nextRating === this.state.rating) {
            return;
        }
        this.state.rating = nextRating;
        await this.loadTab("reviews");
    }

    async loadTab(tab, options = {}) {
        const requestId = ++this.requestSeq;
        this.state.tab = normalizeTab(tab);
        this.state.loading = true;
        try {
            const result = await jsonrpc("/unitrade/seller-profile/products", {
                profile_ref: this.props.profileRef,
                tab: this.state.tab,
                search: this.state.search,
                rating: this.state.tab === "reviews" ? this.state.rating : 0,
            });
            if (requestId !== this.requestSeq) {
                return;
            }
            if (!result.success) {
                throw new Error(result.message || "Konten toko belum bisa dimuat.");
            }
            this.state.tab = normalizeTab(result.tab || tab);
            this.state.rating = this.state.tab === "reviews" ? normalizeRating(result.rating) : 0;
            this.state.search = result.search || "";
            this.state.resultsHtml = result.html || "";
            this._syncSidebarSearch();
            this._updateUrl(options.replace);
        } catch (error) {
            console.error("[UniTrade] Seller profile tabs:", error);
            window.alert("Konten toko belum bisa dimuat. Silakan coba lagi.");
        } finally {
            if (requestId === this.requestSeq) {
                this.state.loading = false;
            }
        }
    }

    _updateUrl(replace = false) {
        const params = new URLSearchParams();
        if (this.state.tab !== "home") {
            params.set("tab", this.state.tab);
        }
        if (this.state.search) {
            params.set("search", this.state.search);
        }
        if (this.state.tab === "reviews" && this.state.rating) {
            params.set("rating", String(this.state.rating));
        }
        const query = params.toString();
        const url = `/seller-profile/${this.props.profileRef}${query ? `?${query}` : ""}`;
        const method = replace ? "replaceState" : "pushState";
        window.history[method]({}, "", url);
    }
}

publicWidget.registry.UnitradeSellerProfileTabs = publicWidget.Widget.extend({
    selector: "#ut-seller-profile-owl",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const results = this.el.querySelector("#ut-seller-initial-products");
        const props = {
            profileRef: this.el.dataset.profileRef || "",
            initialTab: this.el.dataset.initialTab || "home",
            initialRating: this.el.dataset.initialRating || "",
            search: this.el.dataset.search || "",
            initialResultsHtml: results ? results.innerHTML : "",
        };
        if (!props.profileRef) {
            return superPromise;
        }
        this.el.innerHTML = "";
        this.component = await mount(SellerProfileTabs, this.el, { props, templates });
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

publicWidget.registry.UnitradeSellerReportModal = publicWidget.Widget.extend({
    selector: ".ut-seller-report-widget",

    events: {
        "click .ut-seller-report-trigger": "_openReportModal",
        "click [data-report-close]": "_closeReportModal",
    },

    start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.el.classList.contains("ut-is-open")) {
                this._closeReportModal(ev);
            }
        };
        document.addEventListener("keydown", this._onKeydown);
        return superPromise;
    },

    destroy() {
        if (this._onKeydown) {
            document.removeEventListener("keydown", this._onKeydown);
        }
        if (this._super) {
            this._super.apply(this, arguments);
        }
    },

    _openReportModal(ev) {
        ev.preventDefault();
        this.el.classList.add("ut-is-open");
        const modal = this.el.querySelector(".ut-seller-report-modal");
        const textarea = this.el.querySelector(".ut-seller-report-textarea");
        if (modal) {
            modal.setAttribute("aria-hidden", "false");
        }
        if (textarea) {
            window.setTimeout(() => textarea.focus(), 30);
        }
    },

    _closeReportModal(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.el.classList.remove("ut-is-open");
        const modal = this.el.querySelector(".ut-seller-report-modal");
        const trigger = this.el.querySelector(".ut-seller-report-trigger");
        if (modal) {
            modal.setAttribute("aria-hidden", "true");
        }
        if (trigger) {
            trigger.focus();
        }
    },
});
