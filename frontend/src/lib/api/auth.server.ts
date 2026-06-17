const API_BASE = process.env.BET_API_URL || 'http://localhost:8001';

class AuthApiServer {
	async login(data: { email: string; password: string }): Promise<{ access_token: string; token_type: string }> {
		const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data)
		});
		if (!res.ok) {
			const err = await res.json().catch(() => ({ detail: 'Login failed' }));
			throw new Error(err.detail || `HTTP ${res.status}`);
		}
		return res.json();
	}

	async signup(data: { email: string; password: string; name: string }): Promise<{ access_token: string; token_type: string }> {
		const res = await fetch(`${API_BASE}/api/v1/auth/signup`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data)
		});
		if (!res.ok) {
			const err = await res.json().catch(() => ({ detail: 'Signup failed' }));
			throw new Error(err.detail || `HTTP ${res.status}`);
		}
		return res.json();
	}
}

export const authApi = new AuthApiServer();