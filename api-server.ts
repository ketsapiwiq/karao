import { Database } from 'bun:sqlite';
import { spawn } from 'child_process';
import { mkdir, access, readFile, stat, rm } from 'fs/promises';
import path from 'path';

const DB_PATH = process.env.LRCLIB_DB || '/lrclib.sqlite3';
const DATA_DIR = process.env.DATA_DIR || '/data';
const PORT = parseInt(process.env.PORT || '3001', 10);

const db = new Database(DB_PATH, { readonly: true });
console.log('Database connected');

async function fileExists(p: string): Promise<boolean> {
	try {
		await access(p);
		return true;
	} catch {
		return false;
	}
}

async function handleSearch(q: string, page: number = 1, limit: number = 50): Promise<any[]> {
	const t0 = performance.now();
	// Split query into terms and escape them for FTS, then join with AND (implied by space)
	// We want to support "Artist Title" or "Title Artist"
	const terms = q.split(/\s+/).filter(t => t.length > 0).map(t => `"${t.replace(/"/g, '""')}"`);
	const ftsQuery = terms.join(' ');
	const offset = (page - 1) * limit;
	
	const sql = `
		SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
			   l.has_synced_lyrics, l.has_plain_lyrics
		FROM tracks_fts fts
		CROSS JOIN tracks t ON fts.rowid = t.id
		CROSS JOIN lyrics l ON t.last_lyrics_id = l.id
		WHERE tracks_fts MATCH ? 
		  AND l.has_synced_lyrics = 1 
		  AND l.synced_lyrics IS NOT NULL
		  AND l.synced_lyrics != ''
		LIMIT ? OFFSET ?
	`;
	
	const results = db.query(sql).all(ftsQuery, limit, offset) as any[];
	console.log(`Search for "${q}" (page ${page}) took ${(performance.now() - t0).toFixed(2)}ms, found ${results.length} results`);
	return results;
}

async function handleGetLyrics(id: number): Promise<any> {
	const sql = `
		SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
			   l.synced_lyrics, l.plain_lyrics
		FROM tracks t
		LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
		WHERE t.id = ?
	`;
	return db.query(sql).get(id) as any;
}

const tasks = new Map<string, {
	status: 'pending' | 'processing' | 'completed' | 'failed',
	step: string,
	progress: number,
	error?: string,
	resultUrl?: string,
	originalUrl?: string,
	videoUrl?: string,
	stepSource?: string
}>();

async function handlePrepare(artist: string, title: string, customUrl?: string, force = false, onlyDownload = false): Promise<any> {
	// Ensure customUrl is a string or undefined
	const actualCustomUrl = typeof customUrl === 'string' ? customUrl : undefined;
	
	const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const taskId = slug;

	if (actualCustomUrl || force) {
		console.log(`Forcing re-preparation for ${taskId}${actualCustomUrl ? ` with custom URL: ${actualCustomUrl}` : ''}`);
		tasks.delete(taskId);
		// Cleanup existing directories/files
		const audioDir = path.join(DATA_DIR, 'audio', slug);
		const separatedDir = path.join(DATA_DIR, 'separated', 'htdemucs', slug);
		try {
			if (await fileExists(audioDir)) await rm(audioDir, { recursive: true, force: true });
			if (await fileExists(separatedDir)) await rm(separatedDir, { recursive: true, force: true });
		} catch (e) {
			console.error(`Cleanup failed for ${taskId}:`, e);
		}
	}

	if (tasks.has(taskId) && tasks.get(taskId)?.status !== 'failed') {
		return { taskId };
	}

	tasks.set(taskId, { status: 'pending', step: 'Initializing', progress: 0 });

	// Start background process
	(async () => {
		try {
			console.log(`Background task ${taskId} started${actualCustomUrl ? ' with custom URL' : ''}`);
			const downloadResult = await handleDownload(artist, title, taskId, actualCustomUrl);
			if (downloadResult.error) throw new Error(downloadResult.error);

			// Slug used in handleDownload and runYtDlp is taskId or artist - title
			const originalUrl = `/api/audio/audio/${taskId}/${taskId}.mp3`;
			const videoUrl = downloadResult.videoPath ? `/api/audio/audio/${taskId}/${taskId}.mp4` : undefined;
			
			tasks.set(taskId, { ...tasks.get(taskId)!, originalUrl, videoUrl });

			if (onlyDownload) {
				console.log(`Download for ${taskId} finished, skipping separation as requested.`);
				tasks.set(taskId, { 
					status: 'completed', 
					step: 'Finished', 
					progress: 100, 
					resultUrl: originalUrl,
					originalUrl,
					videoUrl
				});
				return;
			}

			console.log(`Download for ${taskId} finished, starting separation: ${downloadResult.path}`);
			const separateResult = await handleSeparate(downloadResult.path, taskId);
			if (separateResult.error) throw new Error(separateResult.error);

			console.log(`Separation for ${taskId} finished`);
			tasks.set(taskId, { 
				status: 'completed', 
				step: 'Finished', 
				progress: 100, 
				resultUrl: separateResult.url,
				originalUrl,
				videoUrl
			});
		} catch (err: any) {
			console.error(`Task ${taskId} failed:`, err);
			tasks.set(taskId, { status: 'failed', step: 'Error', progress: 0, error: err.message });
		}
	})();

	return { taskId };
}

async function runYtDlp(queryOrUrl: any, outputDir: string, slug: string, taskId: string, provider = 'ytsearch'): Promise<{ success: boolean; path?: string; videoPath?: string; details?: string }> {
	return new Promise((resolve) => {
		if (typeof queryOrUrl !== 'string') {
			console.log(`[yt-dlp] queryOrUrl is not a string, converting: ${JSON.stringify(queryOrUrl)}`);
			queryOrUrl = String(queryOrUrl);
		}
		const isDirectUrl = queryOrUrl.startsWith('http');
		let target: string;
		if (isDirectUrl) {
			target = queryOrUrl;
		} else if (provider.startsWith('http')) {
			target = `${provider}${encodeURIComponent(queryOrUrl)}`;
		} else {
			target = `${provider}1:${queryOrUrl}`;
		}

		// Download video and extract audio so we have both
		// We use double quotes for ffmpeg command and handle escaping
		const audioPath = path.join(outputDir, `${slug}.mp3`);
		const ytDlpArgs = [
			'-m', 'yt_dlp',
			'--format', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
			'--merge-output-format', 'mp4',
			'--postprocessor-args', 'ffmpeg:-movflags +faststart',
			'--no-playlist',
			'--newline',
			'-o', path.join(outputDir, `${slug}.%(ext)s`),
			'--exec', `ffmpeg -y -i {} -vn -acodec libmp3lame -q:a 0 "${audioPath}"`,
			target
		];

		console.log(`[yt-dlp] Starting with target: "${target}"`);

		const ytDlp = spawn('python3', ytDlpArgs);
		
		let stderr = '';
		let stdout = '';
		let downloadedVideoPath = '';

		ytDlp.stdout.on('data', (d) => {
			const output = d.toString();
			stdout += output;
			const lines = output.split('\n').filter(l => l.trim().length > 0);
			
			for (const line of lines) {
				const trimmed = line.trim();
				if (trimmed.includes('[download]')) {
					const match = trimmed.match(/(\d+\.\d+)%/);
					if (match) {
						const progress = parseFloat(match[1]);
						tasks.set(taskId, { ...tasks.get(taskId)!, status: 'processing', step: 'Downloading', progress });
					}
				}
			}
		});

		ytDlp.stderr.on('data', (d) => {
			const output = d.toString();
			console.error(`[yt-dlp] stderr: ${output}`);
			stderr += output;
		});
		
		ytDlp.on('close', async (code) => {
			console.log(`[yt-dlp] exited with code ${code} for target: ${target}`);
			
			const videoPath = path.join(outputDir, `${slug}.mp4`);
			const audioPath = path.join(outputDir, `${slug}.mp3`);

			if (code !== 0) {
				resolve({ success: false, details: stderr });
				return;
			}
			
			if (await fileExists(audioPath)) {
				resolve({ 
					success: true, 
					path: audioPath, 
					videoPath: await fileExists(videoPath) ? videoPath : undefined 
				});
			} else {
				resolve({ success: false, details: 'Audio file not found after successful download.' });
			}
		});
		
		ytDlp.on('error', (err) => {
			console.error('[yt-dlp] Failed to start:', err);
			resolve({ success: false, details: err.message });
		});
	});
}

async function handleDownload(artist: string, title: string, taskId?: string, customUrl?: string): Promise<any> {
	const slug = taskId || `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const actualTaskId = taskId || slug;
	const outputDir = path.join(DATA_DIR, 'audio', slug);
	const finalPath = path.join(outputDir, `${slug}.mp3`);
	const videoPath = path.join(outputDir, `${slug}.mp4`);
	
	await mkdir(outputDir, { recursive: true });

	if (await fileExists(finalPath)) {
		if (taskId) tasks.set(taskId, { ...tasks.get(taskId)!, status: 'processing', step: 'Download (Cached)', progress: 100 });
		return { 
			status: 'cached', 
			path: finalPath, 
			videoPath: await fileExists(videoPath) ? videoPath : undefined 
		};
	}

	if (customUrl) {
		if (taskId) tasks.set(taskId, { ...tasks.get(taskId)!, status: 'processing', step: 'Downloading custom URL...', progress: 0, stepSource: 'Manual URL' });
		const attempt = await runYtDlp(customUrl, outputDir, slug, actualTaskId);
		if (attempt.success && attempt.path) {
			return { status: 'downloaded', path: attempt.path, videoPath: attempt.videoPath };
		}
		return { error: 'Custom URL download failed', details: attempt.details };
	}
	
	const quotedQuery = `"${artist}" "${title}"`;
	const normalQuery = `${artist} ${title}`;

	// Attempt 1: YouTube search (quoted) - usually official/best version
	console.log(`[api] Attempt 1: Searching YouTube for "${quotedQuery}"`);
	if (taskId) tasks.set(taskId, { status: 'processing', step: 'Searching YouTube (Precise)...', progress: 0, stepSource: 'YouTube' });
	const attempt1 = await runYtDlp(quotedQuery, outputDir, slug, actualTaskId, 'ytsearch');
	if (attempt1.success && attempt1.path) return { status: 'downloaded', path: attempt1.path };

	// Attempt 2: Standard YouTube search
	console.log(`[api] Attempt 1 failed. Attempt 2: Searching YouTube for "${normalQuery}"`);
	if (taskId) tasks.set(taskId, { status: 'processing', step: 'Searching YouTube...', progress: 0, stepSource: 'YouTube' });
	const attempt2 = await runYtDlp(normalQuery, outputDir, slug, actualTaskId, 'ytsearch');
	if (attempt2.success && attempt2.path) return { status: 'downloaded', path: attempt2.path };
	
	return { error: 'Download failed', details: attempt2.details || attempt1.details };
}

async function ensureWorkerRunning(): Promise<boolean> {
	const socketPath = '/tmp/demucs_worker.sock';
	if (await fileExists(socketPath)) {
		return true;
	}

	console.log('[api] Starting demucs worker...');
	const worker = spawn('python3', ['demucs_worker.py'], {
		detached: true,
		stdio: 'inherit'
	});
	worker.unref();

	// Wait for socket to appear
	for (let i = 0; i < 30; i++) {
		if (await fileExists(socketPath)) return true;
		await new Promise(r => setTimeout(r, 1000));
	}
	return false;
}

async function handleSeparate(audioPath: string, taskId?: string): Promise<any> {
	const basename = taskId || path.basename(audioPath, path.extname(audioPath));
	const actualTaskId = taskId || basename;
	const outputDir = path.join(DATA_DIR, 'separated');
	const instrumentalPath = path.join(outputDir, 'htdemucs', basename, 'no_vocals.mp3');
	
	if (await fileExists(instrumentalPath)) {
		if (taskId) tasks.set(taskId, { status: 'processing', step: 'Separation (Cached)', progress: 100 });
		return { 
			status: 'cached', 
			instrumentalPath,
			url: `/api/audio/separated/htdemucs/${basename}/no_vocals.mp3`
		};
	}
	
	if (taskId) tasks.set(taskId, { status: 'processing', step: 'Separating (Demucs)', progress: 0 });

	if (!(await ensureWorkerRunning())) {
		return { error: 'Failed to start demucs worker' };
	}

	return new Promise((resolve) => {
		const client = new (require('net').Socket)();
		client.connect('/tmp/demucs_worker.sock', () => {
			client.write(JSON.stringify({
				command: 'separate',
				inputPath: audioPath,
				outputDir: DATA_DIR, // Worker adds 'separated' and model name
				taskId: actualTaskId
			}));
		});

		let buffer = '';
		client.on('data', (d: Buffer) => {
			buffer += d.toString();
			const lines = buffer.split('\n');
			buffer = lines.pop() || ''; // Keep the last incomplete line in buffer

			for (const line of lines) {
				if (!line.trim()) continue;
				try {
					const msg = JSON.parse(line);
					if (msg.type === 'progress') {
						tasks.set(actualTaskId, { 
							...tasks.get(actualTaskId)!, 
							status: 'processing', 
							step: msg.step, 
							progress: msg.progress 
						});
					} else if (msg.success !== undefined) {
						// This is the final result
						if (msg.success) {
							resolve({ 
								status: 'separated',
								instrumentalPath,
								url: `/api/audio/separated/htdemucs/${basename}/no_vocals.mp3`
							});
						} else {
							resolve({ error: 'Separation failed', details: msg.error });
						}
					}
				} catch (e) {
					console.error('[api] Failed to parse worker message:', line, e);
				}
			}
		});

		client.on('close', () => {
			// If we haven't resolved yet, something went wrong
			resolve({ error: 'Worker connection closed unexpectedly' });
		});

		client.on('error', (err: any) => {
			resolve({ error: 'Worker communication error', details: err.message });
		});
	});
}

async function handleAudio(filePath: string, req: Request): Promise<Response> {
	const decodedPath = decodeURIComponent(filePath);
	const fullPath = path.join(DATA_DIR, decodedPath);
	console.log(`Serving audio from: "${fullPath}"`);
	
	try {
		const stats = await stat(fullPath);
		if (!stats.isFile()) {
			console.log(`Audio file not found: "${fullPath}"`);
			return new Response('Not found', { status: 404 });
		}
	} catch (e: any) {
		console.log(`Error stating audio file: "${fullPath}" - ${e.message}`);
		return new Response('Not found', { status: 404 });
	}
	
	const fileBuffer = await readFile(fullPath);
	const contentType = fullPath.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg';
	
	const range = req.headers.get('range');
	if (range) {
		const fileSize = fileBuffer.length;
		const parts = range.replace(/bytes=/, '').split('-');
		const start = parseInt(parts[0], 10);
		const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
		const chunkSize = end - start + 1;
		
		return new Response(fileBuffer.slice(start, end + 1), {
			status: 206,
			headers: {
				'Content-Range': `bytes ${start}-${end}/${fileSize}`,
				'Accept-Ranges': 'bytes',
				'Content-Length': chunkSize.toString(),
				'Content-Type': contentType
			}
		});
	}
	
	return new Response(fileBuffer, {
		headers: {
			'Content-Length': fileBuffer.length.toString(),
			'Content-Type': contentType
		}
	});
}

const server = Bun.serve({
	port: PORT,
	async fetch(req: Request): Promise<Response> {
		const url = new URL(req.url);
		
		const corsHeaders = {
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
			'Access-Control-Allow-Headers': 'Content-Type'
		};
		
		if (req.method === 'OPTIONS') {
			return new Response(null, { status: 204, headers: corsHeaders });
		}
		
		try {
			// console.log(`[${new Date().toISOString()}] ${req.method} ${url.pathname}${url.search}`);
			
			if (url.pathname === '/api/health') {
				return new Response(JSON.stringify({ status: 'ok', uptime: process.uptime() }), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/search-lyrics') {
				const q = url.searchParams.get('q');
				const page = parseInt(url.searchParams.get('page') || '1', 10);
				const limit = parseInt(url.searchParams.get('limit') || '50', 10);
				if (!q) {
					return new Response(JSON.stringify({ error: 'Missing q parameter' }), { 
						status: 400, 
						headers: { ...corsHeaders, 'Content-Type': 'application/json' }
					});
				}
				console.log(`Searching for: ${q} (page: ${page}, limit: ${limit})`);
				const results = await handleSearch(q, page, limit);
				return new Response(JSON.stringify({ results }), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/lyrics' && req.method === 'GET') {
				const id = url.searchParams.get('id');
				if (!id) {
					return new Response(JSON.stringify({ error: 'Missing id parameter' }), { 
						status: 400, 
						headers: { ...corsHeaders, 'Content-Type': 'application/json' }
					});
				}
				const row = await handleGetLyrics(parseInt(id, 10));
				if (!row) {
					return new Response(JSON.stringify({ error: 'Track not found' }), { 
						status: 404, 
						headers: { ...corsHeaders, 'Content-Type': 'application/json' }
					});
				}
				return new Response(JSON.stringify(row), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/prepare' && req.method === 'POST') {
				const body = await req.json();
				const { artist, title, youtubeUrl, force, onlyDownload } = body as { artist: string; title: string; youtubeUrl?: string; force?: boolean; onlyDownload?: boolean };
				const result = await handlePrepare(artist, title, youtubeUrl, force, onlyDownload);
				return new Response(JSON.stringify(result), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname.startsWith('/api/tasks/')) {
				const taskId = decodeURIComponent(url.pathname.replace('/api/tasks/', ''));
				const task = tasks.get(taskId);
				if (!task) {
					return new Response(JSON.stringify({ error: 'Task not found' }), { 
						status: 404, 
						headers: { ...corsHeaders, 'Content-Type': 'application/json' }
					});
				}
				return new Response(JSON.stringify(task), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/download' && req.method === 'POST') {
				const body = await req.json();
				const { artist, title } = body as { artist: string; title: string };
				const result = await handleDownload(artist, title);
				return new Response(JSON.stringify(result), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/separate' && req.method === 'POST') {
				const body = await req.json();
				const { audioPath } = body as { audioPath: string };
				const result = await handleSeparate(audioPath);
				return new Response(JSON.stringify(result), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname.startsWith('/api/audio/')) {
				const filePath = url.pathname.replace('/api/audio/', '');
				return handleAudio(filePath, req);
			}
			else {
				return new Response(JSON.stringify({ error: 'Not found' }), { 
					status: 404, 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
		} catch (err) {
			console.error('Error:', err);
			return new Response(JSON.stringify({ error: 'Internal server error' }), { 
				status: 500, 
				headers: { ...corsHeaders, 'Content-Type': 'application/json' }
			});
		}
	}
});

console.log(`API server listening on port ${PORT}`);
