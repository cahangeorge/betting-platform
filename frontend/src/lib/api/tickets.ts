import { ApiClient } from './client';
import type { Ticket, PlaceBetRequest, SettleRequest } from '$lib/types';

class TicketsApi extends ApiClient {
	async getTickets(status?: string): Promise<Ticket[]> {
		return this.get<Ticket[]>('/api/v1/tickets');
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

	async getStats(): Promise<{ total: number; won: number; lost: number; profit_loss: number }> {
		return this.get<{ total: number; won: number; lost: number; profit_loss: number }>('/api/v1/tickets/stats');
	}
}

export const ticketsApi = new TicketsApi();
