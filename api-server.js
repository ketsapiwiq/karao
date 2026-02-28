const http = require('http');
const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.env.PORT || '3001', 10);
const DATA_DIR = process.env.DATA_DIR || '/data';
const DB_PATH = process.env.LRCLIB_DB || '/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3';

if (!isMainThread) {
	const Database = require('better-sqlite3');
	const db = new Database(DB_PATH, { readonly: true });
	db.pragma('journal_mode = OFF');
	
	const searchStmt = db.prepare(`
		SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
			   l.has_synced_lyrics, l.has_plain_lyrics
		FROM tracks t
		JOIN tracks_fts fts ON t.id = fts.rowid
		LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
		WHERE tracks_fts MATCH ? AND l.has_synced_lyrics = 1
		ORDER BY t.id LIMIT 20
	`);
	
	const lyricsStmt = db.prepare(`
		SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
			   l.synced_lyrics, l.plain_lyrics
		FROM tracks t
		LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
		WHERE t.id = ?
	`);
	
	parentPort.on('message', (msg) => {
		if (msg.type === 'search') {
			const searchTerms = msg.q.replace(/"/g, '""');
			const results = searchStmt.all(`"${searchTerms}"`);
			parentPort.postMessage({ id: msg.id, results });
		} else if (msg.type === 'lyrics') {
			const row = lyricsStmt.get(msg.id);
			parentPort.postMessage({ id: msg.id, row });
		}
	});
	
	parentPort.postMessage({ type: 'ready' });
} else {
	console.log('Starting worker...');
	const worker = new Worker(__filename);
	let ready = false;
	const pendingRequests = new Map();
	let requestId = 0;
	
	worker.on('message', (msg) => {
		if (msg.type === 'ready') {
			ready = true;
			console.log('Worker ready');
			console.log(`Server listening on port ${PORT}`);
		} else if (msg.id !== undefined) {
			const resolver = pendingRequests.get(msg.id);
			if (resolver) {
				pendingRequests.delete(msg.id);
				resolver(msg);
			}
		}
	});
	
	function search(q) {
		return new Promise((resolve) => {
			const id = ++requestId;
			pendingRequests.set(id, resolve);
			worker.postMessage({ type: 'search', q, id });
		});
	}
	
	function getLyrics(id) {
		return new Promise((resolve) => {
			const rid = ++requestId;
			pendingRequests.set(rid, resolve);
			worker.postMessage({ type: 'lyrics', id, id: rid });
		});
	}
	
	const server = http.createServer(async (req, res) => {
		console.log('Request:', req.method, req.url);
		
		res.setHeader('Access-Control-Allow-Origin', '*');
		res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
		res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
		
		if (req.method === 'OPTIONS') {
			res.writeHead(204);
			res.end();
			return;
		}
		
		const url = new URL(req.url, `http://localhost:${PORT}`);
		
		if (url.pathname === '/api/search-lyrics' && req.method === 'GET') {
			const q = url.searchParams.get('q') || '';
			console.log('Search:', q);
			const { results } = await search(q);
			console.log('Found:', results.length);
			res.writeHead(200, { 'Content-Type': 'application/json' });
			res.end(JSON.stringify({ results }));
			return;
		}
		
		if (url.pathname === '/api/lyrics' && req.method === 'GET') {
			const id = parseInt(url.searchParams.get('id') || '0', 10);
			console.log('Lyrics:', id);
			const { row } = await getLyrics(id);
			if (!row) {
				res.writeHead(404, { 'Content-Type': 'application/json' });
				res.end(JSON.stringify({ error: 'Not found' }));
				return;
			}
			res.writeHead(200, { 'Content-Type': 'application/json' });
			res.end(JSON.stringify(row));
			return;
		}
		
		if (url.pathname === '/api/download' && req.method === 'POST') {
			let body = '';
			req.on('data', chunk => body += chunk);
			req.on('end', () => {
				const { artist, title } = JSON.parse(body);
				console.log('Download:', artist, title);
				const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
				const outputDir = path.join(DATA_DIR, 'audio', slug);
				const finalPath = path.join(outputDir, `${slug}.mp3`);
				
				if (fs.existsSync(finalPath)) {
					res.writeHead(200, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ status: 'cached', path: finalPath, url: `/api/audio/audio/${slug}/${slug}.mp3` }));
					return;
				}
				
				fs.mkdirSync(outputDir, { recursive: true });
				
				const ytDlp = spawn('yt-dlp', [
					'-x', '--audio-format', 'mp3', '--audio-quality', '0',
					'-o', path.join(outputDir, '%(title)s.%(ext)s'),
					`ytsearch1:${artist} ${title}`
				]);
				
				ytDlp.on('close', (code) => {
					if (code !== 0) {
						res.writeHead(500, { 'Content-Type': 'application/json' });
						res.end(JSON.stringify({ error: 'Download failed' }));
						return;
					}
					const files = fs.readdirSync(outputDir);
					const mp3File = files.find(f => f.endsWith('.mp3'));
					res.writeHead(200, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ status: 'downloaded', path: path.join(outputDir, mp3File), url: `/api/audio/audio/${slug}/${mp3File}` }));
				});
			});
			return;
		}
		
		if (url.pathname === '/api/separate' && req.method === 'POST') {
			let body = '';
			req.on('data', chunk => body += chunk);
			req.on('end', () => {
				const { audioPath } = JSON.parse(body);
				console.log('Separate:', audioPath);
				const basename = path.basename(audioPath, path.extname(audioPath));
				const outputDir = path.join(DATA_DIR, 'separated');
				const instrumentalPath = path.join(outputDir, 'htdemucs', basename, 'no_vocals.wav');
				
				if (fs.existsSync(instrumentalPath)) {
					res.writeHead(200, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ status: 'cached', url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav` }));
					return;
				}
				
				const demucs = spawn('demucs', [
					'--two-stems', 'vocals', '-d', 'cpu', '--float32', '-n', 'htdemucs',
					'--out', outputDir, audioPath
				]);
				
				demucs.on('close', (code) => {
					if (code !== 0) {
						res.writeHead(500, { 'Content-Type': 'application/json' });
						res.end(JSON.stringify({ error: 'Separation failed' }));
						return;
					}
					res.writeHead(200, { 'Content-Type': 'application/json' });
					res.end(JSON.stringify({ status: 'separated', url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav` }));
				});
			});
			return;
		}
		
		if (url.pathname.startsWith('/api/audio/')) {
			const filePath = url.pathname.replace('/api/audio/', '');
			const fullPath = path.join(DATA_DIR, filePath);
			console.log('Audio:', fullPath);
			
			if (!fs.existsSync(fullPath)) {
				res.writeHead(404);
				res.end('Not found');
				return;
			}
			
			const stat = fs.statSync(fullPath);
			const contentType = fullPath.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg';
			
			res.writeHead(200, {
				'Content-Type': contentType,
				'Content-Length': stat.size
			});
			fs.createReadStream(fullPath).pipe(res);
			return;
		}
		
		res.writeHead(404, { 'Content-Type': 'application/json' });
		res.end(JSON.stringify({ error: 'Not found' }));
	});
	
	server.listen(PORT, '0.0.0.0');
}