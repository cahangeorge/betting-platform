
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/private';
 * 
 * console.log(ENVIRONMENT); // => "production"
 * console.log(PUBLIC_BASE_URL); // => throws error during build
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/private' {
	export const SVELTEKIT_FORK: string;
	export const NODE_ENV: string;
	export const EDITOR: string;
	export const INIT_CWD: string;
	export const HERMES_REDACT_SECRETS: string;
	export const BROWSER_INACTIVITY_TIMEOUT: string;
	export const HERMES_WEBUI_DEFAULT_MODEL: string;
	export const LC_ALL: string;
	export const npm_config_init_module: string;
	export const npm_config_globalconfig: string;
	export const TERMINAL_DOCKER_RUN_AS_HOST_USER: string;
	export const HERMES_WEBUI_HOST: string;
	export const TERMINAL_CONTAINER_DISK: string;
	export const PWD: string;
	export const HERMES_SESSION_PLATFORM: string;
	export const TERMINAL_SINGULARITY_IMAGE: string;
	export const HERMES_WEBUI_STATE_DIR: string;
	export const UV_PROJECT_ENVIRONMENT: string;
	export const PYTHON_VERSION: string;
	export const HERMES_WEBUI_PASSWORD: string;
	export const npm_lifecycle_event: string;
	export const DEBIAN_FRONTEND: string;
	export const npm_lifecycle_script: string;
	export const MOA_TOOLS_DEBUG: string;
	export const TERMINAL_CONTAINER_MEMORY: string;
	export const ENV_IGNORELIST: string;
	export const HERMES_EXEC_ASK: string;
	export const TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE: string;
	export const HERMES_WEBUI_PORT: string;
	export const npm_package_version: string;
	export const GPG_KEY: string;
	export const npm_execpath: string;
	export const VIRTUAL_ENV: string;
	export const WEB_TOOLS_DEBUG: string;
	export const TERMINAL_MODAL_IMAGE: string;
	export const TERMINAL_ENV: string;
	export const npm_config_npm_version: string;
	export const TERMINAL_MODAL_MODE: string;
	export const TERMINAL_DOCKER_IMAGE: string;
	export const npm_package_json: string;
	export const _HW_ROOT_ENV_PATH: string;
	export const BROWSERBASE_PROXIES: string;
	export const UV_CACHE_DIR: string;
	export const HERMES_HOME: string;
	export const VIRTUAL_ENV_PROMPT: string;
	export const HOME: string;
	export const HERMES_WEBUI_DEFAULT_WORKSPACE: string;
	export const TERMINAL_PERSISTENT_SHELL: string;
	export const HERMES_SESSION_KEY: string;
	export const MAIL: string;
	export const npm_node_execpath: string;
	export const TERMINAL_DOCKER_ENV: string;
	export const TERMINAL_DOCKER_FORWARD_ENV: string;
	export const TERMINAL_CWD: string;
	export const npm_config_local_prefix: string;
	export const USER: string;
	export const OLDPWD: string;
	export const npm_config_user_agent: string;
	export const npm_config_global_prefix: string;
	export const WANTED_GID: string;
	export const BROWSER_SESSION_TIMEOUT: string;
	export const ENV_OBFUSCATE_PART: string;
	export const npm_config_noproxy: string;
	export const HOSTNAME: string;
	export const HERMES_QUIET: string;
	export const HERMES_WEBUI_AGENT_DIR: string;
	export const SHLVL: string;
	export const GH_TOKEN: string;
	export const TERMINAL_CONTAINER_PERSISTENT: string;
	export const LANG: string;
	export const IMAGE_TOOLS_DEBUG: string;
	export const npm_config_userconfig: string;
	export const VISION_TOOLS_DEBUG: string;
	export const PYTHON_SHA256: string;
	export const _: string;
	export const COLOR: string;
	export const npm_command: string;
	export const LOGNAME: string;
	export const PYTHONIOENCODING: string;
	export const TERMINAL_CONTAINER_CPU: string;
	export const PYTHONDONTWRITEBYTECODE: string;
	export const npm_config_prefix: string;
	export const TERMINAL_LIFETIME_SECONDS: string;
	export const BROWSERBASE_ADVANCED_STEALTH: string;
	export const TERMINAL_DAYTONA_IMAGE: string;
	export const PYTHONUNBUFFERED: string;
	export const npm_config_cache: string;
	export const WANTED_UID: string;
	export const HERMES_SESSION_ID: string;
	export const TERMINAL_TIMEOUT: string;
	export const SHELL: string;
	export const npm_config_node_gyp: string;
	export const TERMINAL_DOCKER_VOLUMES: string;
	export const PATH: string;
	export const NODE: string;
	export const npm_package_name: string;
}

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/public';
 * 
 * console.log(ENVIRONMENT); // => throws error during build
 * console.log(PUBLIC_BASE_URL); // => "http://site.com"
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * 
 * console.log(env.ENVIRONMENT); // => "production"
 * console.log(env.PUBLIC_BASE_URL); // => undefined
 * ```
 */
declare module '$env/dynamic/private' {
	export const env: {
		SVELTEKIT_FORK: string;
		NODE_ENV: string;
		EDITOR: string;
		INIT_CWD: string;
		HERMES_REDACT_SECRETS: string;
		BROWSER_INACTIVITY_TIMEOUT: string;
		HERMES_WEBUI_DEFAULT_MODEL: string;
		LC_ALL: string;
		npm_config_init_module: string;
		npm_config_globalconfig: string;
		TERMINAL_DOCKER_RUN_AS_HOST_USER: string;
		HERMES_WEBUI_HOST: string;
		TERMINAL_CONTAINER_DISK: string;
		PWD: string;
		HERMES_SESSION_PLATFORM: string;
		TERMINAL_SINGULARITY_IMAGE: string;
		HERMES_WEBUI_STATE_DIR: string;
		UV_PROJECT_ENVIRONMENT: string;
		PYTHON_VERSION: string;
		HERMES_WEBUI_PASSWORD: string;
		npm_lifecycle_event: string;
		DEBIAN_FRONTEND: string;
		npm_lifecycle_script: string;
		MOA_TOOLS_DEBUG: string;
		TERMINAL_CONTAINER_MEMORY: string;
		ENV_IGNORELIST: string;
		HERMES_EXEC_ASK: string;
		TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE: string;
		HERMES_WEBUI_PORT: string;
		npm_package_version: string;
		GPG_KEY: string;
		npm_execpath: string;
		VIRTUAL_ENV: string;
		WEB_TOOLS_DEBUG: string;
		TERMINAL_MODAL_IMAGE: string;
		TERMINAL_ENV: string;
		npm_config_npm_version: string;
		TERMINAL_MODAL_MODE: string;
		TERMINAL_DOCKER_IMAGE: string;
		npm_package_json: string;
		_HW_ROOT_ENV_PATH: string;
		BROWSERBASE_PROXIES: string;
		UV_CACHE_DIR: string;
		HERMES_HOME: string;
		VIRTUAL_ENV_PROMPT: string;
		HOME: string;
		HERMES_WEBUI_DEFAULT_WORKSPACE: string;
		TERMINAL_PERSISTENT_SHELL: string;
		HERMES_SESSION_KEY: string;
		MAIL: string;
		npm_node_execpath: string;
		TERMINAL_DOCKER_ENV: string;
		TERMINAL_DOCKER_FORWARD_ENV: string;
		TERMINAL_CWD: string;
		npm_config_local_prefix: string;
		USER: string;
		OLDPWD: string;
		npm_config_user_agent: string;
		npm_config_global_prefix: string;
		WANTED_GID: string;
		BROWSER_SESSION_TIMEOUT: string;
		ENV_OBFUSCATE_PART: string;
		npm_config_noproxy: string;
		HOSTNAME: string;
		HERMES_QUIET: string;
		HERMES_WEBUI_AGENT_DIR: string;
		SHLVL: string;
		GH_TOKEN: string;
		TERMINAL_CONTAINER_PERSISTENT: string;
		LANG: string;
		IMAGE_TOOLS_DEBUG: string;
		npm_config_userconfig: string;
		VISION_TOOLS_DEBUG: string;
		PYTHON_SHA256: string;
		_: string;
		COLOR: string;
		npm_command: string;
		LOGNAME: string;
		PYTHONIOENCODING: string;
		TERMINAL_CONTAINER_CPU: string;
		PYTHONDONTWRITEBYTECODE: string;
		npm_config_prefix: string;
		TERMINAL_LIFETIME_SECONDS: string;
		BROWSERBASE_ADVANCED_STEALTH: string;
		TERMINAL_DAYTONA_IMAGE: string;
		PYTHONUNBUFFERED: string;
		npm_config_cache: string;
		WANTED_UID: string;
		HERMES_SESSION_ID: string;
		TERMINAL_TIMEOUT: string;
		SHELL: string;
		npm_config_node_gyp: string;
		TERMINAL_DOCKER_VOLUMES: string;
		PATH: string;
		NODE: string;
		npm_package_name: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://example.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.ENVIRONMENT); // => undefined, not public
 * console.log(env.PUBLIC_BASE_URL); // => "http://example.com"
 * ```
 * 
 * ```
 * 
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
