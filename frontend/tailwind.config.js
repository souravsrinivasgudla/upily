/** @type {import('tailwindcss').Config} */

// Newsprint design tokens — the single source of truth for colour, type and shape.
// Every radius is 0: the style is built from sharp rectangles only.
const zero = '0px'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    borderRadius: { none: zero, sm: zero, DEFAULT: zero, md: zero, lg: zero, xl: zero, '2xl': zero, full: zero },
    extend: {
      colors: {
        paper:   '#F9F9F7',   // background — newsprint off-white
        ink:     '#111111',   // text + borders
        divider: '#E5E5E0',   // muted rules and fills
        accent:  '#CC0000',   // editorial red — use sparingly
        focus:   '#F0F0F0',   // input focus fill
      },
      fontFamily: {
        serif: ['"Playfair Display"', '"Times New Roman"', 'serif'],
        body:  ['Lora', 'Georgia', 'serif'],
        sans:  ['Inter', '"Helvetica Neue"', 'sans-serif'],
        mono:  ['"JetBrains Mono"', '"Courier New"', 'monospace'],
      },
      boxShadow: {
        hard:    '4px 4px 0px 0px #111111',
        'hard-sm': '2px 2px 0px 0px #111111',
      },
      maxWidth: { page: '1280px' },
      keyframes: {
        ticker: { from: { transform: 'translateX(0)' }, to: { transform: 'translateX(-50%)' } },
      },
      animation: {
        ticker: 'ticker 60s linear infinite',
      },
    },
  },
  plugins: [],
}
