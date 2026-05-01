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

    // =============================================
    // PDP: Thumbnail Gallery Switching
    // =============================================
    const mainImage = document.getElementById('ut-main-image');
    const thumbnails = document.querySelectorAll('.ut-thumb');
    
    if (mainImage && thumbnails.length > 0) {
        thumbnails.forEach(thumb => {
            thumb.addEventListener('click', function() {
                // Remove active class from all
                thumbnails.forEach(t => {
                    t.classList.remove('tw-border-gray-800');
                    t.classList.add('tw-border-gray-200');
                });
                
                // Add active class to clicked
                this.classList.remove('tw-border-gray-200');
                this.classList.add('tw-border-gray-800');
                
                // Update main image src
                const imgSrc = this.querySelector('img').getAttribute('src');
                mainImage.setAttribute('src', imgSrc);
            });
        });
    }

    // =============================================
    // PDP: Tabs Switching
    // =============================================
    const tabBtns = document.querySelectorAll('.ut-tab-btn');
    const tabContents = document.querySelectorAll('.ut-tab-content');
    
    if (tabBtns.length > 0 && tabContents.length > 0) {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const target = this.getAttribute('data-target');
                
                // Reset buttons
                tabBtns.forEach(b => {
                    b.classList.remove('tw-text-black', 'tw-border-b-2', 'tw-border-black', 'tw-font-bold');
                    b.classList.add('tw-text-gray-500', 'tw-font-medium');
                });
                
                // Activate clicked button
                this.classList.remove('tw-text-gray-500', 'tw-font-medium');
                this.classList.add('tw-text-black', 'tw-border-b-2', 'tw-border-black', 'tw-font-bold');
                
                // Hide all contents
                tabContents.forEach(content => {
                    content.classList.remove('tw-block');
                    content.classList.add('tw-hidden');
                });
                
                // Show target content
                const targetContent = document.getElementById('tab-' + target);
                if (targetContent) {
                    targetContent.classList.remove('tw-hidden');
                    targetContent.classList.add('tw-block');
                }
            });
        });
    }
});
