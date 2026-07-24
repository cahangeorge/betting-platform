import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { createServer } from 'node:https';
import { request } from 'node:http';
import { resolve } from 'node:path';

const httpsPort = Number(process.env.E2E_PWA_HTTPS_PORT ?? 4173);
const appPort = Number(process.env.E2E_PWA_APP_PORT ?? 4174);
const host = '127.0.0.1';
const backendURL = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8001';
const artifactDir = resolve('../.playwright-artifacts/frontend/pwa-https');
const keyPath = resolve(artifactDir, 'localhost.key');
const certPath = resolve(artifactDir, 'localhost.crt');

mkdirSync(artifactDir, { recursive: true });
const certificate = spawnSync(
	'openssl',
	[
		'req',
		'-x509',
		'-newkey',
		'rsa:2048',
		'-nodes',
		'-keyout',
		keyPath,
		'-out',
		certPath,
		'-days',
		'1',
		'-subj',
		'/CN=127.0.0.1',
		'-addext',
		'subjectAltName=IP:127.0.0.1'
	],
	{ stdio: 'ignore' }
);
if (certificate.status !== 0) {
	throw new Error('Unable to create the ephemeral PWA HTTPS certificate');
}

const app = spawn('node', ['build'], {
	stdio: 'inherit',
	env: {
		...process.env,
		HOST: host,
		PORT: String(appPort),
		ORIGIN: `https://${host}:${httpsPort}`,
		BET_API_URL: backendURL,
		BET_TRADING_PAPER_ENABLED: 'false'
	}
});

const updateWorker = `
self.addEventListener('install', () => {});
self.addEventListener('message', (event) => {
	if (event.data?.type === 'SKIP_WAITING') {
		self.skipWaiting();
	}
});
self.addEventListener('activate', (event) => {
	event.waitUntil(self.clients.claim());
});
`;

const server = createServer(
	{
		key: readFileSync(keyPath),
		cert: readFileSync(certPath)
	},
	(clientRequest, clientResponse) => {
		if (clientRequest.url?.startsWith('/pwa-test-update-sw.js')) {
			clientResponse.writeHead(200, {
				'Cache-Control': 'no-store',
				'Content-Type': 'application/javascript',
				'Service-Worker-Allowed': '/'
			});
			clientResponse.end(updateWorker);
			return;
		}

		const target = clientRequest.url?.startsWith('/api/') ? new URL(backendURL) : null;
		const proxyRequest = request(
			{
				host: target?.hostname ?? host,
				port: target?.port || appPort,
				method: clientRequest.method,
				path: clientRequest.url,
				headers: {
					...clientRequest.headers,
					host: target?.host ?? `${host}:${appPort}`,
					'x-forwarded-proto': 'https',
					'x-forwarded-host': `${host}:${httpsPort}`
				}
			},
			(proxyResponse) => {
				clientResponse.writeHead(proxyResponse.statusCode ?? 502, proxyResponse.headers);
				proxyResponse.pipe(clientResponse);
			}
		);
		proxyRequest.on('error', (error) => {
			clientResponse.writeHead(502, { 'Content-Type': 'text/plain' });
			clientResponse.end(`PWA preview proxy error: ${error.message}`);
		});
		clientRequest.pipe(proxyRequest);
	}
);

server.listen(httpsPort, host);

function shutdown() {
	server.close();
	if (!app.killed) app.kill('SIGTERM');
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
app.on('exit', (code) => {
	if (code && code !== 0) process.exitCode = code;
	server.close();
});
