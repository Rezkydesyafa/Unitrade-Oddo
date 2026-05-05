/** @type {import('tailwindcss').Config} */
module.exports = {
  prefix: 'tw-',
  corePlugins: {
    preflight: false, // Avoid conflict with Odoo Bootstrap
  },
  content: [
    './unitrade_*/views/*.xml',
    './unitrade_*/static/src/**/*.{js,xml}',
  ],
  theme: {
    extend: {
      colors: {
        'primary': 'var(--ut-color-primary)',
        'secondary': 'var(--ut-color-secondary)',
        'accent': 'var(--ut-color-accent)',
        'text-main': 'var(--ut-color-text-main)',
        'text-muted': 'var(--ut-color-text-muted)',
        'bg-main': 'var(--ut-color-bg-main)',
        'bg-surface': 'var(--ut-color-bg-surface)',
        'border': 'var(--ut-color-border)',
        'heading': 'var(--ut-color-heading)',
        'button': 'var(--ut-color-button-bg)',
        'button-text': 'var(--ut-color-button-text)',
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
