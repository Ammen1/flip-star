/* FlipStar Web Push service worker.
 *
 * Receives `push` events from the browser's push service, shows a
 * notification, and on click focuses an existing tab (or opens one) and
 * forwards the payload via postMessage so the SPA can deep-link.
 */
/* eslint-disable no-restricted-globals */

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    payload = { title: 'FlipStar', body: event.data ? event.data.text() : '' };
  }
  const title = payload.title || 'FlipStar';
  const options = {
    body: payload.body || '',
    icon: '/Flip_Star_Final_Logo_v3_side__2_-removebg-preview.png',
    badge: '/Flip_Star_Final_Logo_v3_side__2_-removebg-preview.png',
    data: payload.data || {},
    tag: payload.data && payload.data.notification_id
      ? `notif-${payload.data.notification_id}`
      : undefined,
    renotify: false,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = (event.notification && event.notification.data) || {};
  const urlToOpen = new URL('/', self.location.origin).href;
  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true,
      });
      // Focus an existing tab if any and forward the payload.
      for (const client of allClients) {
        try {
          client.postMessage({ type: 'push-click', data });
          if ('focus' in client) {
            await client.focus();
            return;
          }
        } catch (_) {
          // ignore
        }
      }
      // Otherwise open a new window.
      if (self.clients.openWindow) {
        const win = await self.clients.openWindow(urlToOpen);
        if (win) {
          try {
            win.postMessage({ type: 'push-click', data });
          } catch (_) {}
        }
      }
    })()
  );
});
