/** Web Push plumbing.
 *
 *  Worth being clear about what this is: push goes to *this browser*, not to a
 *  phone number. On iOS it only works once the site is installed to the Home
 *  Screen, which is why the app ships a manifest.
 */
export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/** The subscribe call wants the VAPID key as raw bytes, not base64url. */
function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4))
    .replace(/-/g, '+')
    .replace(/_/g, '/')
  const raw = atob(padded)
  return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)))
}

export async function subscribeToPush(publicKey: string): Promise<PushSubscriptionJSON> {
  if (!pushSupported()) throw new Error('This browser cannot receive push notifications.')
  if (!publicKey) throw new Error('Push is not configured on the server yet.')

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notifications are blocked for this site. Allow them in your browser settings.')
  }

  const registration = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready

  const existing = await registration.pushManager.getSubscription()
  if (existing) return existing.toJSON()

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
  })
  return subscription.toJSON()
}
