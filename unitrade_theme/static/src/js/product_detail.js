/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

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
