/// <reference types="@sveltejs/kit" />

declare namespace App {
	interface Locals {
		user: {
			id: number;
			email: string;
			name: string;
		} | null;
	}

	interface PageData {
		user?: {
			id: number;
			email: string;
			name: string;
		} | null;
	}

	// eslint-disable-next-line @typescript-eslint/no-empty-object-type
	interface PageState {}

	// eslint-disable-next-line @typescript-eslint/no-empty-object-type
	interface Platform {}
}
