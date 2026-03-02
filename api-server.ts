import { Database } from 'bun:sqlite';
import { spawn } from 'child_process';
import { mkdir, access, readFile, stat } from 'fs/promises';
import path from 'path';

const DB_PATH = process.env.LRCLIB_DB || '/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3';
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
	resultUrl?: string
}>();

async function handlePrepare(artist: string, title: string, customUrl?: string): Promise<any> {
	const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const taskId = slug;

	if (customUrl) {
		console.log(`Forcing re-preparation for ${taskId} with custom URL: ${customUrl}`);
		tasks.delete(taskId);
		// Cleanup existing directories
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
		console.log(`Task ${taskId} already exists with status: ${tasks.get(taskId)?.status}`);
		return { taskId };
	}

	tasks.set(taskId, { status: 'pending', step: 'Initializing', progress: 0 });

	// Start background process
	(async () => {
		try {
			console.log(`Background task ${taskId} started${customUrl ? ' with custom URL' : ''}`);
			const downloadResult = await handleDownload(artist, title, taskId, customUrl);
			if (downloadResult.error) throw new Error(downloadResult.error);

			console.log(`Download for ${taskId} finished, starting separation`);
			const separateResult = await handleSeparate(downloadResult.path, taskId);
			if (separateResult.error) throw new Error(separateResult.error);

			console.log(`Separation for ${taskId} finished`);
			tasks.set(taskId, { 
				status: 'completed', 
				step: 'Finished', 
				progress: 100, 
				resultUrl: separateResult.url 
			});
		} catch (err: any) {
			console.error(`Task ${taskId} failed:`, err);
			tasks.set(taskId, { status: 'failed', step: 'Error', progress: 0, error: err.message });
		}
	})();

	return { taskId };
}
async function runYtDlp(query: string, outputDir: string, slug: string, taskId: string, provider = 'ytsearch'): Promise<{ success: boolean; details?: string }> {
	return new Promise((resolve) => {
		console.log(`[yt-dlp] Starting ${provider} for query: "${query}"`);
		
		const isDirectUrl = query.startsWith('http');
		const target = isDirectUrl ? query : `${provider}1:${query}`;

		const ytDlpArgs = [
			'-x', '--audio-format', 'mp3',
			'--audio-quality', '0',
			'--print', 'title,uploader,duration,webpage_url',
			'--no-playlist',
			'-o', path.join(outputDir, `${slug}.%(ext)s`),
			target
		];

		// Exclude live and karaoke from searches (but not direct URLs)
		if (!isDirectUrl) {
			ytDlpArgs.splice(-1, 0, '--match-filter', 'title !~* "live" & title !~* "karaoke"');
		}

		const ytDlp = spawn('yt-dlp', ytDlpArgs);
		
		let stderr = '';
		let metadataLogged = false;

		ytDlp.stdout.on('data', (d) => {
			const output = d.toString();
			
			// Log metadata if we haven't yet (yt-dlp prints it first due to --print)
			if (!metadataLogged && output.includes('http')) {
				console.log(`[yt-dlp] Grabbed video: ${output.trim().replace(/\n/g, ' | ')}`);
				metadataLogged = true;
			}

			const match = output.match(/\[download\]\s+(\d+\.\d+)%/);
			if (match) {
				const progress = parseFloat(match[1]);
				tasks.set(taskId, { status: 'processing', step: 'Downloading', progress });
			}
		});
		ytDlp.stderr.on('data', (d) => stderr += d.toString());
		
		ytDlp.on('close', async (code) => {
			console.log(`[yt-dlp] exited with code ${code} for query: ${query}`);
			if (code !== 0) {
				resolve({ success: false, details: stderr });
				return;
			}
			resolve({ success: true });
		});
		
		ytDlp.on('error', (err) => {
			console.error('[yt-dlp] Failed to start:', err);
			resolve({ success: false, details: err.message });
		});
	});
}

async function handleDownload(artist: string, title: string, taskId: string, customUrl?: string): Promise<any> {
	const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const outputDir = path.join(DATA_DIR, 'audio', slug);
	const finalPath = path.join(outputDir, `${slug}.mp3`);
	
	if (!customUrl && await fileExists(finalPath)) {
		tasks.set(taskId, { status: 'processing', step: 'Download (Cached)', progress: 100 });
		return { status: 'cached', path: finalPath, url: `/api/audio/audio/${slug}/${slug}.mp3` };
	}
	
	await mkdir(outputDir, { recursive: true });

	if (customUrl) {
		tasks.set(taskId, { status: 'processing', step: 'Downloading custom URL...', progress: 0, stepSource: 'Manual URL' });
		const attempt = await runYtDlp(customUrl, outputDir, slug, taskId);
		if (attempt.success && await fileExists(finalPath)) {
			return { status: 'downloaded', path: finalPath };
		}
		return { error: 'Custom URL download failed', details: attempt.details };
	}
	
	// Attempt 1: General YouTube search with "(Official Audio)" suffix - often more reliable than YT Music search
	tasks.set(taskId, { status: 'processing', step: 'Searching YouTube...', progress: 0, stepSource: 'YouTube' });
	const query1 = `${artist} ${title} (Official Audio)`;
	const attempt1 = await runYtDlp(query1, outputDir, slug, taskId, 'ytsearch');
	
	if (attempt1.success && await fileExists(finalPath)) {
		return { status: 'downloaded', path: finalPath };
	}
	
	console.log(`[api] Primary search failed for "${query1}", falling back to YT Music...`);
	tasks.set(taskId, { status: 'processing', step: 'Falling back to YT Music...', progress: 0, stepSource: 'YouTube Music' });
	
	// Attempt 2: YouTube Music search
	const query2 = `${artist} ${title}`;
	const attempt2 = await runYtDlp(query2, outputDir, slug, taskId, 'https://music.youtube.com/search?q=');
	
	if (attempt2.success && await fileExists(finalPath)) {
		return { status: 'downloaded', path: finalPath };
	}
	
	return { error: 'Download failed', details: attempt2.details || attempt1.details };
}

async function handleSeparate(audioPath: string, taskId: string): Promise<any> {
	const basename = path.basename(audioPath, path.extname(audioPath));
	const outputDir = path.join(DATA_DIR, 'separated');
	const instrumentalPath = path.join(outputDir, 'htdemucs', basename, 'no_vocals.mp3');
	
	if (await fileExists(instrumentalPath)) {
		tasks.set(taskId, { status: 'processing', step: 'Separation (Cached)', progress: 100 });
		return { 
			status: 'cached', 
			instrumentalPath,
			url: `/api/audio/separated/htdemucs/${basename}/no_vocals.mp3`
		};
	}
	
	tasks.set(taskId, { status: 'processing', step: 'Separating (Demucs)', progress: 0 });

	return new Promise((resolve) => {
		const demucs = spawn('demucs', [
			'--two-stems', 'vocals',
			'-d', 'cuda',
			'--mp3',
			'-n', 'htdemucs',
			'--out', outputDir,
			audioPath
		]);
		
		let stderr = '';
		demucs.stdout.on('data', (d) => {
			const line = d.toString();
			console.log(`[demucs stdout] ${line.trim()}`);
			// Demucs progress bar look: 10%|███       | 10/100
			const match = line.match(/(\d+)%/);
			if (match) {
				const progress = parseInt(match[1], 10);
				tasks.set(taskId, { status: 'processing', step: 'Separating', progress });
			}
		});
		demucs.stderr.on('data', (d) => {
			const line = d.toString();
			console.log(`[demucs stderr] ${line.trim()}`);
			stderr += line;
			// Demucs often writes progress to stderr
			const match = line.match(/(\d+)%/);
			if (match) {
				const progress = parseInt(match[1], 10);
				tasks.set(taskId, { status: 'processing', step: 'Separating', progress });
			}
		});
		
		demucs.on('close', async (code) => {
			console.log(`demucs exited with code ${code}`);
			if (code !== 0) {
				resolve({ error: 'Separation failed', details: stderr });
				return;
			}
			
			resolve({ 
				status: 'separated',
				instrumentalPath,
				url: `/api/audio/separated/htdemucs/${basename}/no_vocals.mp3`
			});
		});

		demucs.on('error', (err) => {
			console.error('Failed to start demucs:', err);
			resolve({ error: 'Failed to start demucs', details: err.message });
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
			console.log(`[${new Date().toISOString()}] ${req.method} ${url.pathname}${url.search}`);
			
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
				const { artist, title, youtubeUrl } = body as { artist: string; title: string; youtubeUrl?: string };
				const result = await handlePrepare(artist, title, youtubeUrl);
				return new Response(JSON.stringify(result), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname.startsWith('/api/tasks/')) {
				const taskId = decodeURIComponent(url.pathname.replace('/api/tasks/', ''));
				console.log(`Polling task: "${taskId}"`);
				const task = tasks.get(taskId);
				if (!task) {
					console.log(`Task not found for ID: "${taskId}". Available tasks: ${Array.from(tasks.keys()).join(', ')}`);
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