import assert from 'node:assert/strict';
import test from 'node:test';
import { SessionEpochCoordinator, type SessionEpochMessage } from '../../src/lib/auth/session-epoch.ts';

type TestChannel = {
	onmessage: ((event: MessageEvent<SessionEpochMessage>) => void) | null;
	peer?: TestChannel;
	postMessage(message: SessionEpochMessage): void;
};

function channelPair(): [TestChannel, TestChannel] {
	const first: TestChannel = {
		onmessage: null,
		postMessage(message) { this.peer?.onmessage?.({ data: message } as MessageEvent<SessionEpochMessage>); }
	};
	const second: TestChannel = {
		onmessage: null,
		postMessage(message) { this.peer?.onmessage?.({ data: message } as MessageEvent<SessionEpochMessage>); }
	};
	first.peer = second;
	second.peer = first;
	return [first, second];
}

test('broadcast logout invalidates another tab epoch and marks it remote', () => {
	const [firstChannel, secondChannel] = channelPair();
	const first = new SessionEpochCoordinator(firstChannel);
	const second = new SessionEpochCoordinator(secondChannel);
	let remote = false;
	second.onTerminate((isRemote) => { remote = isRemote; });
	const secondEpoch = second.current();

	first.terminate();

	assert.equal(remote, true);
	assert.equal(second.canRefresh(secondEpoch), false);
});
