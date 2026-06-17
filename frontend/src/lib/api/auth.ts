import { ApiClient } from './client';
import type { User, LoginRequest, SignupRequest, AuthResponse } from '$lib/types';

class AuthApi extends ApiClient {
	async login(data: LoginRequest): Promise<AuthResponse> {
		return this.post<AuthResponse>('/api/v1/auth/login', data as unknown as Record<string, unknown>);
	}

	async signup(data: SignupRequest): Promise<AuthResponse> {
		return this.post<AuthResponse>('/api/v1/auth/signup', data as unknown as Record<string, unknown>);
	}

	async logout(): Promise<void> {
		return this.post<void>('/api/v1/auth/logout');
	}

	async getMe(): Promise<User> {
		return this.get<User>('/api/v1/auth/me');
	}
}

export const authApi = new AuthApi();
