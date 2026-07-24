import { ApiClient, waitForSessionRefresh } from './client';
import { sessionEpoch } from '../auth/session-epoch.ts';
import type { User, LoginRequest, SignupRequest, AuthResponse } from '$lib/types';

class AuthApi extends ApiClient {
	async login(data: LoginRequest): Promise<AuthResponse> {
		const response = await this.post<AuthResponse>('/api/v1/auth/login', data as unknown as Record<string, unknown>);
		sessionEpoch.activate();
		return response;
	}

	async signup(data: SignupRequest): Promise<AuthResponse> {
		const response = await this.post<AuthResponse>('/api/v1/auth/signup', data as unknown as Record<string, unknown>);
		sessionEpoch.activate();
		return response;
	}

	async logout(): Promise<void> {
		sessionEpoch.terminate();
		await waitForSessionRefresh();
		return this.post<void>('/api/v1/auth/logout');
	}

	async getMe(): Promise<User> {
		return this.get<User>('/api/v1/auth/me');
	}
}

export const authApi = new AuthApi();
