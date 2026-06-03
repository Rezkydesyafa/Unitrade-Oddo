/* UniTrade refund/dispute frontend script.
 * This file is intentionally small; the module manifest registers it in
 * web.assets_frontend, so it must exist even when no page-specific JS runs.
 */
(function () {
    "use strict";

    document.addEventListener("change", function (event) {
        var input = event.target;
        if (!input || !input.matches(".unitrade-refund-page input[type='file']")) {
            return;
        }

        var wrapper = input.closest(".unitrade-refund-file");
        var label = wrapper ? wrapper.querySelector(".unitrade-refund-file-name") : null;
        if (!label) {
            return;
        }

        var files = Array.prototype.slice.call(input.files || []);
        label.textContent = files.length ? files.map(function (file) { return file.name; }).join(", ") : "";
    });
})();
