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

async function handleSearch(q: string): Promise<any[]> {
	const searchTerms = q.replace(/"/g, '""');
	const ftsQuery = `"${searchTerms}"`;
	
	const sql = `
		SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
			   l.has_synced_lyrics, l.has_plain_lyrics
		FROM tracks t
		JOIN tracks_fts fts ON t.id = fts.rowid
		LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
		WHERE tracks_fts MATCH ? AND l.has_synced_lyrics = 1
		ORDER BY t.id LIMIT 20
	`;
	
	return db.query(sql).all(ftsQuery) as any[];
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

async function handleDownload(artist: string, title: string): Promise<any> {
	const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const outputDir = path.join(DATA_DIR, 'audio', slug);
	const finalPath = path.join(outputDir, `${slug}.mp3`);
	
	if (await fileExists(finalPath)) {
		return { status: 'cached', path: finalPath, url: `/api/audio/audio/${slug}/${slug}.mp3` };
	}
	
	await mkdir(outputDir, { recursive: true });
	
	return new Promise((resolve) => {
		const ytDlp = spawn('yt-dlp', [
			'-x', '--audio-format', 'mp3',
			'--audio-quality', '0',
			'-o', path.join(outputDir, '%(title)s.%(ext)s'),
			`ytsearch1:${artist} ${title}`
		]);
		
		let stderr = '';
		ytDlp.stderr.on('data', (d) => stderr += d.toString());
		
		ytDlp.on('close', async (code) => {
			if (code !== 0) {
				resolve({ error: 'Download failed', details: stderr });
				return;
			}
			
			const fs = await import('fs');
			const files = fs.readdirSync(outputDir);
			const mp3File = files.find(f => f.endsWith('.mp3'));
			const actualPath = mp3File ? path.join(outputDir, mp3File) : finalPath;
			
			resolve({ 
				status: 'downloaded',
				path: actualPath,
				url: `/api/audio/audio/${slug}/${mp3File || slug + '.mp3'}`
			});
		});
	});
}

async function handleSeparate(audioPath: string): Promise<any> {
	const basename = path.basename(audioPath, path.extname(audioPath));
	const outputDir = path.join(DATA_DIR, 'separated');
	const instrumentalPath = path.join(outputDir, 'htdemucs', basename, 'no_vocals.wav');
	
	if (await fileExists(instrumentalPath)) {
		return { 
			status: 'cached', 
			instrumentalPath,
			url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav`
		};
	}
	
	return new Promise((resolve) => {
		const demucs = spawn('demucs', [
			'--two-stems', 'vocals',
			'-d', 'cpu',
			'--float32',
			'-n', 'htdemucs',
			'--out', outputDir,
			audioPath
		]);
		
		let stderr = '';
		demucs.stderr.on('data', (d) => stderr += d.toString());
		
		demucs.on('close', async (code) => {
			if (code !== 0) {
				resolve({ error: 'Separation failed', details: stderr });
				return;
			}
			
			resolve({ 
				status: 'separated',
				instrumentalPath,
				url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav`
			});
		});
	});
}

async function handleAudio(filePath: string, req: Request): Promise<Response> {
	const fullPath = path.join(DATA_DIR, filePath);
	
	try {
		const stats = await stat(fullPath);
		if (!stats.isFile()) {
			return new Response('Not found', { status: 404 });
		}
	} catch {
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
			if (url.pathname === '/api/search-lyrics') {
				const q = url.searchParams.get('q');
				if (!q) {
					return new Response(JSON.stringify({ error: 'Missing q parameter' }), { 
						status: 400, 
						headers: { ...corsHeaders, 'Content-Type': 'application/json' }
					});
				}
				const results = await handleSearch(q);
				return new Response(JSON.stringify({ results }), { 
					headers: { ...corsHeaders, 'Content-Type': 'application/json' }
				});
			}
			else if (url.pathname === '/api/lyrics') {
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