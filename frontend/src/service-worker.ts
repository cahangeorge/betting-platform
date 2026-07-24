/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

const sw = self as unknown as ServiceWorkerGlobalScope;

import { build, files, version } from '$service-worker';

// Create a unique cache name for this deployment
const CACHE_PREFIX = 'betfront-';
const CACHE = `${CACHE_PREFIX}${version}`;
const OFFLINE_FALLBACK = '/offline.html';

// `files` already contains the contents of `static`, including the offline page.
// Keep the explicit fallback for custom serviceWorker.files configurations, while
// deduplicating because Cache.addAll rejects duplicate requests.
const ASSETS = Array.from(new Set([...build, ...files, OFFLINE_FALLBACK]));

// Install service worker
sw.addEventListener('install', (event) => {
	async function addFilesToCache() {
		const cache = await caches.open(CACHE);
		await cache.addAll(ASSETS);
	}
	event.waitUntil(addFilesToCache());
});

sw.addEventListener('message', (event) => {
	if (event.data?.type === 'SKIP_WAITING') {
		void sw.skipWaiting();
	}
});

// Activate and clean old caches + take control immediately
sw.addEventListener('activate', (event) => {
	async function deleteOldCaches() {
		const keys = await caches.keys();
		await Promise.all(
			keys
				.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE)
				.map((key) => caches.delete(key))
		);
		// Take control of all open tabs immediately
		await sw.clients.claim();
	}
	event.waitUntil(deleteOldCaches());
});

// Fetch strategy
sw.addEventListener('fetch', (event) => {
	// Ignore non-GET requests
	if (event.request.method !== 'GET') return;

	// Ignore chrome-extension requests
	if (event.request.url.startsWith('chrome-extension://')) return;

	const url = new URL(event.request.url);
	const isSameOrigin = url.origin === self.location.origin;
	const isNavigationRequest =
		event.request.mode === 'navigate' ||
		(event.request.destination === 'document' && isSameOrigin);
	const isApiCall = url.pathname.startsWith('/api/');
	const isAsset = ASSETS.includes(url.pathname);

	// Never intercept cross-origin requests or persist authenticated API responses.
	if (!isSameOrigin) {
		return;
	}

	if (isApiCall) {
		event.respondWith(fetch(event.request));
	} else if (isNavigationRequest) {
		event.respondWith(navigationFallback(event.request));
	} else if (isAsset) {
		// Only the versioned, known-public static asset list is cacheable.
		event.respondWith(cacheFirst(event.request));
	}
});

async function cacheFirst(request: Request): Promise<Response> {
	const cache = await caches.open(CACHE);
	const cached = await cache.match(request);
	if (cached) {
		return cached;
	}
	try {
		const response = await fetch(request);
		return response;
	} catch {
		// Return offline fallback for assets
		return new Response('Offline', { status: 503 });
	}
}

async function navigationFallback(request: Request): Promise<Response> {
	try {
		return await fetch(request);
	} catch {
		const cache = await caches.open(CACHE);
		const offlinePage = await cache.match(OFFLINE_FALLBACK);
		if (offlinePage) {
			return offlinePage;
		}

		return new Response('Offline', { status: 503 });
	}
}
