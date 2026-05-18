/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { sellerSidebarItems } from "./seller_sidebar";

const ORDER_TABS = [
    { key: "all", label: "Semua Pesanan" },
    { key: "new", label: "Baru" },
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
        this.state = useState({
            ready: false,
            loading: true,
            error: "",
            activeTab: "all",
            query: "",
            sidebarOpen: false,
            handoffOrder: null,
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
        });

        onMounted(() => this.loadOrders());
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
        const query = this.state.query.trim().toLowerCase();
        return this.state.orders.filter((order) => {
            const tabMatch = this.state.activeTab === "all" || order.status_key === this.state.activeTab;
            if (!tabMatch) {
                return false;
            }
            if (!query) {
                return true;
            }
            return [
                order.order_name,
                order.customer_name,
                order.product_name,
                order.total_label,
                order.status_label,
                order.date_label,
            ].join(" ").toLowerCase().includes(query);
        });
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

    orderKey(order) {
        return `${order.id || order.order_name}-${order.product_name || ""}`;
    }

    count(key) {
        return this.state.counts[key] || 0;
    }

    setTab(key) {
        this.state.activeTab = ORDER_TABS.some((tab) => tab.key === key) ? key : "all";
    }

    openHandoff(order) {
        this.state.handoffOrder = order;
    }

    closeHandoff() {
        this.state.handoffOrder = null;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
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
            const result = await jsonrpc("/unitrade/seller/orders/data", {});
            if (!result.success) {
                throw new Error(result.message || "Pesanan belum bisa dimuat.");
            }
            this.state.orders = result.orders || [];
            this.state.counts = {
                ...this.state.counts,
                ...(result.counts || {}),
            };
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
        this.el.innerHTML = "";
        this.component = await mount(SellerOrders, this.el, {
            props: { payload },
            templates,
        });
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
