/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.UnitradeProductDetailSkeleton = publicWidget.Widget.extend({
    selector: "#product_detail.ut-product-detail-hydrating",

    start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        this._isRevealed = false;
        this._fallbackTimer = window.setTimeout(() => this._revealContent(), 1800);

        const revealAfterFrame = () => {
            window.requestAnimationFrame(() => {
                window.setTimeout(() => this._revealContent(), 180);
            });
        };

        if (document.readyState === "complete") {
            revealAfterFrame();
        } else {
            this._onWindowLoad = revealAfterFrame;
            window.addEventListener("load", this._onWindowLoad, { once: true });
        }

        return superPromise;
    },

    destroy() {
        if (this._fallbackTimer) {
            window.clearTimeout(this._fallbackTimer);
        }
        if (this._onWindowLoad) {
            window.removeEventListener("load", this._onWindowLoad);
        }
        if (this._super) {
            this._super.apply(this, arguments);
        }
    },

    _revealContent() {
        if (this._isRevealed || !this.el) {
            return;
        }
        this._isRevealed = true;
        if (this._fallbackTimer) {
            window.clearTimeout(this._fallbackTimer);
            this._fallbackTimer = null;
        }
        this.el.classList.remove("ut-product-detail-hydrating");
        this.el.classList.add("ut-product-detail-loaded");
    },
});

publicWidget.registry.UnitradeProductDetailHashTabs = publicWidget.Widget.extend({
    selector: "#product_detail",

    start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        window.setTimeout(() => this._activateInitialTab(), 0);
        return superPromise;
    },

    _activateInitialTab() {
        const params = new URLSearchParams(window.location.search);
        if (window.location.hash !== "#tab-ulasan" && params.get("tab") !== "reviews") {
            return;
        }
        const reviewTab = document.getElementById("ut-tab-ulasan");
        const reviewPanel = document.getElementById("tab-ulasan");
        if (reviewTab) {
            reviewTab.click();
        }
        if (reviewPanel) {
            reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    },
});

publicWidget.registry.UnitradeProductWishlistDirect = publicWidget.Widget.extend({
    selector: "#product_detail",
    events: {
        "click .ut-product-wishlist-direct": "_onWishlistClick",
    },

    async _onWishlistClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        const button = ev.currentTarget;
        const productId = parseInt(button.dataset.productId, 10);
        if (!productId || button.disabled) {
            return;
        }

        button.disabled = true;
        button.classList.add("is-loading");

        try {
            const result = await jsonrpc("/unitrade/wishlist/toggle", {
                product_id: productId,
            });

            if (!result || result.success === false) {
                throw new Error((result && result.message) || "Wishlist update failed");
            }

            const isActive = Boolean(result.added);
            button.dataset.active = isActive ? "1" : "0";
            button.classList.toggle("is-active", isActive);
            button.setAttribute("title", isActive ? "Lihat wishlist" : "Tambahkan ke wishlist");
            this._showWishlistFeedback(button, isActive ? "Ditambahkan ke wishlist" : "Dihapus dari wishlist", isActive);
        } catch (error) {
            if (error && (error.message || "").includes("Session expired")) {
                window.location.href = `/web/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
                return;
            }
            this._showWishlistFeedback(button, "Wishlist gagal diperbarui", false);
            console.error("[UniTrade] Wishlist direct:", error);
        } finally {
            button.disabled = false;
            button.classList.remove("is-loading");
        }
    },

    _showWishlistFeedback(button, message, showLink) {
        const wrapper = button.parentElement;
        if (!wrapper) {
            return;
        }

        let feedback = wrapper.querySelector(".ut-product-wishlist-feedback");
        if (!feedback) {
            feedback = document.createElement("a");
            feedback.className = "ut-product-wishlist-feedback";
            wrapper.appendChild(feedback);
        }

        feedback.textContent = message;
        feedback.href = showLink ? "/my/wishlist" : "#";
        feedback.classList.toggle("is-link", showLink);
        feedback.classList.add("is-visible");

        window.clearTimeout(this._wishlistFeedbackTimer);
        this._wishlistFeedbackTimer = window.setTimeout(() => {
            feedback.classList.remove("is-visible");
        }, 2400);
    },
});
