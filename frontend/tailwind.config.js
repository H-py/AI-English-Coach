/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      // 极简中性色板：参考 Apple / Linear / Notion，避免花哨。
      // primary 取接近黑的深灰，强调克制留白与阅读优先。
      colors: {
        brand: {
          DEFAULT: '#1d1d1f',
          soft: '#3a3a3c',
          muted: '#86868b'
        }
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'system-ui',
          'sans-serif'
        ],
        serif: ['"Georgia"', '"Songti SC"', 'serif']
      },
      borderRadius: {
        xl: '0.75rem',
        '2xl': '1rem'
      },
      maxWidth: {
        prose: '68ch'
      }
    }
  },
  plugins: []
}
