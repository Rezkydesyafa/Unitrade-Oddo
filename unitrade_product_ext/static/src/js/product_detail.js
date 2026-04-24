/** @odoo-module **/

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    /* ============================================================
       TABS
       ============================================================ */
    const tabBtns = document.querySelectorAll('.ut-tab-btn');
    const tabContents = document.querySelectorAll('.ut-tab-content');

    tabBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabName = this.getAttribute('data-tab');

            // Deactivate all
            tabBtns.forEach(function (b) { b.classList.remove('active'); });
            tabContents.forEach(function (c) { c.classList.remove('active'); });

            // Activate clicked
            this.classList.add('active');
            var targetTab = document.getElementById('tab-' + tabName);
            if (targetTab) {
                targetTab.classList.add('active');
            }
        });
    });

    /* ============================================================
       GALLERY THUMBNAILS
       ============================================================ */
    var thumbs = document.querySelectorAll('.ut-thumb');
    var mainImage = document.getElementById('ut-main-image');

    thumbs.forEach(function (thumb) {
        thumb.addEventListener('click', function () {
            var src = this.getAttribute('data-src');
            if (mainImage && src) {
                // Smooth fade transition
                mainImage.style.opacity = '0';
                setTimeout(function () {
                    mainImage.src = src;
                    mainImage.style.opacity = '1';
                }, 200);
            }
            // Update active class
            thumbs.forEach(function (t) { t.classList.remove('active'); });
            this.classList.add('active');
        });
    });

    // Smooth opacity transition for main image
    if (mainImage) {
        mainImage.style.transition = 'opacity 0.25s ease';
    }

    /* ============================================================
       QUANTITY SELECTOR
       ============================================================ */
    var qtyValue = document.getElementById('ut-qty-value');
    var qtyMinus = document.getElementById('ut-qty-minus');
    var qtyPlus = document.getElementById('ut-qty-plus');
    var addCartBtn = document.getElementById('ut-add-cart-btn');

    if (qtyValue && qtyMinus && qtyPlus) {
        var currentQty = parseInt(qtyValue.value) || 1;

        qtyMinus.addEventListener('click', function () {
            if (currentQty > 1) {
                currentQty--;
                qtyValue.value = currentQty;
            }
        });

        qtyPlus.addEventListener('click', function () {
            currentQty++;
            qtyValue.value = currentQty;
        });
    }

    /* ============================================================
       RELATED PRODUCTS CAROUSEL — Drag scroll
       ============================================================ */
    var carousel = document.getElementById('ut-related-carousel');
    if (carousel) {
        var isDown = false;
        var startX;
        var scrollLeft;

        carousel.addEventListener('mousedown', function (e) {
            isDown = true;
            carousel.style.cursor = 'grabbing';
            startX = e.pageX - carousel.offsetLeft;
            scrollLeft = carousel.scrollLeft;
        });

        carousel.addEventListener('mouseleave', function () {
            isDown = false;
            carousel.style.cursor = 'grab';
        });

        carousel.addEventListener('mouseup', function () {
            isDown = false;
            carousel.style.cursor = 'grab';
        });

        carousel.addEventListener('mousemove', function (e) {
            if (!isDown) return;
            e.preventDefault();
            var x = e.pageX - carousel.offsetLeft;
            var walk = (x - startX) * 1.5;
            carousel.scrollLeft = scrollLeft - walk;
        });

        // Set initial cursor
        carousel.style.cursor = 'grab';
    }
});
