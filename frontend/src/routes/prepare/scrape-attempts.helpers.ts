export type FailedScrapeAttempt = {
	label: string;
	params: Record<string, unknown>;
	league?: string;
	jobId?: number;
	idempotencyKey: string;
	reason: string;
};

export function safeScrapeFailureReason(error: unknown): string {
	const message = error instanceof Error ? error.message : 'Eroare necunoscută la pornirea jobului.';
	return message.replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 240) || 'Eroare necunoscută la pornirea jobului.';
}

export function scrapeAttemptNotice(createdJobIds: number[], failedAttempts: FailedScrapeAttempt[]): string {
	if (failedAttempts.length === 0) return `Joburi create și pornite: #${createdJobIds.join(', ')}.`;

	const outcome = createdJobIds.length
		? `Joburile reușite au fost păstrate: #${createdJobIds.join(', ')}.`
		: 'Niciun job nu a fost pornit.';
	return `${failedAttempts.length} parte${failedAttempts.length === 1 ? '' : 'e'} nu a putut fi pornită. ${outcome} Reîncearcă doar părțile eșuate.`;
}
