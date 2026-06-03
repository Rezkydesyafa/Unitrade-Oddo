/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";
import { mountSellerApp } from "./seller_mount";

function parsePayload(dataset) {
    try {
        return JSON.parse(dataset.productDetailPayload || "{}");
    } catch (error) {
        console.error("[UniTrade] Seller product detail payload:", error);
        return {};
    }
}

export class SellerProductDetail extends Component {
    static template = "unitrade_seller.SellerProductDetail";
    static props = {
        payload: Object,
    };

    setup() {
        this.state = useState({
            ready: false,
            sidebarOpen: readSellerSidebarOpen(),
            imagePreview: null,
            payload: this.props.payload || {},
        });

        onMounted(() => {
            window.setTimeout(() => {
                this.state.ready = true;
            }, 120);
        });
    }

    get payload() {
        return this.state.payload || {};
    }

    get seller() {
        return this.payload.seller || {};
    }

    get stats() {
        return this.payload.stats || {};
    }

    get product() {
        return this.payload.product || {};
    }

    get status() {
        return this.product.status || {};
    }

    get actions() {
        return this.product.actions || {};
    }

    get reviews() {
        return this.product.reviews || { summary: {}, items: [] };
    }

    get sidebarActiveKey() {
        return "products";
    }

    get sidebarClass() {
        return "ut-product-detail-sidebar";
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

    get mainImage() {
        const images = this.product.images || [];
        return images[0] || { url: this.product.image_url, alt: this.product.name };
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    statusClass(status = this.status) {
        return `ut-product-detail-status ut-product-detail-status-${status.key || "draft"}`;
    }

    conditionClass() {
        return `ut-products-condition ut-products-condition-${this.product.condition_key || "used"}`;
    }

    reviewKey(review) {
        return review.id || `${review.reviewer_name || "review"}-${review.date_label || ""}`;
    }

    imageKey(image) {
        return image.id || image.url || image;
    }

    ratingStars(rating) {
        const value = Math.round(Number(rating || 0));
        return [1, 2, 3, 4, 5].map((star) => ({
            star,
            active: star <= value,
        }));
    }

    reviewBarStyle(item) {
        const percent = Math.max(0, Math.min(100, Number(item.percent || 0)));
        return `width: ${percent}%`;
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

    openImagePreview(url, title, caption = "") {
        if (!url) {
            return;
        }
        this.state.imagePreview = { url, title, caption };
    }

    closeImagePreview() {
        this.state.imagePreview = null;
    }
}

publicWidget.registry.UnitradeSellerProductDetail = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-product-detail-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const payload = parsePayload(this.el.dataset);
        await mountSellerApp(this, SellerProductDetail, { payload }, templates, "Seller product detail");
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
