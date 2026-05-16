/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { sellerSidebarItems } from "./seller_sidebar";

function compactMoney(value) {
    const number = Number(value || 0);
    if (number >= 1000000000) {
        return "Rp " + (Math.round(number / 100000000) / 10).toLocaleString("id-ID") + " M";
    }
    if (number >= 1000000) {
        return "Rp " + (Math.round(number / 100000) / 10).toLocaleString("id-ID") + " jt";
    }
    if (number >= 1000) {
        return "Rp " + Math.round(number / 1000).toLocaleString("id-ID") + " rb";
    }
    return "Rp " + Math.round(number).toLocaleString("id-ID");
}

function initials(name) {
    return String(name || "UT")
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part.charAt(0).toUpperCase())
        .join("") || "UT";
}

function todayLabel() {
    const now = new Date();
    return [
        String(now.getDate()).padStart(2, "0"),
        String(now.getMonth() + 1).padStart(2, "0"),
        now.getFullYear(),
    ].join("/");
}

function payloadFromDataset(dataset, parsed) {
    if (parsed && parsed.stats) {
        return parsed;
    }
    return {
        seller: {
            name: dataset.sellerName || "Penjual UniTrade",
            avatar_url: dataset.sellerAvatarUrl || "/web/static/img/user_menu_avatar.png",
            profile_url: dataset.sellerProfileUrl || "/unitrade/seller/dashboard",
        },
        stats: {
            revenue_label: dataset.revenueLabel || "Rp 0",
            available_balance_label: dataset.availableBalanceLabel || "Rp 0",
            active_products: Number(dataset.activeProducts || 0),
            incoming_orders: Number(dataset.incomingOrders || 0),
            sold_count: Number(dataset.soldCount || 0),
            unread_chat_count: Number(dataset.unreadChatCount || 0),
            notification_count: Number(dataset.notificationCount || 0),
        },
        orders: [],
        products: [],
        messages: [],
        reviews: [],
        refunds: [],
        chart: parsed && (parsed.weekly || parsed.monthly) ? parsed : {},
        current_date_label: todayLabel(),
        add_product_url: dataset.addProductUrl || "",
        csrf_token: "",
    };
}

export class SellerDashboard extends Component {
    static template = "unitrade_seller.SellerDashboard";
    static props = {
        payload: Object,
    };

    setup() {
        this.chartRef = useRef("chart");
        this.rootRef = useRef("root");
        this.onResize = () => this.drawChart();
        this.state = useState({
            period: "weekly",
            query: "",
            searchOpen: false,
            sidebarOpen: false,
            ready: false,
            handoffOrder: null,
        });

        onMounted(() => {
            window.addEventListener("resize", this.onResize);
            window.setTimeout(() => {
                this.state.ready = true;
                window.requestAnimationFrame(() => this.drawChart());
            }, 220);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this.onResize);
        });

        useEffect(
            () => {
                if (this.state.ready) {
                    this.drawChart();
                }
            },
            () => [this.state.period, this.state.ready]
        );
    }

    get payload() {
        return this.props.payload || {};
    }

    get seller() {
        return this.payload.seller || {};
    }

    get stats() {
        return this.payload.stats || {};
    }

    get orders() {
        return (this.payload.orders || []).slice(0, 4);
    }

    get messages() {
        return (this.payload.messages || []).slice(0, 5);
    }

    get refunds() {
        return (this.payload.refunds || []).slice(0, 4).map((refund, index) => ({
            ...refund,
            initials: initials(refund.buyer_name),
            index,
        }));
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get sidebarActiveKey() {
        return "dashboard";
    }

    get sidebarClass() {
        return "ut-dashboard-sidebar";
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get searchItems() {
        const orderItems = (this.payload.orders || []).map((order, index) => ({
            key: "order-" + index + "-" + order.order_name,
            icon: "fa-shopping-cart",
            title: `${order.order_name || "Order"} - ${order.customer_name || "Customer"}`,
            subtitle: `${order.product_name || ""} - ${order.status_label || ""}`,
            url: order.action_url || "#dashboard-orders",
        }));
        const productItems = (this.payload.products || []).map((product, index) => ({
            key: "product-" + index + "-" + product.name,
            icon: "fa-cube",
            title: product.name || "Produk",
            subtitle: `${product.price_label || ""} - Rating ${product.rating_label || "0.0"}`,
            url: product.url || "#dashboard-orders",
        }));
        const messageItems = (this.payload.messages || []).map((message, index) => ({
            key: "message-" + index + "-" + message.title,
            icon: "fa-commenting-o",
            title: message.title || "Chat pembeli",
            subtitle: message.last_message || "",
            url: message.url || "/unitrade/seller/chat",
        }));
        const refundItems = (this.payload.refunds || []).map((refund, index) => ({
            key: "refund-" + index + "-" + refund.name,
            icon: "fa-undo",
            title: `${refund.name || "Refund"} - ${refund.buyer_name || "Pembeli"}`,
            subtitle: `${refund.reason || ""} - ${refund.amount_label || ""}`,
            url: refund.detail_url || "#dashboard-refunds",
        }));
        return orderItems.concat(productItems, messageItems, refundItems);
    }

    get filteredSearchItems() {
        const query = this.state.query.trim().toLowerCase();
        if (!query) {
            return this.searchItems;
        }
        return this.searchItems.filter((item) => `${item.title} ${item.subtitle}`.toLowerCase().includes(query));
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    periodClass(period) {
        const base = "tw-h-7 tw-rounded-[8px] tw-border-0 tw-px-4 tw-text-[12px] tw-font-semibold";
        return this.state.period === period
            ? `${base} tw-bg-[#101828] tw-text-white`
            : `${base} tw-bg-transparent tw-text-[#6a7282]`;
    }

    statusClass(status) {
        return `ut-dash-status-pill ut-dash-status-${status || "pending"}`;
    }

    messageKey(message) {
        return `${message.title || "message"}-${message.url || ""}`;
    }

    orderKey(order) {
        return `${order.order_name || "order"}-${order.product_name || ""}`;
    }

    refundKey(refund) {
        return refund.key || `refund-${refund.id || refund.name || ""}`;
    }

    setPeriod(period) {
        this.state.period = period;
    }

    openSearch() {
        this.state.searchOpen = true;
    }

    closeSearch() {
        this.state.searchOpen = false;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        window.setTimeout(() => this.drawChart(), 300);
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
        window.setTimeout(() => this.drawChart(), 300);
    }

    openHandoff(order) {
        this.state.handoffOrder = order;
    }

    closeHandoff() {
        this.state.handoffOrder = null;
    }

    onSidebarNavClick() {
        if (window.innerWidth <= 1024) {
            this.closeSidebar();
        }
    }

    drawChart() {
        if (!this.state.ready) {
            return;
        }
        const canvas = this.chartRef.el;
        if (!canvas || !canvas.getContext) {
            return;
        }
        const data = (this.payload.chart || {})[this.state.period] || (this.payload.chart || {}).weekly || {};
        const labels = data.labels || [];
        const values = data.revenue || [];
        const parent = canvas.parentElement;
        const rect = parent ? parent.getBoundingClientRect() : canvas.getBoundingClientRect();
        const width = Math.max(320, Math.floor(rect.width || 720));
        const height = Math.max(240, Math.floor(rect.height || 315));
        const ratio = window.devicePixelRatio || 1;
        const ctx = canvas.getContext("2d");

        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const pad = { top: 18, right: 18, bottom: 34, left: 58 };
        const plotWidth = width - pad.left - pad.right;
        const plotHeight = height - pad.top - pad.bottom;
        const rawMax = Math.max(...values.map((value) => Number(value || 0)), 0);
        const maxValue = rawMax > 0 ? rawMax * 1.12 : 100000;
        const stepValue = maxValue / 4;
        const steps = [4, 3, 2, 1, 0].map((step) => stepValue * step);

        ctx.font = "500 11px Inter, Urbanist, sans-serif";
        ctx.textBaseline = "middle";
        ctx.textAlign = "right";
        ctx.strokeStyle = "#edf0f4";
        ctx.lineWidth = 1;
        ctx.fillStyle = "#6a7282";

        steps.forEach((value, index) => {
            const y = pad.top + (plotHeight / (steps.length - 1)) * index;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(width - pad.right, y);
            ctx.stroke();
            ctx.fillText(compactMoney(value), pad.left - 10, y);
        });

        ctx.textAlign = "center";
        const fallbackLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
        const drawLabels = labels.length ? labels : fallbackLabels;
        const gap = drawLabels.length > 1 ? plotWidth / (drawLabels.length - 1) : plotWidth;
        drawLabels.forEach((label, index) => {
            const x = pad.left + gap * index;
            ctx.fillText(String(label), x, height - 15);
            ctx.beginPath();
            ctx.moveTo(x, pad.top);
            ctx.lineTo(x, pad.top + plotHeight);
            ctx.stroke();
        });

        const drawValues = values.length
            ? values.map((value) => Number(value || 0))
            : [0, 0, 0, 0, 0, 0, 0];
        const points = drawValues.map((value, index) => ({
            x: pad.left + gap * index,
            y: pad.top + plotHeight - (value / maxValue) * plotHeight,
        }));

        ctx.beginPath();
        points.forEach((point, index) => {
            if (index === 0) {
                ctx.moveTo(point.x, point.y);
            } else {
                const previous = points[index - 1];
                const controlX = previous.x + (point.x - previous.x) / 2;
                ctx.bezierCurveTo(controlX, previous.y, controlX, point.y, point.x, point.y);
            }
        });
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();

        points.forEach((point) => {
            ctx.beginPath();
            ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = "#3b82f6";
            ctx.fill();
        });
    }
}

publicWidget.registry.UnitradeSellerDashboard = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-dashboard-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.dashboardPayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller dashboard payload:", error);
        }
        const payload = payloadFromDataset(this.el.dataset, parsed);
        const fallbackNodes = Array.from(this.el.childNodes);
        const mountTarget = document.createElement("div");
        mountTarget.className = "ut-owl-mount-host";
        this.el.appendChild(mountTarget);
        try {
            this.component = await mount(SellerDashboard, mountTarget, {
                props: { payload },
                templates,
            });
            fallbackNodes.forEach((node) => node.remove());
        } catch (error) {
            mountTarget.remove();
            console.error("[UniTrade] Seller dashboard mount:", error);
            this.el.classList.add("ut-owl-mount-failed");
            if (!this.el.querySelector(".ut-owl-fallback-error")) {
                const fallback = document.createElement("div");
                fallback.className = "ut-owl-fallback-error";
                fallback.textContent = "Dashboard penjual belum bisa dimuat. Muat ulang halaman setelah modul di-upgrade.";
                this.el.appendChild(fallback);
            }
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
