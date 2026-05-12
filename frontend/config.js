// API Configuration for different environments
const getApiConfig = () => {
  const hostname = window.location.hostname;
  const isLocalhost = hostname.includes('localhost') || hostname.includes('127.0.0.1');

  if (isLocalhost) {
    // Local dev: Vite runs on :5173, Django on :8000 (different ports = need full URL)
    return {
      API_BASE_URL: 'http://localhost:8000/api',
      ENVIRONMENT: 'development'
    };
  }

  // Production: relative URL — nginx proxies /api/ to the backend container.
  // Works on ANY domain or IP without code changes.
  return {
    API_BASE_URL: '/api',
    ENVIRONMENT: 'production'
  };
};

const config = getApiConfig();

export default config;




