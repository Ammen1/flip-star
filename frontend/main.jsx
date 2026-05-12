import ReactDOM from 'react-dom/client'
import WerqRoot from './App'
import { ThemeProvider } from './contexts/ThemeContext'
import { LanguageProvider } from './contexts/LanguageContext'

// When Vite deploys a new build, old chunk filenames (content-hashed) no longer exist.
// Browsers with cached HTML will try to import old chunk URLs → 404.
// Reload once to pick up the fresh HTML with new chunk references.
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault();
  const reloadKey = '__vite_reload__';
  if (!sessionStorage.getItem(reloadKey)) {
    sessionStorage.setItem(reloadKey, '1');
    window.location.reload();
  }
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <ThemeProvider>
    <LanguageProvider>
      <WerqRoot />
    </LanguageProvider>
  </ThemeProvider>,
);

// Skeleton removal is handled by components when content is ready.
// Fallback: remove after 2s max so it never stays forever (e.g. error paths).
setTimeout(() => {
  const skeleton = document.getElementById('app-skeleton');
  if (skeleton) {
    skeleton.style.transition = 'opacity 0.2s ease';
    skeleton.style.opacity = '0';
    setTimeout(() => skeleton.remove(), 220);
  }
}, 2000);




