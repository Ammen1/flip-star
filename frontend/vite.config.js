import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    minify: 'terser',
    cssCodeSplit: true,
    cssMinify: true,
    reportCompressedSize: false,
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ['console.log', 'console.info', 'console.warn', 'console.debug'],
        passes: 2,
      },
      mangle: {
        safari10: true,
      },
      format: {
        comments: false,
      },
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Core React - loaded first, critical
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('node_modules/scheduler')) {
            return 'vendor-react';
          }
          // Icons - split separately since it's large
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
          // Other vendor deps
          if (id.includes('node_modules/')) {
            return 'vendor-misc';
          }
          // Profile pages
          if (
            id.includes('ProfilePage') ||
            id.includes('EditProfilePage') ||
            id.includes('FollowersListPage')
          ) {
            return 'chunk-profile';
          }
          // Campaigns
          if (
            id.includes('CampaignsPage') ||
            id.includes('CampaignDetailPage') ||
            id.includes('CampaignLeaderboard') ||
            id.includes('CampaignFeed') ||
            id.includes('CampaignStats')
          ) {
            return 'chunk-campaigns';
          }
          // Admin - large, split fully
          if (id.includes('AdminApp') || id.includes('/admin/')) {
            return 'chunk-admin';
          }
          // Auth screens
          if (id.includes('ModernLoginScreen') || id.includes('ModernRegisterScreen') || id.includes('LandingPage')) {
            return 'chunk-auth';
          }
          // Post/video detail
          if (id.includes('VideoDetailPage') || id.includes('EnhancedPostPage')) {
            return 'chunk-post';
          }
        },
        // Predictable chunk names for better caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    chunkSizeWarningLimit: 600,
    // Target modern browsers for smaller bundles
    target: 'es2020',
  },
  // Pre-bundle critical deps for faster dev & prod loads
  optimizeDeps: {
    include: ['react', 'react-dom', 'lucide-react'],
  },
  base: '/'
})
