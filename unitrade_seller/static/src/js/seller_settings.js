/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { Component, mount, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { templates } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { readSellerSidebarOpen, sellerSidebarItems, writeSellerSidebarOpen } from "./seller_sidebar";

const JOGJA_CENTER = [-7.7956, 110.3695];
const MAPBOX_GL_CSS_URL = "https://api.mapbox.com/mapbox-gl-js/v3.10.0/mapbox-gl.css";
const MAPBOX_GL_JS_URL = "https://api.mapbox.com/mapbox-gl-js/v3.10.0/mapbox-gl.js";
const STORE_DESCRIPTION_MAX_LENGTH = 1000;
let mapboxLoadPromise = null;
let mapboxConfigPromise = null;

function toNumber(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
}

function loadMapboxGL() {
    if (window.mapboxgl) {
        return Promise.resolve(window.mapboxgl);
    }
    if (mapboxLoadPromise) {
        return mapboxLoadPromise;
    }

    mapboxLoadPromise = new Promise((resolve, reject) => {
        if (!document.querySelector(`link[href="${MAPBOX_GL_CSS_URL}"]`)) {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = MAPBOX_GL_CSS_URL;
            document.head.appendChild(link);
        }

        const script = document.createElement("script");
        script.src = MAPBOX_GL_JS_URL;
        script.onload = () => resolve(window.mapboxgl);
        script.onerror = () => reject(new Error("Mapbox GL JS failed to load"));
        document.head.appendChild(script);
    });

    return mapboxLoadPromise;
}

function getMapboxConfig() {
    if (!mapboxConfigPromise) {
        mapboxConfigPromise = jsonrpc("/unitrade/mapbox/config", {}).then((result) => {
            if (!result || !result.success) {
                throw new Error((result && result.message) || "Mapbox config unavailable");
            }
            return result;
        });
    }
    return mapboxConfigPromise;
}

function formatCoordinate(value, field) {
    const fallback = field === "latitude" ? JOGJA_CENTER[0] : JOGJA_CENTER[1];
    const number = Number(value || fallback);
    return Number.isFinite(number) ? number.toFixed(6) : "";
}

function emptyAddressForm(summary = {}) {
    return {
        label: summary.label_key || "home",
        place_id: summary.place_id || "",
        province: summary.province || "",
        city: summary.city || "",
        district: summary.district || "",
        village: summary.village || "",
        zip: summary.zip || "",
        street: summary.street || "",
        street2: summary.street2 || "",
        latitude: formatCoordinate(summary.latitude, "latitude"),
        longitude: formatCoordinate(summary.longitude, "longitude"),
    };
}

function payloadFromDataset(dataset, parsed) {
    if (parsed && parsed.settings) {
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
        settings: {},
        bank_options: [],
        data_url: "/unitrade/seller/settings/data",
        update_url: "/unitrade/seller/settings/update",
        close_url: "/unitrade/seller/settings/close-store",
        delete_request_url: "/unitrade/seller/settings/request-delete",
        profile_address_url: "/my/account",
    };
}

export class SellerSettings extends Component {
    static template = "unitrade_seller.SellerSettings";
    static props = {
        payload: Object,
    };

    setup() {
        const payload = this.props.payload || {};
        this.addressSearchTimer = null;
        this.addressMap = null;
        this.addressMarker = null;
        this.mapboxConfig = null;
        this.onAddressKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.addressModalOpen) {
                this.closeAddressModal(ev);
            }
        };
        this.state = useState({
            ready: false,
            loading: true,
            savingSection: "",
            closing: false,
            requestingDelete: false,
            error: "",
            success: "",
            sidebarOpen: readSellerSidebarOpen(),
            seller: payload.seller || {},
            stats: payload.stats || {},
            bankOptions: payload.bank_options || [],
            dataUrl: payload.data_url || "/unitrade/seller/settings/data",
            updateUrl: payload.update_url || "/unitrade/seller/settings/update",
            closeUrl: payload.close_url || "/unitrade/seller/settings/close-store",
            deleteRequestUrl: payload.delete_request_url || "/unitrade/seller/settings/request-delete",
            profileAddressUrl: payload.profile_address_url || "/my/account",
            form: this.formFromSettings(payload.settings || {}),
            addressModalOpen: false,
            addressForm: this.addressFormFromSettings(payload.settings || {}),
            addressSuggestions: [],
            addressSearch: "",
            addressSaving: false,
            addressError: "",
        });

        onMounted(() => {
            document.addEventListener("keydown", this.onAddressKeydown);
            this.loadSettings();
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", this.onAddressKeydown);
            clearTimeout(this.addressSearchTimer);
            document.body.classList.remove("ut-address-modal-open");
            if (this.addressMap) {
                this.addressMap.remove();
            }
        });
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
        return "settings";
    }

    get sidebarClass() {
        return "ut-settings-sidebar";
    }

    get storeProfileUrl() {
        const slug = encodeURIComponent(this.state.form.slug || "");
        return slug ? `/seller-profile/${slug}` : (this.seller.profile_url || "/unitrade/seller/profile");
    }

    get descriptionCounter() {
        const length = String(this.state.form.description || "").length;
        return `${length}/${STORE_DESCRIPTION_MAX_LENGTH}`;
    }

    formFromSettings(settings) {
        return {
            storeUrlBase: settings.store_url_base || "unitrade.my.id/",
            slug: settings.slug || "",
            description: settings.description || "",
            phone: settings.phone || "",
            province: settings.province || "",
            city: settings.city || "",
            addressDetail: settings.address_detail || "",
            addressSummary: settings.address_summary || {},
            bankName: settings.bank_name || "",
            accountNumber: settings.account_number || "",
            accountName: settings.account_name || "",
            storeActive: settings.store_active !== false,
            chatEnabled: settings.chat_enabled !== false,
            deleteRequested: Boolean(settings.delete_requested),
        };
    }

    addressFormFromSettings(settings) {
        return emptyAddressForm(settings.address_summary || {});
    }

    applyPayload(payload) {
        this.state.seller = payload.seller || this.state.seller;
        this.state.stats = payload.stats || this.state.stats;
        this.state.bankOptions = payload.bank_options || this.state.bankOptions;
        this.state.form = this.formFromSettings(payload.settings || {});
        if (!this.state.addressModalOpen) {
            this.state.addressForm = this.addressFormFromSettings(payload.settings || {});
        }
    }

    sidebarItemClass(item) {
        const base = "ut-dash-sidebar-item";
        return item.active ? `${base} active` : base;
    }

    setField(field, ev) {
        let value = ev.target.value;
        if (field === "description" && value.length > STORE_DESCRIPTION_MAX_LENGTH) {
            value = value.slice(0, STORE_DESCRIPTION_MAX_LENGTH);
            ev.target.value = value;
        }
        this.state.form[field] = value;
        this.state.error = "";
        this.state.success = "";
    }

    setStoreActive(ev) {
        this.state.form.storeActive = Boolean(ev.target.checked);
        this.state.error = "";
        this.state.success = "";
    }

    setChatEnabled(ev) {
        this.state.form.chatEnabled = Boolean(ev.target.checked);
        this.state.error = "";
        this.state.success = "";
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

    async loadSettings() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await jsonrpc(this.state.dataUrl, {});
            if (!result.success) {
                throw new Error(result.message || "Pengaturan toko belum bisa dimuat.");
            }
            this.applyPayload(result);
        } catch (error) {
            console.error("[UniTrade] Seller settings:", error);
            this.state.error = error.message || "Pengaturan toko belum bisa dimuat.";
        } finally {
            this.state.loading = false;
            window.setTimeout(() => {
                this.state.ready = true;
            }, 160);
        }
    }

    payloadForSave() {
        const form = this.state.form;
        return {
            slug: form.slug,
            description: form.description,
            phone: form.phone,
            bank_name: form.bankName,
            account_number: form.accountNumber,
            account_name: form.accountName,
            store_active: form.storeActive,
            chat_enabled: form.chatEnabled,
        };
    }

    async saveSection(section) {
        if (this.state.savingSection) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        if (String(this.state.form.description || "").length > STORE_DESCRIPTION_MAX_LENGTH) {
            this.state.error = `Deskripsi / catatan toko maksimal ${STORE_DESCRIPTION_MAX_LENGTH} karakter.`;
            return;
        }
        this.state.savingSection = section;
        try {
            const result = await jsonrpc(this.state.updateUrl, this.payloadForSave());
            if (!result.success) {
                throw new Error(result.message || "Pengaturan toko belum bisa disimpan.");
            }
            this.applyPayload(result);
            this.state.success = result.message || "Pengaturan toko berhasil disimpan.";
        } catch (error) {
            console.error("[UniTrade] Seller settings save:", error);
            this.state.error = error.message || "Pengaturan toko belum bisa disimpan.";
        } finally {
            this.state.savingSection = "";
        }
    }

    addressLabelClass(label) {
        const base = "ut-address-label";
        return this.state.addressForm.label === label ? `${base} is-active` : base;
    }

    openAddressModal(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.state.addressForm = emptyAddressForm(this.state.form.addressSummary || {});
        this.state.addressModalOpen = true;
        this.state.addressError = "";
        this.state.addressSuggestions = [];
        this.state.addressSearch = "";
        document.body.classList.add("ut-address-modal-open");
        window.setTimeout(() => this.bootAddressMap(), 80);
    }

    closeAddressModal(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.state.addressModalOpen = false;
        this.state.addressError = "";
        this.state.addressSuggestions = [];
        document.body.classList.remove("ut-address-modal-open");
    }

    setAddressField(field, ev) {
        this.state.addressForm[field] = ev.target.value;
        this.state.addressError = "";
    }

    setAddressLabel(label) {
        this.state.addressForm.label = label || "home";
        this.state.addressError = "";
    }

    onAddressSearchInput(ev) {
        const query = ev.target.value.trim();
        this.state.addressSearch = query;
        clearTimeout(this.addressSearchTimer);
        if (query.length < 3) {
            this.state.addressSuggestions = [];
            return;
        }
        this.addressSearchTimer = window.setTimeout(() => this.searchAddress(query), 260);
    }

    async searchAddress(query) {
        this.state.addressSuggestions = [{ id: "loading", label: "Mencari alamat...", muted: true }];
        try {
            const result = await jsonrpc("/unitrade/mapbox/geocode", { query });
            if (!result || !result.success) {
                throw new Error((result && result.message) || "Pencarian alamat gagal.");
            }
            this.state.addressSuggestions = result.features && result.features.length
                ? result.features
                : [{ id: "empty", label: "Alamat tidak ditemukan.", muted: true }];
        } catch (error) {
            console.error("[UniTrade] Seller address search:", error);
            this.state.addressSuggestions = [{ id: "error", label: "Pencarian alamat belum tersedia.", muted: true }];
        }
    }

    selectAddressSuggestion(feature) {
        if (!feature || feature.muted) {
            return;
        }
        const form = this.state.addressForm;
        form.place_id = feature.id || "";
        form.province = feature.province || form.province || "";
        form.city = feature.city || form.city || "";
        form.district = feature.district || form.district || "";
        form.village = feature.village || form.village || "";
        form.zip = feature.zip || form.zip || "";
        form.street = feature.street || this.firstAddressLine(feature.label) || form.street || "";
        form.latitude = formatCoordinate(feature.latitude, "latitude");
        form.longitude = formatCoordinate(feature.longitude, "longitude");
        this.state.addressSearch = feature.label || "";
        this.state.addressSuggestions = [];
        this.setAddressMapLocation(form.latitude, form.longitude, 16);
    }

    async useCurrentAddressLocation(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!navigator.geolocation) {
            this.state.addressError = "Browser tidak mendukung akses lokasi.";
            return;
        }
        this.state.addressError = "";
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                this.setAddressCoordinates(latitude, longitude);
                this.setAddressMapLocation(latitude, longitude, 16);
                try {
                    const result = await jsonrpc("/unitrade/mapbox/geocode", { latitude, longitude });
                    const feature = result && result.success && result.features && result.features[0];
                    if (feature) {
                        this.selectAddressSuggestion(feature);
                    }
                } catch (error) {
                    console.error("[UniTrade] Seller reverse geocode:", error);
                }
            },
            () => {
                this.state.addressError = "Lokasi saat ini tidak dapat diakses.";
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    }

    validateAddressPayload(payload) {
        const required = {
            province: "Provinsi wajib diisi.",
            city: "Kota atau kabupaten wajib diisi.",
            district: "Kecamatan wajib diisi.",
            village: "Kelurahan wajib diisi.",
            zip: "Kode pos wajib diisi.",
            street: "Nama jalan atau nomor rumah wajib diisi.",
            latitude: "Pilih lokasi pada peta.",
            longitude: "Pilih lokasi pada peta.",
        };
        for (const [field, message] of Object.entries(required)) {
            if (!String(payload[field] || "").trim()) {
                return message;
            }
        }
        if (!/^[0-9]{4,10}$/.test(payload.zip)) {
            return "Kode pos harus berupa angka 4 sampai 10 digit.";
        }
        return "";
    }

    async saveAddress() {
        if (this.state.addressSaving) {
            return;
        }
        const payload = { ...this.state.addressForm };
        const validationError = this.validateAddressPayload(payload);
        if (validationError) {
            this.state.addressError = validationError;
            return;
        }
        this.state.addressSaving = true;
        this.state.addressError = "";
        try {
            const result = await jsonrpc("/my/account/address", payload);
            if (!result || !result.success) {
                const messages = (result && result.error_messages) || [];
                throw new Error(messages[0] || (result && result.message) || "Alamat gagal disimpan.");
            }
            const settingsResult = await jsonrpc(this.state.dataUrl, {});
            if (settingsResult && settingsResult.success) {
                this.applyPayload(settingsResult);
            }
            this.closeAddressModal();
            this.state.success = "Alamat toko berhasil diperbarui.";
        } catch (error) {
            console.error("[UniTrade] Seller address save:", error);
            this.state.addressError = error.message || "Alamat gagal disimpan.";
        } finally {
            this.state.addressSaving = false;
        }
    }

    async bootAddressMap() {
        if (!this.state.addressModalOpen) {
            return;
        }
        try {
            const [mapboxgl, config] = await Promise.all([loadMapboxGL(), getMapboxConfig()]);
            this.mapboxConfig = config;
            mapboxgl.accessToken = config.access_token;
            this.initAddressMap();
        } catch (error) {
            console.error("[UniTrade] Seller address map:", error);
            this.state.addressError = error.message || "Peta tidak dapat dimuat. Isi alamat secara manual lalu coba simpan.";
        }
    }

    initAddressMap() {
        const mapEl = document.querySelector(".ut-settings-address-modal [data-address-map]");
        if (!window.mapboxgl || !mapEl || !this.mapboxConfig) {
            return;
        }
        const latitude = Number(this.state.addressForm.latitude) || JOGJA_CENTER[0];
        const longitude = Number(this.state.addressForm.longitude) || JOGJA_CENTER[1];
        if (!this.addressMap) {
            this.addressMap = new window.mapboxgl.Map({
                container: mapEl,
                style: this.mapboxConfig.style,
                center: [longitude, latitude],
                zoom: 15,
                pitch: 38,
                bearing: -8,
                attributionControl: true,
            });
            this.addressMap.addControl(new window.mapboxgl.NavigationControl({ showCompass: true }), "top-left");
            this.addressMarker = new window.mapboxgl.Marker({
                color: "#1d1d1d",
                draggable: true,
            }).setLngLat([longitude, latitude]).addTo(this.addressMap);
            this.addressMarker.on("dragend", () => {
                const point = this.addressMarker.getLngLat();
                this.setAddressCoordinates(point.lat, point.lng);
            });
        } else {
            this.setAddressMapLocation(latitude, longitude, 15);
        }
        window.setTimeout(() => this.addressMap && this.addressMap.resize(), 80);
    }

    setAddressMapLocation(latitude, longitude, zoom) {
        const lat = Number(latitude);
        const lng = Number(longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            return;
        }
        this.setAddressCoordinates(lat, lng);
        if (this.addressMap) {
            this.addressMap.flyTo({
                center: [lng, lat],
                zoom: zoom || this.addressMap.getZoom(),
                essential: true,
            });
        }
        if (this.addressMarker) {
            this.addressMarker.setLngLat([lng, lat]);
        }
    }

    setAddressCoordinates(latitude, longitude) {
        this.state.addressForm.latitude = formatCoordinate(latitude, "latitude");
        this.state.addressForm.longitude = formatCoordinate(longitude, "longitude");
    }

    firstAddressLine(label) {
        return String(label || "").split(",")[0].trim();
    }

    async closeStore() {
        if (this.state.closing) {
            return;
        }
        if (!window.confirm("Tutup toko dan nonaktifkan seluruh produk?")) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.closing = true;
        try {
            const result = await jsonrpc(this.state.closeUrl, { confirm: "CLOSE_STORE" });
            if (!result.success) {
                throw new Error(result.message || "Toko belum bisa ditutup.");
            }
            this.state.form.storeActive = false;
            this.state.success = result.message || "Toko berhasil dinonaktifkan.";
        } catch (error) {
            console.error("[UniTrade] Seller settings close:", error);
            this.state.error = error.message || "Toko belum bisa ditutup.";
        } finally {
            this.state.closing = false;
        }
    }

    async requestDeleteSeller() {
        if (this.state.requestingDelete) {
            return;
        }
        if (!window.confirm("Ajukan penghapusan akun penjual untuk ditinjau admin? Data tidak akan dihapus permanen sekarang.")) {
            return;
        }
        this.state.error = "";
        this.state.success = "";
        this.state.requestingDelete = true;
        try {
            const result = await jsonrpc(this.state.deleteRequestUrl, { confirm: "REQUEST_SELLER_DELETE" });
            if (!result.success) {
                throw new Error(result.message || "Permintaan hapus akun belum bisa diproses.");
            }
            this.state.form.deleteRequested = true;
            this.state.success = result.message || "Permintaan hapus akun sudah dicatat.";
        } catch (error) {
            console.error("[UniTrade] Seller delete request:", error);
            this.state.error = error.message || "Permintaan hapus akun belum bisa diproses.";
        } finally {
            this.state.requestingDelete = false;
        }
    }
}

publicWidget.registry.UnitradeSellerSettings = publicWidget.Widget.extend({
    selector: "#wrap.ut-seller-settings-mount",

    async start() {
        const superPromise = this._super ? this._super.apply(this, arguments) : Promise.resolve();
        let parsed = {};
        try {
            parsed = JSON.parse(this.el.dataset.sellerSettingsPayload || "{}");
        } catch (error) {
            console.error("[UniTrade] Seller settings payload:", error);
        }
        const payload = payloadFromDataset(this.el.dataset, parsed);
        const fallbackNodes = Array.from(this.el.childNodes);
        const mountTarget = document.createElement("div");
        mountTarget.className = "ut-owl-mount-host";
        this.el.appendChild(mountTarget);
        try {
            this.component = await mount(SellerSettings, mountTarget, {
                props: { payload },
                templates,
            });
            fallbackNodes.forEach((node) => node.remove());
        } catch (error) {
            mountTarget.remove();
            console.error("[UniTrade] Seller settings mount:", error);
            this.el.classList.add("ut-owl-mount-failed");
            if (!this.el.querySelector(".ut-owl-fallback-error")) {
                const fallback = document.createElement("div");
                fallback.className = "ut-owl-fallback-error";
                fallback.textContent = "Pengaturan toko belum bisa dimuat. Muat ulang halaman setelah modul di-upgrade.";
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
