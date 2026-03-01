import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	if (event.url.pathname.startsWith('/api')) {
		const apiUrl = process.env.API_URL || 'http://localhost:3001';
		const targetUrl = `${apiUrl}${event.url.pathname}${event.url.search}`;
		
		const headers = new Headers(event.request.headers);
		headers.delete('host');
		
		try {
			const res = await fetch(targetUrl, {
				method: event.request.method,
				headers,
				body: event.request.method !== 'GET' && event.request.method !== 'HEAD' 
					? await event.request.arrayBuffer() 
					: undefined
			});
			
			return res;
		} catch (e) {
			console.error('Proxy error:', e);
			return new Response('Proxy error', { status: 502 });
		}
	}

	return resolve(event);
};