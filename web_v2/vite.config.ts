import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/static/web-v2/',
  build: {
    outDir: '../static/web-v2',
    emptyOutDir: true,
  },
})
