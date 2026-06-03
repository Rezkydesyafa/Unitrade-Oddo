/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { formatHandoffFileSize, validateHandoffImageFile } from "./seller_handoff_upload";
import { mountSellerApp } from "./seller_mount";

const ORDER_TABS = [
    { key: "all", label: "Semua Pesanan" },
    { key: "new", label: "Menunggu" },
    { key: "processing", label: "Diproses" },
    { key: "done", label: "Selesai" },
    { key: "cancel", label: "Dibatalkan" },
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

export class SellerOrders extends Component {
    static template = "unitrade_seller.SellerOrders";
    static props = {
        payload: Object,
    };

    setup() {
        this.handoffFileInputRef = useRef("handoffFileInput");
        this.searchTimer = null;
        this.state = useState({
            ready: false,
            loading: true,
            error: "",
            activeTab: "all",
            query: "",
            filterOpen: false,
            sidebarOpen: readSellerSidebarOpen(),
            handoffOrder: null,
            handoffDragActive: false,
            handoffFileName: "",
            handoffFileSize: "",
            handoffPreviewUrl: "",
            handoffError: "",
            csrfToken: "",
            seller: (this.props.payload || {}).seller || {},
            stats: (this.props.payload || {}).stats || {},
            orders: [],
            counts: {
                all: 0,
                new: 0,
                processing: 0,
                done: 0,
                cancel: 0,
            },
            pagination: {
                page: 1,
                page_size: 5,
                total: 0,
                total_pages: 1,
                has_prev: false,
                has_next: false,
                start: 0,
                end: 0,
            },
            pageSize: 5,
        });

        onMounted(() => this.loadOrders());
        onWillUnmount(() => {
            clearTimeout(this.searchTimer);
            this.resetHandoffUpload();
        });
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get tabs() {
        return ORDER_TABS;
    }

    get sidebarItems() {
        const incoming = this.state.counts.new + this.state.counts.processing;
        return sellerSidebarItems(this.sidebarActiveKey, {
            ...this.stats,
            incoming_orders: incoming || this.stats.notification_count || 0,
        });
    }

    get sidebarActiveKey() {
        return "orders";
    }

    get sidebarClass() {
        return "ut-orders-sidebar";
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get filteredOrders() {
        return this.state.orders || [];
    }

    get pagination() {
        return this.state.pagination || {};
    }

    get totalOrdersLabel() {
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

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    tabClass(key) {
        const base = "ut-orders-tab";
        return this.state.activeTab === key ? `${base} is-active` : base;
    }

    statusClass(status) {
        return `ut-orders-status ut-orders-status-${status || "new"}`;
    }

    orderRowClass(order) {
        const classes = ["ut-orders-row"];
        if (this.orderDetailUrl(order)) {
            classes.push("is-clickable");
        }
        return classes.join(" ");
    }

    orderKey(order) {
        return `${order.id || order.order_name}-${order.product_name || ""}`;
    }

    orderDetailUrl(order) {
        return order?.order_detail_url || order?.detail_url || order?.order_status_url || "";
    }

    isRowActionEvent(event) {
        const target = event?.target;
        return Boolean(
            target
            && target.closest
            && target.closest("a, button, input, select, textarea, label, [data-ut-orders-no-row-click]")
        );
    }

    openOrderDetail(order, event) {
        if (this.isRowActionEvent(event)) {
            return;
        }
        const url = this.orderDetailUrl(order);
        if (url) {
            window.location.href = url;
        }
    }

    onOrderRowKeydown(order, event) {
        if (this.isRowActionEvent(event)) {
            return;
        }
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            const url = this.orderDetailUrl(order);
            if (url) {
                window.location.href = url;
            }
        }
    }

    count(key) {
        return this.state.counts[key] || 0;
    }

    setTab(key) {
        this.state.activeTab = ORDER_TABS.some((tab) => tab.key === key) ? key : "all";
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadOrders();
    }

    toggleFilters() {
        this.state.filterOpen = !this.state.filterOpen;
    }

    onFilterStatusChange(ev) {
        return this.setTab(ev.target.value || "all");
    }

    onPageSizeChange(ev) {
        this.state.pageSize = Number(ev.target.value || 5);
        this.state.pagination = { ...this.pagination, page: 1 };
        return this.loadOrders();
    }

    pageButtonClass(page) {
        return Number(this.pagination.page || 1) === page
            ? "ut-orders-page-btn is-active"
            : "ut-orders-page-btn";
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
        return this.loadOrders();
    }

    goToPage(page) {
        const totalPages = Math.max(1, Number(this.pagination.total_pages || 1));
        const nextPage = Math.min(Math.max(1, Number(page || 1)), totalPages);
        if (nextPage === Number(this.pagination.page || 1) || this.state.loading) {
            return;
        }
        this.state.pagination = { ...this.pagination, page: nextPage };
        return this.loadOrders();
    }

    prevPage() {
        return this.goToPage(Number(this.pagination.page || 1) - 1);
    }

    nextPage() {
        return this.goToPage(Number(this.pagination.page || 1) + 1);
    }

    openHandoff(order) {
        this.resetHandoffUpload();
        this.state.handoffOrder = order;
    }

    closeHandoff() {
        this.state.handoffOrder = null;
        this.resetHandoffUpload();
    }

    resetHandoffUpload() {
        if (this.state.handoffPreviewUrl) {
            URL.revokeObjectURL(this.state.handoffPreviewUrl);
        }
        this.state.handoffDragActive = false;
        this.state.handoffFileName = "";
        this.state.handoffFileSize = "";
        this.state.handoffPreviewUrl = "";
        this.state.handoffError = "";
        const input = this.handoffFileInputRef.el;
        if (input) {
            input.value = "";
        }
    }

    openHandoffFilePicker() {
        const input = this.handoffFileInputRef.el;
        if (input) {
            input.click();
        }
    }

    validateHandoffFile(file) {
        return validateHandoffImageFile(file);
    }

    setHandoffFile(file) {
        const error = this.validateHandoffFile(file);
        if (error) {
            this.resetHandoffUpload();
            this.state.handoffError = error;
            return;
        }
        if (this.state.handoffPreviewUrl) {
            URL.revokeObjectURL(this.state.handoffPreviewUrl);
        }
        const input = this.handoffFileInputRef.el;
        if (input && window.DataTransfer) {
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
        }
        this.state.handoffFileName = file.name || "bukti-penyerahan.jpg";
        this.state.handoffFileSize = formatHandoffFileSize(file.size);
        this.state.handoffPreviewUrl = URL.createObjectURL(file);
        this.state.handoffError = "";
    }

    onHandoffFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        this.setHandoffFile(file);
    }

    onHandoffDragEnter(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = true;
    }

    onHandoffDragOver(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = true;
    }

    onHandoffDragLeave(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.handoffDragActive = false;
        }
    }

    onHandoffDrop(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.handoffDragActive = false;
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        this.setHandoffFile(file);
    }

    clearHandoffFile(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.resetHandoffUpload();
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

    async loadOrders() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/seller/orders/data", {
                query: this.state.query,
                status_filter: this.state.activeTab,
                page: this.pagination.page || 1,
                page_size: this.state.pageSize || 10,
            });
            if (!result.success) {
                throw new Error(result.message || "Pesanan belum bisa dimuat.");
            }
            this.state.orders = result.orders || [];
            this.state.counts = {
                ...this.state.counts,
                ...(result.counts || {}),
            };
            this.state.pagination = result.pagination || this.state.pagination;
            this.state.pageSize = result.page_size || (result.pagination && result.pagination.page_size) || this.state.pageSize;
            this.state.query = result.query !== undefined ? result.query : this.state.query;
            this.state.activeTab = result.status_filter || this.state.activeTab;
            if (result.seller) {
                this.state.seller = result.seller;
            }
            if (result.stats) {
                this.state.stats = result.stats;
            }
            if (result.csrf_token) {
                this.state.csrfToken = result.csrf_token;
            }
        } catch (error) {
            console.error("[UniTrade] Seller orders:", error);
            this.state.error = "Pesanan belum bisa dimuat. Silakan refresh halaman.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }
}

publicWidget.registry.UnitradeSellerOrders = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-orders-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const payload = datasetPayload(this.el.dataset);
        await mountSellerApp(this, SellerOrders, { payload }, templates, "Seller orders");
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
