export interface BackendLoadStatus {
	state: 'ready' | 'degraded';
	message: string | null;
	failedEndpoints: string[];
}
