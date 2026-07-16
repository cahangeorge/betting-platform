import { ApiClient } from './client';
import type {
	TicketBatch,
	TicketBatchActivateResponse,
	TicketBatchActivateRequest,
	TicketBatchRefreshResponse,
	Ticket,
	PlaceBetRequest,
	SettleRequest,
	TicketGenerateRequest,
	TicketGenerateResponse,
	TicketPreflightRequest,
	TicketPreflightResponse,
	TicketBatchLineage,
	TicketSettlementRun,
	TicketSwapLegsRequest,
	TicketSwapLegsResponse,
	PaginatedResponse
} from '$lib/types';

class TicketsApi extends ApiClient {
	async getTickets(status?: string): Promise<Ticket[]> {
		const sp = new URLSearchParams();
		sp.set('per_page', '100');
		if (status) sp.set('status', status);
		const qs = sp.toString();
		return this.get<Ticket[]>(`/api/v1/tickets${qs ? `?${qs}` : ''}`);
	}

	async getBatchTickets(batchId: number): Promise<Ticket[]> {
		return this.get<Ticket[]>(`/api/v1/tickets/batches/${batchId}/tickets?per_page=300`);
	}

	async getBatchLineage(batchId: number): Promise<TicketBatchLineage> {
		return this.get<TicketBatchLineage>(`/api/v1/tickets/batches/${batchId}/lineage`);
	}

	async getBatches(): Promise<TicketBatch[]> {
		return this.get<TicketBatch[]>('/api/v1/tickets/batches');
	}

	async getTicketsPage(params?: {
		page?: number;
		per_page?: number;
		status?: string;
		batch_id?: number;
	}): Promise<PaginatedResponse<Ticket>> {
		const sp = new URLSearchParams();
		if (params?.page !== undefined) sp.set('page', String(params.page));
		if (params?.per_page !== undefined) sp.set('per_page', String(params.per_page));
		if (params?.status) sp.set('status', params.status);
		if (params?.batch_id !== undefined) sp.set('batch_id', String(params.batch_id));
		const qs = sp.toString();
		return this.get<PaginatedResponse<Ticket>>(`/api/v1/tickets/page${qs ? `?${qs}` : ''}`);
	}

	async getTicket(id: number): Promise<Ticket> {
		return this.get<Ticket>(`/api/v1/tickets/${id}`);
	}

	async placeBet(data: PlaceBetRequest): Promise<Ticket> {
		return this.post<Ticket>('/api/v1/tickets', data as unknown as Record<string, unknown>);
	}

	async settleTicket(data: SettleRequest): Promise<Ticket> {
		return this.post<Ticket>(`/api/v1/tickets/${data.ticket_id}/settle`, { outcome: data.outcome, return_amount: data.return_amount } as unknown as Record<string, unknown>);
	}

	async settleDue(): Promise<TicketSettlementRun> {
		return this.post<TicketSettlementRun>('/api/v1/tickets/settle-due');
	}

	async generate(data: TicketGenerateRequest): Promise<TicketGenerateResponse> {
		return this.post<TicketGenerateResponse>('/api/v1/tickets/generate', data as unknown as Record<string, unknown>);
	}

	async preflight(data: TicketPreflightRequest): Promise<TicketPreflightResponse> {
		return this.post<TicketPreflightResponse>(
			'/api/v1/tickets/preflight',
			data as unknown as Record<string, unknown>
		);
	}

	async activateBatch(batchId: number, data: TicketBatchActivateRequest): Promise<TicketBatchActivateResponse> {
		return this.post<TicketBatchActivateResponse>(
			`/api/v1/tickets/batches/${batchId}/activate`,
			data as unknown as Record<string, unknown>
		);
	}

	async refreshBatch(batchId: number, expectedRevision: number): Promise<TicketBatchRefreshResponse> {
		return this.post<TicketBatchRefreshResponse>(
			`/api/v1/tickets/batches/${batchId}/refresh`,
			{ expected_revision: expectedRevision }
		);
	}

	async discardDraftBatch(batchId: number): Promise<{
		batch_id: number;
		status: 'discarded';
		discarded_tickets: number;
	}> {
		return this.del(`/api/v1/tickets/batches/${batchId}`);
	}

	async swapLegs(batchId: number, data: TicketSwapLegsRequest): Promise<TicketSwapLegsResponse> {
		return this.post<TicketSwapLegsResponse>(
			`/api/v1/tickets/batches/${batchId}/swap-legs`,
			data as unknown as Record<string, unknown>
		);
	}

	async getStats(): Promise<{ total: number; won: number; lost: number; profit_loss: number }> {
		return this.get<{ total: number; won: number; lost: number; profit_loss: number }>('/api/v1/tickets/stats');
	}
}

export const ticketsApi = new TicketsApi();
