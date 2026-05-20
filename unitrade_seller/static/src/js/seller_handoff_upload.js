/** @odoo-module **/

const HANDOFF_ALLOWED_TYPES = new Set(["image/png", "image/jpg", "image/jpeg", "image/webp"]);
const HANDOFF_MAX_FILE_SIZE = 5 * 1024 * 1024;

export function formatHandoffFileSize(size) {
    const bytes = Number(size || 0);
    if (bytes >= 1024 * 1024) {
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function validateHandoffImageFile(file) {
    if (!file) {
        return "Pilih gambar bukti penyerahan terlebih dahulu.";
    }
    if (!HANDOFF_ALLOWED_TYPES.has(file.type)) {
        return "Format gambar harus JPG, PNG, atau WebP.";
    }
    if (file.size > HANDOFF_MAX_FILE_SIZE) {
        return "Ukuran gambar maksimal 5 MB.";
    }
    return "";
}
