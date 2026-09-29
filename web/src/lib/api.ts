let csrf: string | null = null;

export async function api(
	path: string,
	options: { method?: string; body?: unknown } = {}
): Promise<Response> {
	const method = options.method ?? 'GET';
	const headers: Record<string, string> = {};
	if (method !== 'GET' && method !== 'HEAD') {
		if (!csrf) {
			const issued = await fetch('/api/v1/csrf', { credentials: 'include' });
			const payload = (await issued.json()) as { token: string };
			csrf = payload.token;
		}
		headers['content-type'] = 'application/json';
		headers['x-csrf-token'] = csrf;
	}
	return fetch(path, {
		method,
		credentials: 'include',
		headers,
		body: options.body === undefined ? undefined : JSON.stringify(options.body)
	});
}
