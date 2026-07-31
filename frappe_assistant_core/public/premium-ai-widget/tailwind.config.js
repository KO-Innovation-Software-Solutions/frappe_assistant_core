/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#4c1d95'
        }
      },
      boxShadow: {
        widget: '0 24px 80px rgba(88, 56, 255, 0.18)',
        glass: '0 12px 40px rgba(15, 23, 42, 0.08)',
        glow: '0 14px 34px rgba(124, 58, 237, 0.34)'
      },
      animation: {
        pulseSoft: 'pulseSoft 1.8s infinite',
        truckMove: 'truckMove 1.8s ease-in-out infinite',
        wheelSpin: 'wheelSpin .7s linear infinite',
        speedPulse: 'speedPulse .5s ease-in-out infinite',
        smokeFloat: 'smokeFloat 1.4s ease-out infinite',
        roadMove: 'roadMove .9s linear infinite',
        dotBounce: 'dotBounce 1.2s infinite',
        fadeUp: 'fadeUp .3s ease-out'
      },
      keyframes: {
        pulseSoft: {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '50%': { transform: 'scale(1.08)', opacity: '.75' }
        },
        truckMove: {
          '0%, 100%': { transform: 'translateX(0px)' },
          '50%': { transform: 'translateX(10px)' }
        },
        wheelSpin: {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' }
        },
        speedPulse: {
          '0%, 100%': { opacity: '.3', transform: 'translateX(0px)' },
          '50%': { opacity: '1', transform: 'translateX(-2px)' }
        },
        smokeFloat: {
          '0%': { opacity: '0', transform: 'translate(0, 4px) scale(.8)' },
          '40%': { opacity: '.8' },
          '100%': { opacity: '0', transform: 'translate(-10px, -10px) scale(1.5)' }
        },
        roadMove: {
          from: { backgroundPosition: '0 0' },
          to: { backgroundPosition: '28px 0' }
        },
        dotBounce: {
          '0%, 80%, 100%': { transform: 'translateY(0)', opacity: '.35' },
          '40%': { transform: 'translateY(-4px)', opacity: '1' }
        },
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' }
        }
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
}