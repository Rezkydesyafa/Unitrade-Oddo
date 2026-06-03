/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { mountSellerApp } from "./seller_mount";

const DATE_FILTER_OPTIONS = [
    { value: "7", label: "7 hari terakhir", hint: "Update minggu ini" },
    { value: "30", label: "30 hari terakhir", hint: "Update bulan ini" },
    { value: "all", label: "Semua waktu", hint: "Semua barang toko" },
];

function toNumber(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function datasetPayload(dataset, parsed) {
    if (parsed && parsed.seller) {
        return parsed;
    }
    return {
        seller: {
            name: dataset.sellerName || "Penjual UniTrade",
            avatar_url: dataset.sellerAvatarUrl || "/web/static/img/user_menu_avatar.png",
            profile_url: dataset.sellerProfileUrl || "/unitrade/seller/dashboard",
        },
        stats: {
            notification_count: toNumber(dataset.notificationCount),
            unread_chat_count: toNumber(dataset.unreadChatCount),
        },
        products: [],
        pagination: {
            page: 1,
            page_size: 10,
            total: 0,
            total_pages: 1,
            has_prev: false,
            has_next: false,
            start: 0,
            end: 0,
        },
        page_size: 10,
        date_filter: dataset.dateFilter || "30",
        query: "",
        add_product_url: dataset.addProductUrl || "",
    };
}

export class SellerProducts extends Component {
    static template = "unitrade_seller.SellerProducts";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.searchTimer = null;
        this.state = useState({
            ready: false,
            loading: true,
            error: "",
            query: payload.query || "",
            dateFilter: payload.date_filter || "30",
            filterOpen: false,
            sidebarOpen: readSellerSidebarOpen(),
            seller: payload.seller || {},
            stats: payload.stats || {},
            products: payload.products || [],
            pagination: payload.pagination || {
                page: 1,
                page_size: payload.page_size || 10,
                total: (payload.products || []).length,
                total_pages: 1,
                has_prev: false,
                has_next: false,
                start: (payload.products || []).length ? 1 : 0,
                end: (payload.products || []).length,
            },
            pageSize: payload.page_size || (payload.pagination && payload.pagination.page_size) || 10,
            addProductUrl: payload.add_product_url || "",
        });

        onMounted(() => {
            this.loadProducts();
        });
        onWillUnmount(() => {
            clearTimeout(this.searchTimer);
        });
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get addProductUrl() {
        return this.state.addProductUrl || "/web#model=product.template&view_type=form";
    }

    get sidebarActiveKey() {
        return "products";
    }

    get sidebarClass() {
        return "ut-products-sidebar";
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get filteredProducts() {
        return this.state.products || [];
    }

    get pagination() {
        return this.state.pagination || {};
    }

    get totalProductsLabel() {
        const total = Number(this.pagination.total || 0);
        const end = Number(this.pagination.end || 0);
        return `Menampilkan ${end} dari ${total} data`;
    }

    get currentPageLabel() {
        const page = Math.max(1, Number(this.pagination.page || 1));
        const totalPages = Math.max(1, Number(this.pagination.total_pages || 1));
        return `Halaman ${page} dari ${totalPages}`;
    }

    get pageNumbers() {
        const totalPages = Math.max(1, Number(this.pagination.total_pages || 1));
        const currentPage = Math.max(1, Number(this.pagination.page || 1));
        const start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
        const end = Math.min(totalPages, start + 4);
        const pages = [];
        for (let page = start; page <= end; page += 1) {
            pages.push(page);
        }
        return pages;
    }

    get dateFilterOptions() {
        return DATE_FILTER_OPTIONS;
    }

    get activeDateFilterLabel() {
        return this.dateFilterLabel(this.state.dateFilter);
    }

    conditionClass(product) {
        const key = product.condition_key || "used";
        return `ut-products-condition ut-products-condition-${key}`;
    }

    statusClass(product) {
        const key = product.status_key || (product.is_active ? "active" : "inactive");
        return `ut-products-status ut-products-status-${key}`;
    }

    expiryClass(product) {
        const key = product.expiry_state || "neutral";
        return `ut-products-expiry ut-products-expiry-${key}`;
    }

    stockClass(product) {
        return product.stock_warning ? "ut-products-stock is-empty" : "ut-products-stock";
    }

    actionClass(type) {
        return type === "pay" ? "ut-products-action is-pay" : `ut-products-action is-${type || "default"}`;
    }

    pageButtonClass(page) {
        return Number(this.pagination.page || 1) === page
            ? "ut-products-page-btn is-active"
            : "ut-products-page-btn";
    }

    productKey(product) {
        return `${product.id || product.product_code}-${product.name || ""}`;
    }

    dateFilterLabel(value) {
        return {
            "7": "7 hari terakhir",
            "30": "30 hari terakhir",
            all: "Semua waktu",
        }[value || this.state.dateFilter] || "30 hari terakhir";
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        writeSellerSidebarOpen(this.state.sidebarOpen);
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
        writeSellerSidebarOpen(false);
    }

    onSidebarNavClick() {
        if (window.innerWidth <= 1024) {
            this.closeSidebar();
        }
    }

    onDateFilterChange(ev) {
        this.state.dateFilter = ev.target.value || "30";
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadProducts();
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value || "";
        clearTimeout(this.searchTimer);
        this.searchTimer = window.setTimeout(() => this.applySearch(), 320);
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        this.applySearch();
    }

    applySearch() {
        clearTimeout(this.searchTimer);
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadProducts();
    }

    toggleFilters() {
        this.state.filterOpen = !this.state.filterOpen;
    }

    onPageSizeChange(ev) {
        this.state.pageSize = Number(ev.target.value || 10);
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadProducts();
    }

    goToPage(page) {
        const totalPages = Math.max(1, Number(this.pagination.total_pages || 1));
        const nextPage = Math.min(Math.max(1, Number(page || 1)), totalPages);
        if (nextPage === Number(this.pagination.page || 1) || this.state.loading) {
            return;
        }
        this.state.pagination = { ...this.pagination, page: nextPage };
        return this.loadProducts();
    }

    prevPage() {
        return this.goToPage(Number(this.pagination.page || 1) - 1);
    }

    nextPage() {
        return this.goToPage(Number(this.pagination.page || 1) + 1);
    }

    async loadProducts() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/seller/products/data", {
                date_filter: this.state.dateFilter,
                query: this.state.query,
                page: this.pagination.page || 1,
                page_size: this.state.pageSize || 10,
            });
            if (!result.success) {
                throw new Error(result.message || "Produk belum bisa dimuat.");
            }
            this.state.products = result.products || [];
            this.state.pagination = result.pagination || this.state.pagination;
            this.state.pageSize = result.page_size || (result.pagination && result.pagination.page_size) || this.state.pageSize;
            this.state.dateFilter = result.date_filter || this.state.dateFilter;
            this.state.query = result.query !== undefined ? result.query : this.state.query;
            if (result.seller) {
                this.state.seller = result.seller;
            }
            if (result.stats) {
                this.state.stats = result.stats;
            }
            if (result.add_product_url) {
                this.state.addProductUrl = result.add_product_url;
            }
        } catch (error) {
            console.error("[UniTrade] Seller products:", error);
            this.state.error = "Produk belum bisa dimuat. Silakan refresh halaman.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }
}

publicWidget.registry.UnitradeSellerProducts = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-products-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.productsPayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller products payload:", error);
        }
        const payload = datasetPayload(this.el.dataset, parsed);
        await mountSellerApp(this, SellerProducts, { payload }, templates, "Seller products");
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
