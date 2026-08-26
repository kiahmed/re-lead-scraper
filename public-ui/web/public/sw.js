// Service worker for Web Push.
//
// iOS only delivers push to an *installed* PWA, which is why this ships with
// a manifest — on iPhone the site has to be added to the Home Screen first.
// Everywhere else a permission prompt is enough.

self.addEventListener('push', (event) => {
  let payload = { title: 'FlyNest', body: 'A lead matched one of your alerts.', url: '/browse' }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch {
    // a push with no/!JSON body still deserves to surface
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: payload.tag || 'flynest-alert',
      data: { url: payload.url },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/browse'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      // focus an already-open tab rather than piling up new ones
      for (const client of clients) {
        if ('focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      return self.clients.openWindow(url)
    }),
  )
})
