/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { sellerSidebarItems } from "./seller_sidebar";

const ALLOWED_TYPES = new Set(["image/png", "image/jpg", "image/jpeg", "image/webp"]);
const MAX_IMAGES = 4;
const MIN_IMAGES = 2;
const DEFAULT_MAX_FILE_SIZE = 5 * 1024 * 1024;

function toNumber(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function formatFileSize(size) {
    const bytes = Number(size || 0);
    if (bytes >= 1024 * 1024) {
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function formatRupiah(amount) {
    const value = Number(amount || 0);
    const rounded = Number.isFinite(value) ? Math.round(value) : 0;
    return `Rp ${rounded.toLocaleString("id-ID")}`;
}

function shortName(name) {
    const value = String(name || "produk.jpg");
    if (value.length <= 22) {
        return value;
    }
    const dotIndex = value.lastIndexOf(".");
    const ext = dotIndex > -1 ? value.slice(dotIndex) : "";
    return `${value.slice(0, 15)}...${ext}`;
}

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            resolve(result.includes(",") ? result.split(",", 2)[1] : result);
        };
        reader.onerror = () => reject(reader.error || new Error("File tidak bisa dibaca."));
        reader.readAsDataURL(file);
    });
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
        categories: [],
        max_file_size: DEFAULT_MAX_FILE_SIZE,
        products_url: "/unitrade/seller/products",
        dashboard_url: "/unitrade/seller/dashboard",
        mode: "create",
        title: "Tambah Barang",
        subtitle: "Here's what's happening with your store today",
        submit_label: "Post",
        delete_label: "Hapus",
        product_id: 0,
        product: null,
        data_url: "/unitrade/seller/products/new/data",
        submit_url: "/unitrade/seller/products/create",
        delete_url: "",
        payment_url: "",
    };
}

function paymentPayload(dataset, parsed) {
    if (parsed && parsed.product) {
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
        product: {
            id: 0,
            name: "Produk UniTrade",
            category: "Barang",
            price_label: "Rp 0",
            image_url: "/web/static/img/placeholder.png",
            products_url: "/unitrade/seller/products",
        },
        fees: {
            posting_fee: 0,
            posting_fee_label: "Rp 0",
            admin_fee: 0,
            admin_fee_label: "Rp 0",
            total: 0,
            total_label: "Rp 0",
            balance: 0,
            balance_label: "Rp 0",
            tier_label: "",
            percent_label: "",
        },
        methods: [],
        data_url: "",
        submit_url: "",
        existing_intent: {},
    };
}

export class SellerProductCreate extends Component {
    static template = "unitrade_seller.SellerProductCreate";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.fileInputRef = useRef("fileInput");
        this.state = useState({
            ready: false,
            loading: true,
            submitting: false,
            deleting: false,
            dragActive: false,
            error: "",
            success: "",
            sidebarOpen: false,
            mode: payload.mode || "create",
            title: payload.title || (payload.mode === "edit" ? "Edit Barang" : "Tambah Barang"),
            subtitle: payload.subtitle || (payload.mode === "edit" ? "Ubah isi informasi mengenai barang" : "Here's what's happening with your store today"),
            submitLabel: payload.submit_label || (payload.mode === "edit" ? "Simpan" : "Post"),
            deleteLabel: payload.delete_label || "Hapus",
            productId: payload.product_id || payload.product?.id || 0,
            dataUrl: payload.data_url || "/unitrade/seller/products/new/data",
            submitUrl: payload.submit_url || "/unitrade/seller/products/create",
            deleteUrl: payload.delete_url || "",
            paymentUrl: payload.payment_url || "",
            seller: payload.seller || {},
            stats: payload.stats || {},
            categories: payload.categories || [],
            maxFileSize: payload.max_file_size || DEFAULT_MAX_FILE_SIZE,
            productsUrl: payload.products_url || "/unitrade/seller/products",
            dashboardUrl: payload.dashboard_url || "/unitrade/seller/dashboard",
            form: {
                name: "",
                description: "",
                categoryId: "",
                price: "",
                discountPrice: "",
                stock: "",
            },
            images: [],
        });
        this.applyProductPayload(payload.product || null);

        onMounted(() => this.loadData());
        onWillUnmount(() => this.revokeImageUrls());
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get sidebarItems() {
        return sellerSidebarItems(this.sidebarActiveKey, this.stats);
    }

    get sidebarActiveKey() {
        return "products";
    }

    get sidebarClass() {
        return "ut-product-create-sidebar";
    }

    get uploadClass() {
        const base = "ut-product-create-upload";
        return this.state.dragActive ? `${base} is-dragging` : base;
    }

    get isEditMode() {
        return this.state.mode === "edit";
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    categoryClass(category) {
        const base = "ut-product-create-category";
        return String(this.state.form.categoryId) === String(category.id) ? `${base} is-active` : base;
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

    async loadData() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc(this.state.dataUrl, {});
            if (!result.success) {
                throw new Error(result.message || "Form belum bisa dimuat.");
            }
            this.state.seller = result.seller || this.state.seller;
            this.state.stats = result.stats || this.state.stats;
            this.state.categories = result.categories || [];
            this.state.maxFileSize = result.max_file_size || DEFAULT_MAX_FILE_SIZE;
            this.state.productsUrl = result.products_url || this.state.productsUrl;
            this.state.dashboardUrl = result.dashboard_url || this.state.dashboardUrl;
            this.state.mode = result.mode || this.state.mode;
            this.state.title = result.title || this.state.title;
            this.state.subtitle = result.subtitle || this.state.subtitle;
            this.state.submitLabel = result.submit_label || this.state.submitLabel;
            this.state.deleteLabel = result.delete_label || this.state.deleteLabel;
            this.state.productId = result.product_id || this.state.productId;
            this.state.submitUrl = result.submit_url || this.state.submitUrl;
            this.state.deleteUrl = result.delete_url || this.state.deleteUrl;
            this.state.paymentUrl = result.payment_url || this.state.paymentUrl;
            this.applyProductPayload(result.product || null);
        } catch (error) {
            console.error("[UniTrade] Seller product create:", error);
            this.state.error = error.message || "Form belum bisa dimuat.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }

    applyProductPayload(product) {
        if (!product) {
            return;
        }
        this.revokeImageUrls();
        this.state.form.name = product.name || "";
        this.state.form.description = product.description || "";
        this.state.form.categoryId = product.category_id ? String(product.category_id) : "";
        this.state.form.price = product.price || product.price === 0 ? String(product.price) : "";
        this.state.form.discountPrice = product.discount_price ? String(product.discount_price) : "";
        this.state.form.stock = product.stock || product.stock === 0 ? String(product.stock) : "";
        this.state.images = (product.images || []).map((image) => ({
            id: image.id,
            source: image.source || "",
            name: image.name || "Gambar produk",
            shortName: image.shortName || shortName(image.name || "Gambar produk"),
            size: image.size || 0,
            sizeLabel: image.sizeLabel || "Tersimpan",
            mimetype: image.mimetype || "image/jpeg",
            data: "",
            url: image.url,
            existing: true,
        }));
    }

    setField(field, ev) {
        this.state.form[field] = ev.target.value;
        this.state.error = "";
    }

    selectCategory(categoryId) {
        this.state.form.categoryId = String(categoryId);
        this.state.error = "";
    }

    openFileDialog() {
        this.fileInputRef.el?.click();
    }

    onDragEnter() {
        this.state.dragActive = true;
    }

    onDragLeave() {
        this.state.dragActive = false;
    }

    async onDrop(ev) {
        this.state.dragActive = false;
        await this.addFiles(Array.from(ev.dataTransfer?.files || []));
    }

    async onFileInput(ev) {
        await this.addFiles(Array.from(ev.target.files || []));
        ev.target.value = "";
    }

    async addFiles(files) {
        this.state.error = "";
        if (!files.length) {
            return;
        }
        if (this.state.images.length + files.length > MAX_IMAGES) {
            this.state.error = "Foto produk maksimal 4 gambar.";
            return;
        }

        const nextImages = [];
        for (const file of files) {
            if (!ALLOWED_TYPES.has(file.type)) {
                this.state.error = `Format ${file.name} tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.`;
                this.revokePendingUrls(nextImages);
                return;
            }
            if (file.size > this.state.maxFileSize) {
                this.state.error = `Ukuran ${file.name} melebihi 5MB.`;
                this.revokePendingUrls(nextImages);
                return;
            }
            const data = await readFileAsBase64(file);
            nextImages.push({
                id: `${Date.now()}-${file.name}-${Math.random()}`,
                name: file.name,
                shortName: shortName(file.name),
                size: file.size,
                sizeLabel: formatFileSize(file.size),
                mimetype: file.type,
                data,
                url: URL.createObjectURL(file),
            });
        }
        this.state.images = this.state.images.concat(nextImages);
    }

    removeImage(imageId) {
        const image = this.state.images.find((item) => item.id === imageId);
        if (image?.url && !image.existing) {
            URL.revokeObjectURL(image.url);
        }
        this.state.images = this.state.images.filter((item) => item.id !== imageId);
        this.state.error = "";
    }

    revokePendingUrls(images) {
        images.forEach((image) => {
            if (image.url && !image.existing) {
                URL.revokeObjectURL(image.url);
            }
        });
    }

    revokeImageUrls() {
        this.revokePendingUrls(this.state.images || []);
    }

    validateForm() {
        const form = this.state.form;
        const price = Number(form.price);
        const discountPrice = form.discountPrice === "" ? 0 : Number(form.discountPrice);
        const stock = Number(form.stock);
        if (!form.name.trim()) {
            return "Nama produk wajib diisi.";
        }
        if (!form.description.trim()) {
            return "Deskripsi produk wajib diisi.";
        }
        if (!form.categoryId) {
            return "Kategori produk wajib dipilih.";
        }
        if (!Number.isFinite(price) || price < 0) {
            return "Harga tidak boleh negatif.";
        }
        if (form.discountPrice !== "" && (!Number.isFinite(discountPrice) || discountPrice < 0)) {
            return "Harga diskon tidak boleh negatif.";
        }
        if (discountPrice && discountPrice >= price) {
            return "Harga diskon harus lebih kecil dari harga normal.";
        }
        if (!Number.isFinite(stock) || stock < 0) {
            return "Stok harus angka dan tidak boleh negatif.";
        }
        if (this.state.images.length < MIN_IMAGES || this.state.images.length > MAX_IMAGES) {
            return "Foto produk wajib minimal 2 gambar dan maksimal 4 gambar.";
        }
        return "";
    }

    async submitProduct() {
        if (this.state.submitting) {
            return;
        }
        this.state.error = this.validateForm();
        this.state.success = "";
        if (this.state.error) {
            return;
        }

        this.state.submitting = true;
        try {
            const form = this.state.form;
            const result = await jsonrpc(this.state.submitUrl, {
                name: form.name,
                description: form.description,
                category_id: Number(form.categoryId),
                price: Number(form.price || 0),
                discount_price: form.discountPrice === "" ? 0 : Number(form.discountPrice),
                stock: Number(form.stock || 0),
                images: this.state.images.map((image) => ({
                    existing: Boolean(image.existing),
                    source: image.source || "",
                    name: image.name,
                    mimetype: image.mimetype,
                    size: image.size,
                    data: image.data,
                })),
            });
            if (!result.success) {
                throw new Error(result.message || "Produk belum bisa diposting.");
            }
            this.state.success = result.message || (this.isEditMode ? "Perubahan produk berhasil disimpan." : "Produk berhasil diposting.");
            window.setTimeout(() => {
                window.location.href = result.payment_url || result.redirect_url || this.state.paymentUrl || this.state.productsUrl;
            }, 900);
        } catch (error) {
            console.error("[UniTrade] Seller product submit:", error);
            this.state.error = error.message || "Produk belum bisa diposting.";
        } finally {
            this.state.submitting = false;
        }
    }

    async deleteProduct() {
        if (!this.isEditMode || this.state.deleting || this.state.submitting) {
            return;
        }
        if (!window.confirm("Hapus barang ini dari toko Anda?")) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.deleting = true;
        try {
            const result = await jsonrpc(this.state.deleteUrl, {});
            if (!result.success) {
                throw new Error(result.message || "Produk belum bisa dihapus.");
            }
            this.state.success = result.message || "Produk berhasil dihapus.";
            window.setTimeout(() => {
                window.location.href = result.redirect_url || this.state.productsUrl;
            }, 900);
        } catch (error) {
            console.error("[UniTrade] Seller product delete:", error);
            this.state.error = error.message || "Produk belum bisa dihapus.";
        } finally {
            this.state.deleting = false;
        }
    }
}

export class SellerProductPayment extends Component {
    static template = "unitrade_seller.SellerProductPayment";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.state = useState({
            ready: false,
            loading: true,
            submitting: false,
            sidebarOpen: false,
            error: "",
            success: "",
            expandedMethod: "",
            selectedChannel: "",
            acceptedTerms: false,
            paymentResult: null,
            seller: payload.seller || {},
            stats: payload.stats || {},
            product: payload.product || {},
            fees: payload.fees || {},
            methods: payload.methods || [],
            dataUrl: payload.data_url || "",
            submitUrl: payload.submit_url || "",
            existingIntent: payload.existing_intent || {},
        });
        onMounted(() => this.loadData());
    }

    get seller() {
        return this.state.seller || {};
    }

    get stats() {
        return this.state.stats || {};
    }

    get rootClass() {
        const classes = ["ut-seller-dashboard-page", "tw-fixed", "tw-inset-0", "tw-z-[1100]", "tw-overflow-auto", "tw-bg-[#f5f5f7]"];
        if (this.state.sidebarOpen) {
            classes.push("ut-is-sidebar-open");
        }
        return classes.join(" ");
    }

    get sidebarItems() {
        return sellerSidebarItems("products", this.stats);
    }

    get sidebarClass() {
        return "ut-product-create-sidebar";
    }

    get canPay() {
        return Boolean(this.state.selectedChannel && this.state.acceptedTerms && !this.state.submitting);
    }

    get totalLabel() {
        return this.state.fees.total_label || formatRupiah(this.state.fees.total);
    }

    get productsUrl() {
        return this.state.product.products_url || "/unitrade/seller/products";
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    methodClass(method) {
        const classes = ["ut-product-payment-method"];
        if (this.state.expandedMethod === method.key) {
            classes.push("is-selected");
        }
        if ((method.channels || []).some((channel) => channel.key === this.state.selectedChannel)) {
            classes.push("has-selected-channel");
        }
        if (method.insufficient) {
            classes.push("is-warning");
        }
        return classes.join(" ");
    }

    channelClass(channel) {
        const classes = ["ut-product-payment-channel"];
        if (this.state.selectedChannel === channel.key) {
            classes.push("is-active");
        }
        return classes.join(" ");
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

    async loadData() {
        if (!this.state.dataUrl) {
            this.state.loading = false;
            this.state.ready = true;
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc(this.state.dataUrl, {});
            if (!result.success) {
                throw new Error(result.message || "Data pembayaran belum bisa dimuat.");
            }
            this.state.seller = result.seller || this.state.seller;
            this.state.stats = result.stats || this.state.stats;
            this.state.product = result.product || this.state.product;
            this.state.fees = result.fees || this.state.fees;
            this.state.methods = result.methods || this.state.methods;
            this.state.submitUrl = result.submit_url || this.state.submitUrl;
            this.state.existingIntent = result.existing_intent || {};
        } catch (error) {
            console.error("[UniTrade] Seller product payment:", error);
            this.state.error = error.message || "Data pembayaran belum bisa dimuat.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }

    toggleMethod(method) {
        this.state.expandedMethod = this.state.expandedMethod === method.key ? "" : method.key;
        this.state.error = "";
        this.state.success = "";
        this.state.paymentResult = null;
    }

    selectChannel(method, channel) {
        if (method.insufficient) {
            this.state.error = "Saldo akun belum mencukupi untuk metode ini.";
            return;
        }
        this.state.expandedMethod = method.key;
        this.state.selectedChannel = channel.key;
        this.state.error = "";
        this.state.success = "";
        this.state.paymentResult = null;
    }

    toggleTerms(ev) {
        this.state.acceptedTerms = Boolean(ev.target.checked);
        this.state.error = "";
    }

    async submitPayment() {
        if (!this.canPay) {
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        this.state.success = "";
        try {
            const result = await jsonrpc(this.state.submitUrl, {
                payment_method: this.state.selectedChannel,
                accepted_terms: this.state.acceptedTerms,
            });
            if (!result.success) {
                throw new Error(result.message || "Pembayaran belum bisa dibuat.");
            }
            this.state.paymentResult = result;
            this.state.success = result.message || "Transaksi pembayaran berhasil dibuat.";
        } catch (error) {
            console.error("[UniTrade] Seller listing payment:", error);
            this.state.error = error.message || "Pembayaran belum bisa dibuat.";
        } finally {
            this.state.submitting = false;
        }
    }
}

publicWidget.registry.UnitradeSellerProductCreate = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-product-create-mount, #wrap.ut-seller-product-edit-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.productCreatePayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller product create payload:", error);
        }
        const payload = datasetPayload(this.el.dataset, parsed);
        this.el.innerHTML = "";
        this.component = await mount(SellerProductCreate, this.el, {
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

publicWidget.registry.UnitradeSellerProductPayment = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-product-payment-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.productPaymentPayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller product payment payload:", error);
        }
        const payload = paymentPayload(this.el.dataset, parsed);
        this.el.innerHTML = "";
        this.component = await mount(SellerProductPayment, this.el, {
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
