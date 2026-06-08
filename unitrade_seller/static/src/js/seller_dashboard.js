/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import {
    readSellerSidebarOpen,
    sellerSidebarActiveKey,
    sellerSidebarItems,
    writeSellerSidebarOpen,
} from "./seller_sidebar";

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

function todayInputValue() {
    return formatDateInput(new Date());
}

function formatDateInput(date) {
    return [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
    ].join("-");
}

function inputValueFromDate(value) {
    const date = value ? new Date(`${value}T00:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) {
        return todayInputValue();
    }
    return formatDateInput(date);
}

function shiftDateValue(value, days) {
    const date = new Date(`${inputValueFromDate(value)}T00:00:00`);
    date.setDate(date.getDate() + days);
    return formatDateInput(date);
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
            available_balance: Number(dataset.availableBalance || 0),
            payoutable_balance_label: dataset.payoutableBalanceLabel || "Rp 0",
            pending_payout_label: dataset.pendingPayoutLabel || "Rp 0",
            released_balance_label: dataset.releasedBalanceLabel || "Rp 0",
            used_balance_label: dataset.usedBalanceLabel || "Rp 0",
            payout_ready: false,
            can_request_payout: false,
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
        date_filter: {
            value: todayInputValue(),
            mode: "day",
            label: todayLabel(),
            display_label: todayLabel(),
            today_value: todayInputValue(),
            is_today: true,
        },
        orders_period: "weekly",
            current_date_label: todayLabel(),
            add_product_url: dataset.addProductUrl || "",
            data_url: "/unitrade/seller/dashboard/data",
            payout_request_url: "/unitrade/seller/payout/request",
            payout_settings_url: "/unitrade/seller/settings#payout-settings",
            payout_page_url: "/unitrade/seller/payouts",
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
        this.chartFrame = null;
        this.dashboardDataInFlightKey = "";
        this.dashboardDataInFlightPromise = null;
        this.dashboardRequestSeq = 0;
        this.isDestroyed = false;
        this.onResize = () => this.scheduleDrawChart();
        const initialPayload = this.props.payload || {};
        const initialDate = (initialPayload.date_filter && initialPayload.date_filter.value) || todayInputValue();
        const initialDateMode = (initialPayload.date_filter && initialPayload.date_filter.mode) || "day";
        this.onDocumentClick = (ev) => {
            const target = ev.target;
            if (this.state.datePickerOpen && target && target.closest && !target.closest(".ut-dash-date-control")) {
                this.state.datePickerOpen = false;
            }
        };
        this.onSidebarHashChange = () => {
            this.state.sidebarActiveKey = sellerSidebarActiveKey("dashboard");
        };
        this.state = useState({
            period: "weekly",
            payload: initialPayload,
            query: "",
            searchOpen: false,
            sidebarOpen: readSellerSidebarOpen(),
            sidebarActiveKey: sellerSidebarActiveKey("dashboard"),
            ready: true,
            handoffOrder: null,
            datePickerOpen: false,
            dateValue: initialDate,
            dateMode: initialDateMode,
            ordersPeriod: initialPayload.orders_period || "weekly",
            dateLoading: false,
            dateError: "",
        });

        onMounted(() => {
            window.addEventListener("resize", this.onResize);
            window.addEventListener("hashchange", this.onSidebarHashChange);
            document.addEventListener("click", this.onDocumentClick);
            this.scheduleDrawChart();
        });

        onWillUnmount(() => {
            this.isDestroyed = true;
            if (this.chartFrame) {
                window.cancelAnimationFrame(this.chartFrame);
                this.chartFrame = null;
            }
            window.removeEventListener("resize", this.onResize);
            window.removeEventListener("hashchange", this.onSidebarHashChange);
            document.removeEventListener("click", this.onDocumentClick);
        });

        useEffect(
            () => {
                if (this.state.ready) {
                    this.scheduleDrawChart();
                }
            },
            () => [this.state.period, this.state.ready, this.state.payload]
        );
    }

    get payload() {
        return this.state.payload || this.props.payload || {};
    }

    get seller() {
        return this.payload.seller || {};
    }

    get stats() {
        return this.payload.stats || {};
    }

    get dateFilter() {
        return this.payload.date_filter || {};
    }

    get dateLabel() {
        return this.dateFilter.label || this.payload.current_date_label || todayLabel();
    }

    get dateDisplayLabel() {
        return this.dateFilter.display_label || this.dateLabel;
    }

    get orders() {
        return (this.payload.orders || []).slice(0, 4);
    }

    get ordersPeriod() {
        return this.payload.orders_period || this.state.ordersPeriod || "weekly";
    }

    get ordersPeriodLabel() {
        return this.ordersPeriod === "monthly" ? "30 hari terakhir" : "7 hari terakhir";
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

    get reviews() {
        return (this.payload.reviews || []).slice(0, 6);
    }

    get payoutPageUrl() {
        return this.payload.payout_page_url || "/unitrade/seller/payouts";
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get sidebarActiveKey() {
        return this.state.sidebarActiveKey || sellerSidebarActiveKey("dashboard");
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
            title: `${order.order_name || "Pesanan"} - ${order.customer_name || "Pembeli"}`,
            subtitle: `${order.product_name || ""} - ${order.status_label || ""}`,
            url: order.detail_url || order.order_detail_url || order.action_url || "#dashboard-orders",
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

    dateModeClass(mode) {
        const base = "ut-dash-date-preset";
        const activeMode = (this.payload.date_filter && this.payload.date_filter.mode) || this.state.dateMode || "day";
        return activeMode === mode ? `${base} is-active` : base;
    }

    ordersPeriodClass(period) {
        const base = "ut-dash-orders-period-btn";
        return this.ordersPeriod === period ? `${base} is-active` : base;
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

    setOrdersPeriod(period) {
        if (!["weekly", "monthly"].includes(period) || this.state.dateLoading) {
            return;
        }
        this.state.ordersPeriod = period;
        return this.loadDashboardForDate(this.state.dateValue, this.state.dateMode, period);
    }

    toggleDatePicker(ev) {
        if (ev && ev.stopPropagation) {
            ev.stopPropagation();
        }
        this.state.datePickerOpen = !this.state.datePickerOpen;
    }

    onDateInputChange(ev) {
        this.state.dateValue = ev.target.value || todayInputValue();
        this.state.dateMode = "day";
        this.state.dateError = "";
    }

    async loadDashboardForDate(value, mode = this.state.dateMode, ordersPeriod = this.state.ordersPeriod) {
        const selectedDate = inputValueFromDate(value || this.state.dateValue);
        const selectedMode = ["day", "month", "all"].includes(mode) ? mode : "day";
        const selectedOrdersPeriod = ["weekly", "monthly"].includes(ordersPeriod) ? ordersPeriod : "weekly";
        const requestKey = `${selectedDate}|${selectedMode}|${selectedOrdersPeriod}`;
        if (this.dashboardDataInFlightPromise && this.dashboardDataInFlightKey === requestKey) {
            return this.dashboardDataInFlightPromise;
        }
        const requestSeq = ++this.dashboardRequestSeq;
        this.state.dateValue = selectedDate;
        this.state.dateMode = selectedMode;
        this.state.ordersPeriod = selectedOrdersPeriod;
        this.state.dateLoading = true;
        this.state.dateError = "";
        this.dashboardDataInFlightKey = requestKey;
        this.dashboardDataInFlightPromise = (async () => {
            try {
                const payload = await jsonrpc(this.payload.data_url || "/unitrade/seller/dashboard/data", {
                    date: selectedDate,
                    date_mode: selectedMode,
                    orders_period: selectedOrdersPeriod,
                });
                if (!payload || payload.success === false) {
                    throw new Error((payload && payload.message) || "Data dashboard belum bisa dimuat.");
                }
                if (this.isDestroyed || requestSeq !== this.dashboardRequestSeq) {
                    return payload;
                }
                this.state.payload = payload;
                this.state.dateValue = (payload.date_filter && payload.date_filter.value) || selectedDate;
                this.state.dateMode = (payload.date_filter && payload.date_filter.mode) || selectedMode;
                this.state.ordersPeriod = payload.orders_period || selectedOrdersPeriod;
                this.state.datePickerOpen = false;
                const url = new URL(window.location.href);
                url.searchParams.set("date", this.state.dateValue);
                url.searchParams.set("date_mode", this.state.dateMode);
                url.searchParams.set("orders_period", this.state.ordersPeriod);
                window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
                this.scheduleDrawChart();
                return payload;
            } catch (error) {
                if (!this.isDestroyed && requestSeq === this.dashboardRequestSeq) {
                    this.state.dateError = error.message || "Data dashboard belum bisa dimuat.";
                }
                return null;
            } finally {
                if (requestSeq === this.dashboardRequestSeq) {
                    this.state.dateLoading = false;
                }
                if (this.dashboardDataInFlightKey === requestKey) {
                    this.dashboardDataInFlightKey = "";
                    this.dashboardDataInFlightPromise = null;
                }
            }
        })();
        return this.dashboardDataInFlightPromise;
    }

    scheduleDrawChart() {
        if (this.isDestroyed || this.chartFrame) {
            return;
        }
        this.chartFrame = window.requestAnimationFrame(() => {
            this.chartFrame = null;
            this.drawChart();
        });
    }

    applyDateFilter() {
        return this.loadDashboardForDate(this.state.dateValue, "day", this.state.ordersPeriod);
    }

    shiftDate(days) {
        const nextDate = shiftDateValue(this.state.dateValue, days);
        this.state.dateValue = nextDate;
        return this.loadDashboardForDate(nextDate, "day", this.state.ordersPeriod);
    }

    setToday() {
        const today = todayInputValue();
        this.state.dateValue = today;
        return this.loadDashboardForDate(today, "day", this.state.ordersPeriod);
    }

    setLastMonth() {
        const anchorDate = this.state.dateValue || todayInputValue();
        return this.loadDashboardForDate(anchorDate, "month", this.state.ordersPeriod);
    }

    setAllTime() {
        const anchorDate = this.state.dateValue || todayInputValue();
        return this.loadDashboardForDate(anchorDate, "all", this.state.ordersPeriod);
    }

    openSearch() {
        this.state.searchOpen = true;
    }

    closeSearch() {
        this.state.searchOpen = false;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        writeSellerSidebarOpen(this.state.sidebarOpen);
        window.setTimeout(() => this.scheduleDrawChart(), 300);
    }

    closeSidebar() {
        this.state.sidebarOpen = false;
        writeSellerSidebarOpen(false);
        window.setTimeout(() => this.scheduleDrawChart(), 300);
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
        if (this.isDestroyed || !this.state.ready) {
            return;
        }
        const canvas = this.chartRef.el;
        if (!canvas || !canvas.getContext) {
            return;
        }
        const data = (this.payload.chart || {})[this.state.period] || (this.payload.chart || {}).weekly || {};
        const labels = data.labels || [];
        const revenueValues = (data.revenue || []).map((value) => Number(value || 0));
        const orderValues = (data.orders || []).map((value) => Number(value || 0));
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
        const rawMax = Math.max(...revenueValues, 0);
        const maxValue = rawMax > 0 ? rawMax * 1.12 : 100000;
        const maxOrders = Math.max(...orderValues, 0) || 1;
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
        const fallbackLabels = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];
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

        const drawValues = revenueValues.length
            ? revenueValues
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

        if (orderValues.length) {
            const orderPoints = orderValues.map((value, index) => ({
                x: pad.left + gap * index,
                y: pad.top + plotHeight - (value / maxOrders) * plotHeight,
            }));
            ctx.beginPath();
            orderPoints.forEach((point, index) => {
                if (index === 0) {
                    ctx.moveTo(point.x, point.y);
                } else {
                    const previous = orderPoints[index - 1];
                    const controlX = previous.x + (point.x - previous.x) / 2;
                    ctx.bezierCurveTo(controlX, previous.y, controlX, point.y, point.x, point.y);
                }
            });
            ctx.strokeStyle = "#f97316";
            ctx.lineWidth = 2;
            ctx.stroke();

            orderPoints.forEach((point) => {
                ctx.beginPath();
                ctx.arc(point.x, point.y, 3, 0, Math.PI * 2);
                ctx.fillStyle = "#f97316";
                ctx.fill();
            });
        }
    }
}

publicWidget.registry.UnitradeSellerDashboard = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-dashboard-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        if (this.el.dataset.utSellerDashboardMounted === "1") {
            return superPromise;
        }
        this.el.dataset.utSellerDashboardMounted = "1";
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
            const staticFallback = this.el.querySelector("[data-ut-dashboard-static-fallback='1']");
            if (staticFallback) {
                staticFallback.style.display = "block";
            }
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

publicWidget.registry.UnitradeSellerDashboardStaticSidebar = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-dashboard-static",
    events: {
        "click [data-ut-static-sidebar-toggle='1']": "_onToggleSidebar",
        "click .ut-dash-mobile-scrim": "_onCloseSidebar",
    },

    start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        if (this.el.dataset.utSellerStaticSidebarMounted === "1") {
            return superPromise;
        }
        this.el.dataset.utSellerStaticSidebarMounted = "1";
        this.dashboardPage = this.el.querySelector("[data-ut-dashboard-static-fallback='1']");
        this.toggleButton = this.el.querySelector("[data-ut-static-sidebar-toggle='1']");
        this._setSidebarOpen(false);
        return superPromise;
    },

    _onToggleSidebar() {
        this._setSidebarOpen(!this._isSidebarOpen());
    },

    _onCloseSidebar() {
        this._setSidebarOpen(false);
    },

    _isSidebarOpen() {
        return Boolean(this.dashboardPage && this.dashboardPage.classList.contains("ut-is-sidebar-open"));
    },

    _setSidebarOpen(isOpen) {
        if (!this.dashboardPage) {
            return;
        }
        this.dashboardPage.classList.toggle("ut-is-sidebar-open", isOpen);
        if (!this.toggleButton) {
            return;
        }
        const icon = this.toggleButton.querySelector("i");
        const label = this.toggleButton.querySelector(".ut-dash-sidebar-button-label");
        this.toggleButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
        this.toggleButton.setAttribute("aria-label", isOpen ? "Tutup sidebar" : "Buka sidebar");
        if (icon) {
            icon.className = isOpen ? "fa fa-angle-left" : "fa fa-angle-right";
        }
        if (label) {
            label.textContent = isOpen ? "Sembunyikan" : "Buka";
        }
    },
});
