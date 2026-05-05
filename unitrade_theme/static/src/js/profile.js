/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

const JOGJA_CENTER = [-7.7956, 110.3695];
const MAPBOX_GL_CSS_URL = "https://api.mapbox.com/mapbox-gl-js/v3.10.0/mapbox-gl.css";
const MAPBOX_GL_JS_URL = "https://api.mapbox.com/mapbox-gl-js/v3.10.0/mapbox-gl.js";
let mapboxLoadPromise = null;
let mapboxConfigPromise = null;

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

publicWidget.registry.UnitradeUserProfileForm = publicWidget.Widget.extend({
    selector: ".ut-user-profile-form",
    events: {
        "change [data-profile-avatar-input]": "_onAvatarChange",
        "click .ut-user-profile-avatar-picker": "_onAvatarPickerClick",
        "click [data-profile-edit]": "_onEdit",
    },

    start() {
        this._setEditing(this.el.dataset.editing === "1");
        return this._super(...arguments);
    },

    _onEdit() {
        this._setEditing(true);
        const firstInput = this.el.querySelector("input[name='name']");
        if (firstInput) {
            firstInput.focus();
            firstInput.select();
        }
    },

    _onAvatarChange(ev) {
        const file = ev.currentTarget.files && ev.currentTarget.files[0];
        const preview = this.el.querySelector(".ut-user-profile-avatar-img");
        const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
        if (!file || !preview) {
            return;
        }
        if (!allowedTypes.includes(file.type) || file.size > 2 * 1024 * 1024) {
            ev.currentTarget.value = "";
            window.alert("Foto profil harus JPG, PNG, atau WEBP dan maksimal 2 MB.");
            return;
        }
        const reader = new FileReader();
        reader.addEventListener("load", () => {
            preview.src = reader.result;
        });
        reader.readAsDataURL(file);
    },

    _onAvatarPickerClick(ev) {
        const input = this.el.querySelector("[data-profile-avatar-input]");
        if (!this.el.classList.contains("is-editing")) {
            ev.preventDefault();
            return;
        }
        if (ev.target === input || !input || input.disabled) {
            return;
        }
        ev.preventDefault();
        input.click();
    },

    _setEditing(isEditing) {
        this.el.dataset.editing = isEditing ? "1" : "0";
        this.el.classList.toggle("is-editing", isEditing);
        this.el.classList.toggle("is-readonly", !isEditing);

        this.el.querySelectorAll("[data-profile-control]").forEach((control) => {
            control.disabled = !isEditing;
        });
    },
});

publicWidget.registry.UnitradeAddressModal = publicWidget.Widget.extend({
    selector: ".ut-user-profile-card",
    events: {
        "click [data-address-open]": "_onOpen",
        "click [data-address-close]": "_onClose",
        "click [data-address-label]": "_onSelectLabel",
        "click [data-address-save]": "_onSave",
        "click [data-address-use-current]": "_onUseCurrentLocation",
        "click [data-address-suggestion-index]": "_onSelectSuggestion",
        "input [data-address-search]": "_onSearchInput",
    },

    start() {
        this.modal = this.el.querySelector("[data-unitrade-address-modal]");
        this.addressState = this._readInitialState();
        this.selectedLabel = this.addressState.label || "home";
        this.suggestions = [];
        this.searchTimer = null;
        this.map = null;
        this.marker = null;
        this.mapboxConfig = null;

        if (this.modal) {
            this._fillFields(this.addressState);
            this._syncLabelButtons();
        }

        this._onKeydown = this._onKeydown.bind(this);
        document.addEventListener("keydown", this._onKeydown);
        return this._super(...arguments);
    },

    destroy() {
        document.removeEventListener("keydown", this._onKeydown);
        clearTimeout(this.searchTimer);
        if (this.map) {
            this.map.remove();
        }
        this._super(...arguments);
    },

    async _onOpen(ev) {
        ev.preventDefault();
        if (!this.modal) {
            return;
        }
        this.modal.classList.add("is-open");
        this.modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("ut-address-modal-open");
        this._clearError();
        this._fillFields(this.addressState);
        this._syncLabelButtons();

        try {
            const [mapboxgl, config] = await Promise.all([loadMapboxGL(), getMapboxConfig()]);
            this.mapboxConfig = config;
            mapboxgl.accessToken = config.access_token;
            this._initMap();
        } catch (error) {
            console.error("[UniTrade] Mapbox GL JS:", error);
            this._showError(error.message || "Peta tidak dapat dimuat. Periksa koneksi lalu coba lagi.");
        }

        const searchInput = this.modal.querySelector("[data-address-search]");
        if (searchInput) {
            searchInput.focus();
        }
    },

    _onClose(ev) {
        if (ev) {
            ev.preventDefault();
        }
        if (!this.modal) {
            return;
        }
        this.modal.classList.remove("is-open");
        this.modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("ut-address-modal-open");
        this._clearSuggestions();
    },

    _onKeydown(ev) {
        if (ev.key === "Escape" && this.modal && this.modal.classList.contains("is-open")) {
            this._onClose(ev);
        }
    },

    _onSelectLabel(ev) {
        ev.preventDefault();
        this.selectedLabel = ev.currentTarget.dataset.addressLabel || "home";
        this._syncLabelButtons();
    },

    _onSearchInput(ev) {
        const query = ev.currentTarget.value.trim();
        clearTimeout(this.searchTimer);
        if (query.length < 3) {
            this._clearSuggestions();
            return;
        }
        this.searchTimer = setTimeout(() => this._searchAddress(query), 260);
    },

    async _searchAddress(query) {
        const list = this.modal.querySelector("[data-address-suggestions]");
        if (list) {
            list.innerHTML = '<div class="ut-address-suggestion-muted">Mencari alamat...</div>';
        }

        try {
            const result = await jsonrpc("/unitrade/mapbox/geocode", { query });
            if (!result || !result.success) {
                throw new Error((result && result.message) || "Search failed");
            }
            this.suggestions = result.features || [];
            this._renderSuggestions();
        } catch (error) {
            console.error("[UniTrade] Address search:", error);
            this.suggestions = [];
            if (list) {
                list.innerHTML = '<div class="ut-address-suggestion-muted">Pencarian alamat belum tersedia.</div>';
            }
        }
    },

    _renderSuggestions() {
        const list = this.modal.querySelector("[data-address-suggestions]");
        if (!list) {
            return;
        }
        if (!this.suggestions.length) {
            list.innerHTML = '<div class="ut-address-suggestion-muted">Alamat tidak ditemukan.</div>';
            return;
        }
        list.innerHTML = "";
        this.suggestions.forEach((feature, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "ut-address-suggestion";
            button.dataset.addressSuggestionIndex = String(index);
            button.textContent = feature.label || "Alamat";
            list.appendChild(button);
        });
    },

    _onSelectSuggestion(ev) {
        ev.preventDefault();
        const index = Number(ev.currentTarget.dataset.addressSuggestionIndex);
        const feature = this.suggestions[index];
        if (!feature) {
            return;
        }
        this.addressState = {
            ...this.addressState,
            ...feature,
            place_id: feature.id || "",
            street: feature.street || this._firstAddressLine(feature.label),
        };
        this._fillFields(this.addressState);
        this._setMapLocation(this.addressState.latitude, this.addressState.longitude, 16);
        this._clearSuggestions();
    },

    async _onUseCurrentLocation(ev) {
        ev.preventDefault();
        if (!navigator.geolocation) {
            this._showError("Browser tidak mendukung akses lokasi.");
            return;
        }

        const button = ev.currentTarget;
        button.disabled = true;
        button.classList.add("is-loading");
        this._clearError();

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const latitude = position.coords.latitude;
                const longitude = position.coords.longitude;
                this._setCoordinates(latitude, longitude);
                this._setMapLocation(latitude, longitude, 16);
                try {
                    const result = await jsonrpc("/unitrade/mapbox/geocode", { latitude, longitude });
                    const feature = result && result.success && result.features && result.features[0];
                    if (feature) {
                        this.addressState = {
                            ...this.addressState,
                            ...feature,
                            place_id: feature.id || "",
                            street: feature.street || this.addressState.street || this._firstAddressLine(feature.label),
                        };
                        this._fillFields(this.addressState);
                    }
                } catch (error) {
                    console.error("[UniTrade] Reverse geocode:", error);
                } finally {
                    button.disabled = false;
                    button.classList.remove("is-loading");
                }
            },
            () => {
                button.disabled = false;
                button.classList.remove("is-loading");
                this._showError("Lokasi saat ini tidak dapat diakses.");
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    },

    async _onSave(ev) {
        ev.preventDefault();
        const payload = this._collectPayload();
        const errors = this._validatePayload(payload);
        if (errors.length) {
            this._showError(errors[0]);
            return;
        }

        const button = ev.currentTarget;
        button.disabled = true;
        button.classList.add("is-loading");
        this._clearError();

        try {
            const result = await jsonrpc("/my/account/address", payload);
            if (!result || !result.success) {
                this._showServerErrors(result || {});
                return;
            }
            this.addressState = result.address || payload;
            this.selectedLabel = this.addressState.label || this.selectedLabel;
            this._updateSummary(result.summary || {});
            this._onClose();
        } catch (error) {
            console.error("[UniTrade] Address save:", error);
            this._showError(error.message || "Alamat gagal disimpan.");
        } finally {
            button.disabled = false;
            button.classList.remove("is-loading");
        }
    },

    _readInitialState() {
        if (!this.modal) {
            return {};
        }
        try {
            return JSON.parse(this.modal.dataset.addressInitial || "{}");
        } catch (error) {
            console.error("[UniTrade] Address initial state:", error);
            return {};
        }
    },

    _fillFields(values) {
        if (!this.modal) {
            return;
        }
        const fields = ["province", "city", "district", "village", "zip", "street", "street2", "latitude", "longitude"];
        fields.forEach((field) => {
            const input = this.modal.querySelector(`[data-address-field="${field}"]`);
            if (!input) {
                return;
            }
            if (field === "latitude" || field === "longitude") {
                input.value = this._formatCoordinate(values[field], field);
            } else {
                input.value = values[field] || "";
            }
        });
        this.selectedLabel = values.label || this.selectedLabel || "home";
    },

    _collectPayload() {
        const payload = {
            label: this.selectedLabel || "home",
            place_id: this.addressState.place_id || "",
        };
        this.modal.querySelectorAll("[data-address-field]").forEach((input) => {
            payload[input.dataset.addressField] = input.value.trim();
        });
        return payload;
    },

    _validatePayload(payload) {
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

        this.modal.querySelectorAll(".is-invalid").forEach((node) => node.classList.remove("is-invalid"));
        for (const [field, message] of Object.entries(required)) {
            if (!payload[field]) {
                this._markInvalid(field);
                return [message];
            }
        }
        if (!/^[0-9]{4,10}$/.test(payload.zip)) {
            this._markInvalid("zip");
            return ["Kode pos harus berupa angka 4 sampai 10 digit."];
        }
        if (Number.isNaN(Number(payload.latitude)) || Number.isNaN(Number(payload.longitude))) {
            this._markInvalid("latitude");
            this._markInvalid("longitude");
            return ["Koordinat alamat belum valid."];
        }
        return [];
    },

    _markInvalid(field) {
        const input = this.modal.querySelector(`[data-address-field="${field}"]`);
        if (input) {
            input.classList.add("is-invalid");
            input.focus();
        }
    },

    _showServerErrors(result) {
        this.modal.querySelectorAll(".is-invalid").forEach((node) => node.classList.remove("is-invalid"));
        const errors = result.errors || {};
        Object.keys(errors).forEach((field) => {
            if (field === "coordinates") {
                this._markInvalid("latitude");
                this._markInvalid("longitude");
            } else {
                this._markInvalid(field);
            }
        });

        const messages = result.error_messages || [];
        if (messages.length) {
            this._showError(messages.join(" "));
            return;
        }
        this._showError(result.message || "Alamat gagal disimpan.");
    },

    _syncLabelButtons() {
        if (!this.modal) {
            return;
        }
        this.modal.querySelectorAll("[data-address-label]").forEach((button) => {
            const active = button.dataset.addressLabel === this.selectedLabel;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-checked", active ? "true" : "false");
        });
    },

    _initMap() {
        if (!window.mapboxgl || !this.modal || !this.mapboxConfig) {
            return;
        }
        const mapEl = this.modal.querySelector("[data-address-map]");
        if (!mapEl) {
            return;
        }

        const latitude = Number(this.modal.querySelector('[data-address-field="latitude"]').value) || JOGJA_CENTER[0];
        const longitude = Number(this.modal.querySelector('[data-address-field="longitude"]').value) || JOGJA_CENTER[1];
        if (!this.map) {
            this.map = new window.mapboxgl.Map({
                container: mapEl,
                style: this.mapboxConfig.style,
                center: [longitude, latitude],
                zoom: 15,
                pitch: 38,
                bearing: -8,
                attributionControl: true,
            });
            this.map.addControl(new window.mapboxgl.NavigationControl({ showCompass: true }), "top-left");
            this.marker = new window.mapboxgl.Marker({
                color: "#1d1d1d",
                draggable: true,
            }).setLngLat([longitude, latitude]).addTo(this.map);
            this.marker.on("dragend", () => {
                const point = this.marker.getLngLat();
                this._setCoordinates(point.lat, point.lng);
            });
        } else {
            this._setMapLocation(latitude, longitude, 15);
        }
        window.setTimeout(() => this.map.resize(), 80);
    },

    _setMapLocation(latitude, longitude, zoom) {
        const lat = Number(latitude);
        const lng = Number(longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            return;
        }
        this._setCoordinates(lat, lng);
        if (this.map) {
            this.map.flyTo({
                center: [lng, lat],
                zoom: zoom || this.map.getZoom(),
                essential: true,
            });
        }
        if (this.marker) {
            this.marker.setLngLat([lng, lat]);
        }
    },

    _setCoordinates(latitude, longitude) {
        this.addressState.latitude = latitude;
        this.addressState.longitude = longitude;
        const latInput = this.modal.querySelector('[data-address-field="latitude"]');
        const lngInput = this.modal.querySelector('[data-address-field="longitude"]');
        if (latInput) {
            latInput.value = this._formatCoordinate(latitude, "latitude");
        }
        if (lngInput) {
            lngInput.value = this._formatCoordinate(longitude, "longitude");
        }
    },

    _formatCoordinate(value, field) {
        const fallback = field === "latitude" ? JOGJA_CENTER[0] : JOGJA_CENTER[1];
        const number = Number(value || fallback);
        return Number.isFinite(number) ? number.toFixed(6) : "";
    },

    _firstAddressLine(label) {
        return (label || "").split(",")[0].trim();
    },

    _clearSuggestions() {
        const list = this.modal && this.modal.querySelector("[data-address-suggestions]");
        if (list) {
            list.innerHTML = "";
        }
    },

    _showError(message) {
        const error = this.modal && this.modal.querySelector("[data-address-error]");
        if (error) {
            error.textContent = message;
            error.classList.add("is-visible");
        }
    },

    _clearError() {
        const error = this.modal && this.modal.querySelector("[data-address-error]");
        if (error) {
            error.textContent = "";
            error.classList.remove("is-visible");
        }
    },

    _updateSummary(summary) {
        const label = this.el.querySelector("[data-address-summary-label]");
        const line = this.el.querySelector("[data-address-summary-line]");
        const coordinates = this.el.querySelector("[data-address-summary-coordinates]");
        const preview = this.el.querySelector(".ut-user-profile-address-preview");

        if (label) {
            label.textContent = summary.label || this._labelText(this.selectedLabel);
        }
        if (line) {
            line.textContent = summary.line || "Belum ada alamat tersimpan.";
        }
        if (coordinates) {
            coordinates.textContent = summary.coordinates || "";
            coordinates.hidden = !summary.coordinates;
        }
        if (preview) {
            preview.classList.toggle("is-empty", !summary.line);
        }
    },

    _labelText(label) {
        return {
            home: "Rumah",
            office: "Kantor",
            school: "Sekolah",
            other: "Lainnya",
        }[label || "home"] || "Rumah";
    },
});

publicWidget.registry.UnitradeSettingsNotifications = publicWidget.Widget.extend({
    selector: "[data-settings-notifications]",
    events: {
        "change [data-notification-field]": "_onToggle",
    },

    async _onToggle(ev) {
        const input = ev.currentTarget;
        const field = input.dataset.notificationField;
        const value = input.checked;
        const switchControl = input.closest(".ut-settings-switch");

        if (switchControl) {
            switchControl.classList.add("is-saving");
        }

        try {
            const result = await jsonrpc("/my/settings/notifications", {
                field: field,
                value: value,
            });

            if (!result || !result.success) {
                throw new Error((result && result.message) || "Notification update failed");
            }

            const values = result.values || {};
            this.el.querySelectorAll("[data-notification-field]").forEach((control) => {
                if (Object.prototype.hasOwnProperty.call(values, control.dataset.notificationField)) {
                    control.checked = Boolean(values[control.dataset.notificationField]);
                }
            });
        } catch (error) {
            input.checked = !value;
            console.error("[UniTrade] Settings notification toggle:", error);
        } finally {
            if (switchControl) {
                switchControl.classList.remove("is-saving");
            }
        }
    },
});

publicWidget.registry.UnitradeWishlistPage = publicWidget.Widget.extend({
    selector: "[data-unitrade-wishlist-page]",
    events: {
        "click [data-wishlist-remove]": "_onRemoveWishlist",
    },

    async _onRemoveWishlist(ev) {
        ev.preventDefault();
        const button = ev.currentTarget;
        if (button.disabled) {
            return;
        }
        button.disabled = true;
        button.classList.add("is-loading");

        try {
            const result = await jsonrpc("/unitrade/wishlist/remove", {
                wishlist_id: button.dataset.wishlistId,
                product_id: button.dataset.productId,
            });

            if (!result || !result.success) {
                throw new Error((result && result.message) || "Wishlist update failed");
            }

            const productRow = button.closest("[data-wishlist-item]")
                || this.el.querySelector(`[data-wishlist-item][data-wishlist-id="${button.dataset.wishlistId}"]`);
            if (productRow) {
                const card = productRow.closest("[data-wishlist-seller-card]");
                productRow.remove();
                if (card) {
                    const nextHeartItem = card.querySelector("[data-wishlist-item]");
                    if (nextHeartItem) {
                        button.dataset.wishlistId = nextHeartItem.dataset.wishlistId;
                        button.dataset.productId = nextHeartItem.dataset.productId;
                        button.disabled = false;
                        button.classList.remove("is-loading");
                    } else {
                        card.remove();
                    }
                }
            }

            if (!this.el.querySelector("[data-wishlist-item]")) {
                const empty = this.el.querySelector("[data-wishlist-empty]");
                if (empty) {
                    empty.classList.remove("tw-hidden");
                }
            }
        } catch (error) {
            button.disabled = false;
            button.classList.remove("is-loading");
            console.error("[UniTrade] Wishlist page:", error);
        }
    },
});
