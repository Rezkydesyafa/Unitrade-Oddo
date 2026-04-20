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
        'primary': '#6366F1',
        'secondary': '#EC4899',
        'accent': '#F59E0B',
        'text-main': '#1F2937',
        'text-muted': '#6B7280',
        'bg-main': '#F9FAFB',
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
