export type RequestGeneration = {
	next: () => number;
	invalidate: () => void;
	isCurrent: (requestId: number) => boolean;
};

export function createRequestGeneration(): RequestGeneration {
	let currentRequestId = 0;

	return {
		next() {
			currentRequestId += 1;
			return currentRequestId;
		},
		invalidate() {
			currentRequestId += 1;
		},
		isCurrent(requestId: number) {
			return requestId === currentRequestId;
		}
	};
}
