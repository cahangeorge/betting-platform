export type SessionEpochMessage = { type: 'logout'; epoch: number };

type Channel = {
	postMessage(message: SessionEpochMessage): void;
	close?(): void;
	unref?(): void;
	onmessage: ((event: MessageEvent<SessionEpochMessage>) => void) | null;
};

type TerminationListener = (remote: boolean) => void;

export class SessionEpochCoordinator {
	private epoch = 0;
	private terminated = false;
	private readonly listeners = new Set<TerminationListener>();
	private readonly channel: Channel | null;

	constructor(channel: Channel | null = createChannel()) {
		this.channel = channel;
		if (this.channel) this.channel.onmessage = (event) => this.receive(event.data);
	}

	current(): number {
		return this.epoch;
	}

	canRefresh(epoch: number): boolean {
		return !this.terminated && epoch === this.epoch;
	}

	activate(): void {
		this.terminated = false;
		this.epoch += 1;
	}

	terminate(broadcast = true): void {
		if (this.terminated) return;
		this.terminated = true;
		this.epoch += 1;
		if (broadcast) this.channel?.postMessage({ type: 'logout', epoch: this.epoch });
		this.emit(false);
	}

	onTerminate(listener: TerminationListener): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}

	private receive(message: SessionEpochMessage): void {
		if (message?.type !== 'logout') return;
		this.epoch = Math.max(this.epoch + 1, message.epoch);
		this.terminated = true;
		this.emit(true);
	}

	private emit(remote: boolean): void {
		for (const listener of this.listeners) listener(remote);
	}
}

function createChannel(): Channel | null {
	if (typeof BroadcastChannel === 'undefined') return null;
	const channel = new BroadcastChannel('bet-session') as Channel;
	channel.unref?.();
	return channel;
}

export const sessionEpoch = new SessionEpochCoordinator();
