/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Legacy blue primary (for backward compatibility)
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
        // New parchment color scheme for scholar atmosphere
        parchment: {
          25: '#FEFDFB',   // Ultra light cream
          50: '#FDFBF6',   // Lightest cream
          100: '#F5F0E8',  // Light parchment
          200: '#E8DDD1',  // Soft beige
          300: '#D8CFC3',  // Medium beige borders
          400: '#C4B5A6',  // Darker beige
          500: '#B89B72',  // Warm gold accent
          600: '#A08660',  // Deep gold
          700: '#8B7355',  // Bronze
          800: '#6B5B4A',  // Dark bronze
          900: '#4A3F35',  // Deep brown
        },
        // Muted text colors
        scholar: {
          50: '#F7F8F9',
          100: '#E8E9EA',
          200: '#D1D3D6',
          300: '#A0AEC0',  // Light gray-blue for info
          400: '#718096',
          500: '#4A5568',  // Deep blue-gray for accents
          600: '#2D3748',
          700: '#1A202C',
          800: '#171923',
          900: '#0F1114',  // Near black for main text
        },
        // Muted success colors
        sage: {
          50: '#F0F4F3',
          100: '#D9E6E2',
          200: '#B3CCC5',
          300: '#8CB3A8',
          400: '#6A8A82',  // Soft gray-green
          500: '#567169',
          600: '#465B54',
          700: '#37453F',
          800: '#293229',
          900: '#1C201D',
        }
      },
      fontFamily: {
        // Serif fonts for headings - classic, scholarly feel
        'serif': ['Playfair Display', 'Georgia', 'Cambria', 'Times New Roman', 'serif'],
        // Clean sans-serif for UI elements
        'sans': ['Inter', 'Lato', 'system-ui', 'sans-serif'],
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
