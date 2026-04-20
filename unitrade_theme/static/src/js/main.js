/** @odoo-module **/

/**
 * UniTrade Marketplace — Frontend JavaScript
 * Handles UI interactions, animations, and dynamic features.
 */

document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    // =============================================
    // Intersection Observer for scroll animations
    // =============================================
    const animatedElements = document.querySelectorAll('[data-unitrade-animate]');
    if (animatedElements.length > 0) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('unitrade-animate-in');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });

        animatedElements.forEach((el) => observer.observe(el));
    }

    // =============================================
    // Wishlist toggle (heart icon)
    // =============================================
    document.querySelectorAll('.unitrade-wishlist-btn').forEach((btn) => {
        btn.addEventListener('click', async function (e) {
            e.preventDefault();
            e.stopPropagation();

            const productId = this.dataset.productId;
            const icon = this.querySelector('svg, i');

            try {
                const response = await fetch('/unitrade/wishlist/toggle', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ product_id: parseInt(productId) }),
                });
                const result = await response.json();

                if (result.added) {
                    this.classList.add('tw-text-red-500');
                    this.classList.remove('tw-text-gray-400');
                } else {
                    this.classList.remove('tw-text-red-500');
                    this.classList.add('tw-text-gray-400');
                }
            } catch (error) {
                console.error('Wishlist toggle error:', error);
            }
        });
    });

    // =============================================
    // Search bar — live search suggestions
    // =============================================
    const searchInput = document.querySelector('.unitrade-search');
    let searchTimeout = null;

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const query = this.value.trim();
                if (query.length >= 2) {
                    // Future: fetch search suggestions
                    console.log('Searching for:', query);
                }
            }, 300);
        });
    }

    // =============================================
    // Mobile menu toggle
    // =============================================
    const mobileMenuBtn = document.querySelector('#unitrade-mobile-menu-btn');
    const mobileMenu = document.querySelector('#unitrade-mobile-menu');

    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', function () {
            mobileMenu.classList.toggle('tw-hidden');
            mobileMenu.classList.toggle('unitrade-slide-in');
        });
    }

    // =============================================
    // Product image slider
    // =============================================
    const imageSliders = document.querySelectorAll('.unitrade-image-slider');
    imageSliders.forEach((slider) => {
        const images = slider.querySelectorAll('img');
        const dots = slider.querySelectorAll('.unitrade-slider-dot');
        let currentIndex = 0;

        function showImage(index) {
            images.forEach((img, i) => {
                img.style.display = i === index ? 'block' : 'none';
            });
            dots.forEach((dot, i) => {
                dot.classList.toggle('tw-bg-indigo-600', i === index);
                dot.classList.toggle('tw-bg-gray-300', i !== index);
            });
        }

        dots.forEach((dot, i) => {
            dot.addEventListener('click', () => {
                currentIndex = i;
                showImage(currentIndex);
            });
        });

        if (images.length > 0) {
            showImage(0);
        }
    });
});
