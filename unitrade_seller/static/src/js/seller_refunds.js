/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { mountSellerApp } from "./seller_mount";

const REFUND_TABS = [
    { key: "all", label: "Semua Pesanan" },
    { key: "approved", label: "Setuju" },
    { key: "rejected", label: "Ditolak" },
    { key: "waiting", label: "Menunggu" },
    { key: "done", label: "Selesai" },
];

function toNumber(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function datasetPayload(dataset) {
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
    };
}

export class SellerRefunds extends Component {
    static template = "unitrade_seller.SellerRefunds";
    static props = {
        payload: Object,
    };

    setup() {
        this.searchTimer = null;
        this.state = useState({
            ready: false,
            loading: true,
            error: "",
            activeTab: "all",
            filterStatus: "all",
            filterOpen: false,
            query: "",
            dateFrom: "",
            dateTo: "",
            sidebarOpen: readSellerSidebarOpen(),
            seller: (this.props.payload || {}).seller || {},
            stats: (this.props.payload || {}).stats || {},
            refunds: [],
            counts: {
                all: 0,
                approved: 0,
                rejected: 0,
                waiting: 0,
                done: 0,
            },
            pagination: {
                page: 1,
                page_size: 6,
                total: 0,
                total_pages: 1,
                has_prev: false,
                has_next: false,
                start: 0,
                end: 0,
            },
            pageSize: 6,
        });

        onMounted(() => this.loadRefunds());
        onWillUnmount(() => clearTimeout(this.searchTimer));
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get tabs() {
        return REFUND_TABS;
    }

    get refunds() {
        return this.state.refunds || [];
    }

    get pagination() {
        return this.state.pagination || {};
    }

    get hasDateFilter() {
        return Boolean(this.state.dateFrom || this.state.dateTo);
    }

    get sidebarActiveKey() {
        return "refund";
    }

    get sidebarClass() {
        return "ut-refunds-sidebar";
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

    get totalRefundsLabel() {
        const total = Number(this.pagination.total || 0);
        if (!total) {
            return "Menampilkan 0 dari 0 data";
        }
        const start = Number(this.pagination.start || 0);
        const end = Number(this.pagination.end || 0);
        if (start <= 1) {
            return `Menampilkan ${end} dari ${total} data`;
        }
        return `Menampilkan ${start}-${end} dari ${total} data`;
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

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    tabClass(key) {
        const base = "ut-refunds-tab";
        return this.state.activeTab === key ? `${base} is-active` : base;
    }

    count(key) {
        return this.state.counts[key] || 0;
    }

    statusClass(status) {
        return `ut-refunds-status ut-refunds-status-${status || "waiting"}`;
    }

    pageButtonClass(page) {
        return Number(this.pagination.page || 1) === page
            ? "ut-refunds-page-btn is-active"
            : "ut-refunds-page-btn";
    }

    refundRowClass(refund) {
        const classes = ["ut-refunds-row"];
        if (refund.detail_url) {
            classes.push("is-clickable");
        }
        return classes.join(" ");
    }

    isRowActionEvent(event) {
        const target = event?.target;
        return Boolean(
            target
            && target.closest
            && target.closest("a, button, input, select, textarea, label, [data-ut-refunds-no-row-click]")
        );
    }

    openRefundDetail(refund, event) {
        if (this.isRowActionEvent(event)) {
            return;
        }
        if (refund.detail_url) {
            window.location.href = refund.detail_url;
        }
    }

    onRefundRowKeydown(refund, event) {
        if (this.isRowActionEvent(event)) {
            return;
        }
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (refund.detail_url) {
                window.location.href = refund.detail_url;
            }
        }
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

    toggleFilter() {
        this.state.filterOpen = !this.state.filterOpen;
        this.state.filterStatus = this.state.activeTab;
    }

    setTab(key) {
        this.state.activeTab = REFUND_TABS.some((tab) => tab.key === key) ? key : "all";
        this.state.filterStatus = this.state.activeTab;
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadRefunds();
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value || "";
        clearTimeout(this.searchTimer);
        this.searchTimer = window.setTimeout(() => this.applySearch(), 320);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.applySearch();
        }
    }

    applySearch() {
        clearTimeout(this.searchTimer);
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadRefunds();
    }

    applyFilters() {
        this.state.activeTab = REFUND_TABS.some((tab) => tab.key === this.state.filterStatus)
            ? this.state.filterStatus
            : "all";
        this.state.pagination = { ...this.pagination, page: 1 };
        this.state.filterOpen = false;
        return this.loadRefunds();
    }

    clearFilters() {
        clearTimeout(this.searchTimer);
        this.state.query = "";
        this.state.activeTab = "all";
        this.state.filterStatus = "all";
        this.state.dateFrom = "";
        this.state.dateTo = "";
        this.state.pagination = { ...this.pagination, page: 1 };
        this.state.filterOpen = false;
        return this.loadRefunds();
    }

    goToPage(page) {
        const totalPages = Math.max(1, Number(this.pagination.total_pages || 1));
        const nextPage = Math.min(Math.max(1, Number(page || 1)), totalPages);
        if (nextPage === Number(this.pagination.page || 1) || this.state.loading) {
            return;
        }
        this.state.pagination = { ...this.pagination, page: nextPage };
        return this.loadRefunds();
    }

    prevPage() {
        return this.goToPage(Number(this.pagination.page || 1) - 1);
    }

    nextPage() {
        return this.goToPage(Number(this.pagination.page || 1) + 1);
    }

    async loadRefunds() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/seller/refunds/data", {
                query: this.state.query,
                status_filter: this.state.activeTab,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
                page: this.pagination.page || 1,
                page_size: this.state.pageSize || 6,
            });
            if (!result.success) {
                throw new Error(result.message || "Refund belum bisa dimuat.");
            }
            this.state.refunds = result.refunds || [];
            this.state.counts = {
                ...this.state.counts,
                ...(result.counts || {}),
            };
            this.state.pagination = result.pagination || this.state.pagination;
            this.state.pageSize = result.page_size || (result.pagination && result.pagination.page_size) || this.state.pageSize;
            this.state.query = result.query !== undefined ? result.query : this.state.query;
            this.state.activeTab = result.status_filter || this.state.activeTab;
            this.state.filterStatus = this.state.activeTab;
            this.state.dateFrom = result.date_from !== undefined ? result.date_from : this.state.dateFrom;
            this.state.dateTo = result.date_to !== undefined ? result.date_to : this.state.dateTo;
            if (result.seller) {
                this.state.seller = result.seller;
            }
            if (result.stats) {
                this.state.stats = result.stats;
            }
        } catch (error) {
            console.error("[UniTrade] Seller refunds:", error);
            this.state.error = "Refund belum bisa dimuat. Silakan refresh halaman.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 140);
        }
    }
}

publicWidget.registry.UnitradeSellerRefunds = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-refunds-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const payload = datasetPayload(this.el.dataset);
        await mountSellerApp(this, SellerRefunds, { payload }, templates, "Seller refunds");
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
