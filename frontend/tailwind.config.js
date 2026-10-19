/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#d56116',
          dark: '#b34e11',
          light: '#f0792e',
        },
      },
    },
  },
  plugins: [],
};
