/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg:      '#0f172a',
          surface: '#1e293b',
          border:  '#334155',
          muted:   '#475569',
          dim:     '#94a3b8',
          text:    '#f1f5f9',
          green:   '#22c55e',
          red:     '#ef4444',
          amber:   '#f59e0b',
          blue:    '#3b82f6',
        },
      },
      animation: {
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
