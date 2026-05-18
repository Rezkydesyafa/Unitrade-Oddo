/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { sellerSidebarItems } from "./seller_sidebar";

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
        date_filter: dataset.dateFilter || "30",
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
        this.state = useState({
            ready: false,
            loading: true,
            error: "",
            query: "",
            dateFilter: payload.date_filter || "30",
            sidebarOpen: false,
            seller: payload.seller || {},
            stats: payload.stats || {},
            products: payload.products || [],
            addProductUrl: payload.add_product_url || "",
        });

        onMounted(() => this.loadProducts());
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

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get sidebarActiveKey() {
        return "products";
    }

    get sidebarClass() {
        return "ut-products-sidebar";
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get filteredProducts() {
        const query = this.state.query.trim().toLowerCase();
        return this.state.products.filter((product) => {
            if (!query) {
                return true;
            }
            return [
                product.product_code,
                product.name,
                product.condition_label,
                product.stock_label,
                product.date_label,
            ].join(" ").toLowerCase().includes(query);
        });
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    conditionClass(product) {
        const key = product.condition_key || "used";
        return `ut-products-condition ut-products-condition-${key}`;
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

    onDateFilterChange(ev) {
        this.state.dateFilter = ev.target.value || "30";
        return this.loadProducts();
    }

    async loadProducts() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc("/unitrade/seller/products/data", {
                date_filter: this.state.dateFilter,
            });
            if (!result.success) {
                throw new Error(result.message || "Produk belum bisa dimuat.");
            }
            this.state.products = result.products || [];
            this.state.dateFilter = result.date_filter || this.state.dateFilter;
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
        this.el.innerHTML = "";
        this.component = await mount(SellerProducts, this.el, {
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
