const getApiConfig = () => {
  return {
    // API_BASE_URL: 'http://192.168.1.8:8000/api',  // Physical phone via WiFi - Commented out
    // API_BASE_URL: 'http://196.189.236.140/api',  // Old production server
    API_BASE_URL: 'https://uat.flipstar.et/api',  // New UAT server
    ENVIRONMENT: 'development'
  };
};

const config = getApiConfig();

export default config;
