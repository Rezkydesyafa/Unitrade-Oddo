/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";

export const SELLER_SIDEBAR_ICON_BASE = "/unitrade_seller/static/src/img/";
export const SELLER_SIDEBAR_STORAGE_KEY = "unitrade.seller.sidebar.expanded";

const DASHBOARD_HASH_KEYS = {
    "#dashboard-refunds": "refund",
    "#dashboard-payout": "payout",
    "#dashboard-reviews": "reviews",
};

export function readSellerSidebarOpen() {
    try {
        return window.localStorage.getItem(SELLER_SIDEBAR_STORAGE_KEY) === "1";
    } catch (error) {
        return false;
    }
}

export function writeSellerSidebarOpen(isOpen) {
    try {
        window.localStorage.setItem(SELLER_SIDEBAR_STORAGE_KEY, isOpen ? "1" : "0");
    } catch (error) {
        // Local storage can be unavailable in private windows; the reactive state still works.
    }
}

export function compactBadge(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) {
        return 0;
    }
    return number > 99 ? "99+" : number;
}

export function sellerSidebarActiveKey(fallback = "dashboard") {
    if (typeof window === "undefined") {
        return fallback;
    }
    const path = window.location.pathname || "";
    if (path.includes("/unitrade/seller/chat")) {
        return "chat";
    }
    if (path.includes("/unitrade/seller/orders")) {
        return "orders";
    }
    if (path.includes("/unitrade/seller/refunds")) {
        return "refund";
    }
    if (path.includes("/unitrade/seller/payout") || path.includes("/seller/payout")) {
        return "payout";
    }
    if (path.includes("/unitrade/seller/products")) {
        return "products";
    }
    if (path.includes("/unitrade/seller/settings")) {
        return "settings";
    }
    if (path.includes("/unitrade/seller/dashboard")) {
        return DASHBOARD_HASH_KEYS[window.location.hash] || fallback || "dashboard";
    }
    return fallback || "dashboard";
}

export function sellerSidebarItems(activeKey, stats = {}) {
    const currentActiveKey = sellerSidebarActiveKey(activeKey);
    const incomingOrders = stats.incoming_orders || stats.incomingOrders || stats.notification_count || 0;
    const unreadChat = stats.unread_chat_count || stats.unreadChatCount || 0;
    return [
        {
            key: "dashboard",
            section: "store",
            label: "Dashboard",
            href: "/unitrade/seller/dashboard",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-dashboard.svg`,
        },
        {
            key: "orders",
            section: "store",
            label: "Order",
            href: "/unitrade/seller/orders",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-cart.svg`,
            badge: compactBadge(incomingOrders),
        },
        {
            key: "refund",
            section: "store",
            label: "Refund",
            href: "/unitrade/seller/refunds",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-refund.svg`,
        },
        {
            key: "products",
            section: "store",
            label: "Produk",
            href: "/unitrade/seller/products",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-box.svg`,
        },
        {
            key: "payout",
            section: "store",
            label: "Pencairan",
            href: "/unitrade/seller/payouts",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-wallet.svg`,
        },
        {
            key: "chat",
            section: "communication",
            label: "Chat Pembeli",
            href: "/unitrade/seller/chat",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-chat.svg`,
            badge: compactBadge(unreadChat),
        },
        {
            key: "reviews",
            section: "communication",
            label: "Ulasan",
            href: "/unitrade/seller/dashboard#dashboard-reviews",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-star.svg`,
        },
        {
            key: "settings",
            section: "settings",
            label: "Settings",
            href: "/unitrade/seller/settings",
            iconUrl: `${SELLER_SIDEBAR_ICON_BASE}dashboard-icon-settings.svg`,
            ariaLabel: "Pengaturan Toko",
        },
    ].map((item) => ({
        ...item,
        active: item.key === currentActiveKey,
    }));
}

export class SellerSidebarHost extends Component {
    static template = "unitrade_seller.SellerSidebar";
    static props = {
        activeKey: { type: String, optional: true },
        stats: { type: Object, optional: true },
        sidebarClass: { type: String, optional: true },
    };
    static defaultProps = {
        activeKey: "dashboard",
        stats: {},
        sidebarClass: "",
    };

    setup() {
        this.state = useState({
            sidebarOpen: readSellerSidebarOpen(),
        });

        onMounted(() => this.syncRootState());
    }

    get sidebarActiveKey() {
        return this.props.activeKey || "dashboard";
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.props.stats || {});
    }

    get sidebarClass() {
        return this.props.sidebarClass || "";
    }

    sidebarItemClass(item) {
        return item.active ? "ut-dash-sidebar-item active" : "ut-dash-sidebar-item";
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        writeSellerSidebarOpen(this.state.sidebarOpen);
        this.syncRootState();
    }

    onSidebarNavClick() {
        if (window.innerWidth <= 1024) {
            this.state.sidebarOpen = false;
            this.syncRootState();
        }
    }

    syncRootState() {
        const root = document.querySelector(".ut-seller-dashboard-page, .ut-chat-seller-dashboard-page");
        if (root) {
            root.classList.toggle("ut-is-sidebar-open", this.state.sidebarOpen);
        }
    }
}

function numberFromDataset(value) {
    const parsed = parseInt(value || "0", 10);
    return Number.isFinite(parsed) ? parsed : 0;
}

publicWidget.registry.UnitradeSellerSidebarHost = publicWidget.Widget.extend({
    selector: ".ut-seller-sidebar-owl-host",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const fallbackNodes = Array.from(this.el.childNodes);
        const mountTarget = document.createElement("div");
        mountTarget.className = "ut-sidebar-owl-mount-host";
        this.el.appendChild(mountTarget);
        try {
            this.component = await mount(SellerSidebarHost, mountTarget, {
                props: {
                    activeKey: this.el.dataset.sidebarActiveKey || "dashboard",
                    sidebarClass: this.el.dataset.sidebarClass || "",
                    stats: {
                        incoming_orders: numberFromDataset(this.el.dataset.incomingOrders),
                        unread_chat_count: numberFromDataset(this.el.dataset.unreadChatCount),
                    },
                },
                templates,
            });
            fallbackNodes.forEach((node) => node.remove());
        } catch (error) {
            mountTarget.remove();
            console.error("[UniTrade] Seller sidebar mount:", error);
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
