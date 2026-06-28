// Web Notifications API helpers — desktop/OS notifications while the page is
// open (foreground or background tab). Requires HTTPS (or localhost) and user
// permission. For notifications when the browser is fully closed you'd need a
// Service Worker + Web Push + a push server (backend) — out of scope here.

export function notifySupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notifPermission() {
  return notifySupported() ? Notification.permission : "unsupported";
}

export function requestNotifyPermission() {
  if (!notifySupported()) return Promise.resolve("unsupported");
  try {
    const r = Notification.requestPermission();
    // Older Safari uses a callback signature and returns undefined.
    return r && typeof r.then === "function"
      ? r
      : new Promise((resolve) => Notification.requestPermission(resolve));
  } catch {
    return Promise.resolve(Notification.permission);
  }
}

export function sendNotification(title, body, tag) {
  if (!notifySupported() || Notification.permission !== "granted") return;
  try {
    new Notification(title, { body, tag, renotify: true });
  } catch {
    // Some platforms require a ServiceWorkerRegistration to show notifications;
    // ignore so the in-app feed still works.
  }
}
