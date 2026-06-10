/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";

function intOrDefault(value, fallback = 0) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}

export class ProductWishlistButton extends Component {
    static template = "unitrade_theme.ProductWishlistButton";
    static props = {
        productId: Number,
        active: Boolean,
    };

    setup() {
        this.state = useState({
            active: this.props.active,
            loading: false,
        });
    }

    get buttonClass() {
        const base = "tw-w-12 tw-h-12 tw-rounded-full tw-text-white tw-border-0 tw-flex tw-items-center tw-justify-center tw-shrink-0 tw-cursor-pointer tw-transition-all";
        if (this.state.active) {
            return `${base} tw-bg-[#991b1b] hover:tw-bg-[#7f1d1d]`;
        }
        return `${base} tw-bg-[#dc2626] hover:tw-bg-[#b91c1c]`;
    }

    async toggle() {
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        try {
            const result = await jsonrpc("/unitrade/wishlist/toggle", {
                product_id: this.props.productId,
            });
            this.state.active = Boolean(result.added);
        } catch (error) {
            console.error("[UniTrade] Wishlist:", error);
        } finally {
            this.state.loading = false;
        }
    }
}

export class ProductReviewPanel extends Component {
    static template = "unitrade_theme.ProductReviewPanel";
    static props = {
        productId: Number,
    };

    setup() {
        this.limit = 2;
        this.state = useState({
            reviews: [],
            summary: { total: 0, average: 0, counts: {} },
            sort: "newest",
            rating: null,
            offset: 0,
            hasMore: false,
            canReview: false,
            loading: true,
            loadingMore: false,
            submitting: false,
            formRating: 5,
            comment: "",
            imageData: "",
            imagePreview: "",
            imageName: "",
            previewImageUrl: "",
            previewImageAlt: "Preview gambar ulasan",
            message: "",
            error: false,
            isPublic: false,
            reportModalOpen: false,
            reportReview: null,
            reportReason: "",
            reportNote: "",
            reportSubmitting: false,
            reportMessage: "",
            reportError: false,
        });

        onMounted(() => this.loadReviews({ reset: true }));
    }

    chipClass(active) {
        return active ? "ut-review-chip ut-review-chip-active" : "ut-review-chip";
    }

    getRatingCount(star) {
        const counts = this.state.summary.counts || {};
        return counts[String(star)] || 0;
    }

    summaryStarStyle(star) {
        const active = star <= Math.round(this.state.summary.average || 0);
        return `color:${active ? "var(--ut-color-danger)" : "var(--ut-color-border)"}; font-size:20px;`;
    }

    reviewStarStyle(rating, star) {
        return `color:${star <= rating ? "var(--ut-color-danger)" : "var(--ut-color-border)"}; font-size:14px;`;
    }

    helpfulButtonClass(review) {
        const base = "ut-review-helpful";
        return review && review.helpful_active ? `${base} ut-review-helpful-active` : base;
    }

    helpfulIconStyle(review) {
        const color = review && review.helpful_active ? "var(--ut-color-button-bg)" : "var(--ut-color-border)";
        return `color:${color}; font-size:12px;`;
    }

    helpfulLabel(review) {
        const count = review && Number.isFinite(Number(review.helpful_count)) ? Number(review.helpful_count) : 0;
        return `Membantu (${count})`;
    }

    reviewImageAlt(review, index) {
        const name = review && review.user_name ? review.user_name : "pengguna";
        return `Gambar ulasan ${index + 1} dari ${name}`;
    }

    formStarStyle(star) {
        const active = star <= this.state.formRating;
        return `border:none; background:transparent; color:${active ? "var(--ut-color-danger)" : "var(--ut-color-border)"}; font-size:22px; cursor:pointer; padding:0 2px;`;
    }

    async loadReviews(options = {}) {
        const reset = Boolean(options.reset);
        if (reset) {
            this.state.loading = true;
            this.state.offset = 0;
        } else {
            this.state.loadingMore = true;
        }

        try {
            const result = await jsonrpc("/unitrade/reviews/list", {
                product_id: this.props.productId,
                sort: this.state.sort,
                rating: this.state.rating,
                limit: this.limit,
                offset: reset ? 0 : this.state.offset,
            });
            if (!result.success) {
                throw new Error(result.message || "Gagal memuat ulasan");
            }

            this.state.reviews = reset
                ? result.reviews
                : this.state.reviews.concat(result.reviews);
            this.state.summary = result.summary || { total: 0, average: 0, counts: {} };
            this.state.hasMore = Boolean(result.has_more);
            this.state.canReview = Boolean(result.can_review);
            this.state.isPublic = Boolean(result.is_public);
            this.state.offset = this.state.reviews.length;
        } catch (error) {
            console.error("[UniTrade] Reviews:", error);
            this.state.message = "Gagal memuat ulasan.";
            this.state.error = true;
        } finally {
            this.state.loading = false;
            this.state.loadingMore = false;
        }
    }

    setSort(sort) {
        this.state.sort = sort;
        this.loadReviews({ reset: true });
    }

    setRating(rating) {
        this.state.rating = this.state.rating === rating ? null : rating;
        this.loadReviews({ reset: true });
    }

    clearRating() {
        this.state.rating = null;
        this.loadReviews({ reset: true });
    }

    setFormRating(rating) {
        this.state.formRating = rating;
    }

    onImageChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        this.state.imageData = "";
        this.state.imagePreview = "";
        this.state.imageName = "";
        this.state.message = "";
        this.state.error = false;

        if (!file) {
            return;
        }

        const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
        if (!allowedTypes.includes(file.type)) {
            this.state.message = "Format gambar harus JPG, PNG, atau WebP.";
            this.state.error = true;
            ev.target.value = "";
            return;
        }

        if (file.size >= 2 * 1024 * 1024) {
            this.state.message = "Ukuran gambar harus kurang dari 2 MB.";
            this.state.error = true;
            ev.target.value = "";
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            this.state.imageData = reader.result;
            this.state.imagePreview = reader.result;
            this.state.imageName = file.name;
        };
        reader.onerror = () => {
            this.state.message = "Gambar gagal dibaca.";
            this.state.error = true;
            ev.target.value = "";
        };
        reader.readAsDataURL(file);
    }

    clearImage() {
        this.state.imageData = "";
        this.state.imagePreview = "";
        this.state.imageName = "";
    }

    openReviewImage(imageUrl, altText) {
        if (!imageUrl) {
            return;
        }
        this.state.previewImageUrl = imageUrl;
        this.state.previewImageAlt = altText || "Preview gambar ulasan";
    }

    closeReviewImage() {
        this.state.previewImageUrl = "";
        this.state.previewImageAlt = "Preview gambar ulasan";
    }

    loadMore() {
        this.loadReviews({ reset: false });
    }

    redirectToLogin() {
        window.location.href = `/web/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search + window.location.hash)}`;
    }

    async toggleHelpful(review) {
        if (!review || review.helpful_loading) {
            return;
        }
        if (this.state.isPublic) {
            this.redirectToLogin();
            return;
        }

        review.helpful_loading = true;
        try {
            const result = await jsonrpc("/unitrade/reviews/helpful/toggle", {
                review_id: review.id,
            });
            if (!result.success) {
                throw new Error(result.message || "Vote membantu gagal diperbarui.");
            }
            review.helpful_active = Boolean(result.active);
            review.helpful_count = Number(result.helpful_count || 0);
        } catch (error) {
            if (error && (error.message || "").includes("Session expired")) {
                this.redirectToLogin();
                return;
            }
            console.error("[UniTrade] Review helpful:", error);
        } finally {
            review.helpful_loading = false;
        }
    }

    openReportModal(review) {
        if (!review) {
            return;
        }
        if (this.state.isPublic) {
            this.redirectToLogin();
            return;
        }
        if (review.report_active) {
            return;
        }
        this.state.reportReview = review;
        this.state.reportReason = "";
        this.state.reportNote = "";
        this.state.reportMessage = "";
        this.state.reportError = false;
        this.state.reportModalOpen = true;
    }

    closeReportModal() {
        if (this.state.reportSubmitting) {
            return;
        }
        this.state.reportModalOpen = false;
        this.state.reportReview = null;
        this.state.reportReason = "";
        this.state.reportNote = "";
        this.state.reportMessage = "";
        this.state.reportError = false;
    }

    get reportFormValid() {
        return Boolean(this.state.reportReview && this.state.reportReason);
    }

    async submitReport() {
        if (this.state.reportSubmitting || !this.reportFormValid) {
            return;
        }

        this.state.reportSubmitting = true;
        this.state.reportMessage = "";
        this.state.reportError = false;
        try {
            const result = await jsonrpc("/unitrade/reviews/report", {
                review_id: this.state.reportReview.id,
                reason: this.state.reportReason,
                note: this.state.reportNote,
            });
            if (!result.success) {
                this.state.reportMessage = result.message || "Laporan ulasan gagal dikirim.";
                this.state.reportError = true;
                if (result.already_reported && this.state.reportReview) {
                    this.state.reportReview.report_active = true;
                }
                return;
            }
            if (this.state.reportReview) {
                this.state.reportReview.report_active = true;
            }
            this.state.reportMessage = result.message || "Laporan ulasan berhasil dikirim.";
            window.setTimeout(() => {
                if (!this.state.reportSubmitting) {
                    this.closeReportModal();
                }
            }, 900);
        } catch (error) {
            if (error && (error.message || "").includes("Session expired")) {
                this.redirectToLogin();
                return;
            }
            console.error("[UniTrade] Review report:", error);
            this.state.reportMessage = "Laporan ulasan gagal dikirim.";
            this.state.reportError = true;
        } finally {
            this.state.reportSubmitting = false;
        }
    }

    async submitReview() {
        if (this.state.submitting) {
            return;
        }
        this.state.submitting = true;
        this.state.message = "";
        this.state.error = false;
        try {
            const result = await jsonrpc("/unitrade/reviews/create", {
                product_id: this.props.productId,
                rating: this.state.formRating,
                comment: this.state.comment,
                images: this.state.imageData ? [this.state.imageData] : [],
            });
            if (!result.success) {
                this.state.message = result.message || "Ulasan gagal dikirim.";
                this.state.error = true;
                return;
            }
            this.state.message = result.message || "Ulasan berhasil dikirim.";
            this.state.comment = "";
            this.clearImage();
            this.state.canReview = Boolean(result.can_review);
            await this.loadReviews({ reset: true });
        } catch (error) {
            console.error("[UniTrade] Create review:", error);
            this.state.message = "Ulasan gagal dikirim.";
            this.state.error = true;
        } finally {
            this.state.submitting = false;
        }
    }
}

publicWidget.registry.UnitradeProductWishlistOwl = publicWidget.Widget.extend({
    selector: "#ut-product-wishlist-owl",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const productId = intOrDefault(this.el.dataset.productId);
        if (!productId) {
            return superPromise;
        }
        const props = {
            productId,
            active: this.el.dataset.active === "1",
        };
        this.el.innerHTML = "";
        this.component = await mount(ProductWishlistButton, this.el, { props, templates });
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

publicWidget.registry.UnitradeProductReviewOwl = publicWidget.Widget.extend({
    selector: "#ut-product-review-owl",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        const productId = intOrDefault(this.el.dataset.productId);
        if (!productId) {
            return superPromise;
        }
        this.el.innerHTML = "";
        this.component = await mount(ProductReviewPanel, this.el, {
            props: { productId },
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
