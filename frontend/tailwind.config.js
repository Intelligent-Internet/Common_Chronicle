/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'mist': '#d5dce0',
        'sky-blue': '#bae9f4',
        'violet': '#632af5',
        'pewter': '#919eae',
        'slate': '#56696d',
        'charcoal': '#191e1b',
        'white': '#ffffff',
        'black': '#000000',
      },
      fontFamily: {
        // Headers 1-3: Nunito Sans
        'sans': ['Nunito Sans', 'system-ui', 'sans-serif'],
        // Headers 4-5 & Body: Montserrat
        'alt': ['Montserrat', 'system-ui', 'sans-serif'],
        // Monospace for code (keep existing)
        'mono': ['ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      spacing: {
        '18': '4.5rem',
        '72': '18rem',
        '84': '21rem',
        '96': '24rem',
      },
      lineHeight: {
        'relaxed-plus': '1.75',
        'loose-plus': '2.25',
      },
      fill: theme => ({
        ...theme('colors')
      }),
      stroke: theme => ({
        ...theme('colors')
      }),
    },
  },
  plugins: [],
}
