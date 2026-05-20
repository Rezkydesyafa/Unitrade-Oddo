/** @odoo-module **/

import { mount } from "@odoo/owl";

export async function mountSellerApp(widget, ComponentClass, props, templates, label) {
    const fallbackNodes = Array.from(widget.el.childNodes);
    const mountTarget = document.createElement("div");
    mountTarget.className = "ut-owl-mount-host";
    widget.el.appendChild(mountTarget);
    try {
        widget.component = await mount(ComponentClass, mountTarget, {
            props,
            templates,
        });
        fallbackNodes.forEach((node) => node.remove());
    } catch (error) {
        mountTarget.remove();
        console.error(`[UniTrade] ${label || "Seller app"} mount:`, error);
        widget.el.classList.add("ut-owl-mount-failed");
        if (!widget.el.querySelector(".ut-owl-fallback-error")) {
            const fallback = document.createElement("div");
            fallback.className = "ut-owl-fallback-error";
            fallback.textContent = "Halaman seller belum bisa dimuat. Refresh halaman setelah modul dan asset UniTrade di-upgrade.";
            widget.el.appendChild(fallback);
        }
    }
}
