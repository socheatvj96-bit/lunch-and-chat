self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => clients.claim());
self.addEventListener('fetch', e => e.respondWith(fetch(e.request).catch(() => caches.match(e.request))));

self.addEventListener('push', e => {
    if (!e.data) return;
    let data;
    try { data = e.data.json(); } catch { data = { title: 'Новое сообщение', body: e.data.text() }; }

    const title = data.title || 'Обеды ПМ';
    const body = data.body || '';
    const sender = data.sender || '';
    const recipient = data.recipient || '';

    e.waitUntil(
        self.registration.showNotification(title, {
            body,
            icon: '/static/orders/icon-192.png',
            badge: '/static/orders/icon-192.png',
            tag: recipient ? `dm-${sender}` : 'general-chat',
            renotify: true,
            data: { sender, recipient, url: '/app/' }
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
            if (list.length) { list[0].focus(); return; }
            clients.openWindow(e.notification.data?.url || '/app/');
        })
    );
});
