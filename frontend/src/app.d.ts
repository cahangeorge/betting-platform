/// <reference types="@sveltejs/kit" />

declare namespace App {
	interface Locals {
		user: import('$lib/types').User | null;
	}

	interface PageData {
		user?: import('$lib/types').User | null;
	}

	// eslint-disable-next-line @typescript-eslint/no-empty-object-type
	interface PageState {}

	// eslint-disable-next-line @typescript-eslint/no-empty-object-type
	interface Platform {}
}
