// Web Push subscription helper.
//
// Usage:
//   import webPush from './services/WebPushService';
//   await webPush.ensureSubscribed();   // call after login
//   await webPush.unsubscribe();        // call on logout
//
// Silently no-ops in unsupported browsers, on insecure origins, or when the
// backend hasn't been configured with VAPID keys.

import api from '../api';

const SW_URL = '/push-sw.js';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

function isSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

async function registerServiceWorker() {
  if (!isSupported()) return null;
  try {
    const existing = await navigator.serviceWorker.getRegistration(SW_URL);
    if (existing) return existing;
    return await navigator.serviceWorker.register(SW_URL);
  } catch (err) {
    console.warn('[WebPush] SW registration failed', err);
    return null;
  }
}

async function getVapidPublicKey() {
  try {
    const res = await api.request('/push/public-key/');
    return (res && res.public_key) || '';
  } catch (err) {
    console.warn('[WebPush] failed to fetch VAPID public key', err);
    return '';
  }
}

async function requestPermission() {
  if (!('Notification' in window)) return 'denied';
  if (Notification.permission === 'granted' || Notification.permission === 'denied') {
    return Notification.permission;
  }
  try {
    return await Notification.requestPermission();
  } catch (_) {
    return 'denied';
  }
}

async function ensureSubscribed() {
  if (!isSupported()) return { ok: false, reason: 'unsupported' };
  const reg = await registerServiceWorker();
  if (!reg) return { ok: false, reason: 'no-sw' };

  const permission = await requestPermission();
  if (permission !== 'granted') return { ok: false, reason: 'permission-' + permission };

  const publicKey = await getVapidPublicKey();
  if (!publicKey) return { ok: false, reason: 'no-vapid-key' };

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    try {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    } catch (err) {
      console.warn('[WebPush] subscribe failed', err);
      return { ok: false, reason: 'subscribe-failed' };
    }
  }

  try {
    await api.request('/push/subscribe/', {
      method: 'POST',
      body: JSON.stringify(sub.toJSON()),
    });
  } catch (err) {
    console.warn('[WebPush] failed to register subscription with backend', err);
    return { ok: false, reason: 'backend-failed' };
  }
  return { ok: true };
}

async function unsubscribe() {
  if (!isSupported()) return;
  try {
    const reg = await navigator.serviceWorker.getRegistration(SW_URL);
    if (!reg) return;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return;
    try {
      await api.request('/push/unsubscribe/', {
        method: 'POST',
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
    } catch (_) {}
    try { await sub.unsubscribe(); } catch (_) {}
  } catch (err) {
    console.warn('[WebPush] unsubscribe failed', err);
  }
}

// Listen for clicks coming from the SW so the SPA can deep-link.
function onPushClick(handler) {
  if (!isSupported()) return () => {};
  const listener = (event) => {
    if (event?.data?.type === 'push-click') {
      try { handler(event.data.data || {}); } catch (_) {}
    }
  };
  navigator.serviceWorker.addEventListener('message', listener);
  return () => navigator.serviceWorker.removeEventListener('message', listener);
}

export default {
  isSupported,
  ensureSubscribed,
  unsubscribe,
  onPushClick,
};
