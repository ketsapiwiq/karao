const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const DB_PATH = '/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3';
const OUTPUT_DIR = '/tmp/karaokeke';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

console.log('Loading DB...');
const db = new Database(DB_PATH, { readonly: true });

const searchStmt = db.prepare(`
	SELECT t.id, t.name, t.artist_name, t.duration 
	FROM tracks t 
	JOIN tracks_fts fts ON t.id = fts.rowid 
	WHERE tracks_fts MATCH ? 
	LIMIT 10
`);

const lyricsStmt = db.prepare(`
	SELECT l.synced_lyrics, l.plain_lyrics 
	FROM lyrics l 
	WHERE l.track_id = ? AND l.has_synced_lyrics = 1 
	LIMIT 1
`);

console.log('DB loaded');

const server = http.createServer(async (req, res) => {
	console.log('Request:', req.url);
	res.setHeader('Access-Control-Allow-Origin', '*');
	res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
	res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
	
	if (req.method === 'OPTIONS') {
		res.writeHead(200);
		res.end();
		return;
	}

	const url = new URL(req.url, 'http://localhost');
	
	if (url.pathname === '/search' && req.method === 'GET') {
		const q = url.searchParams.get('q') || '';
		console.log('Query:', q);
		const words = q.trim().split(/\s+/).filter(w => w.length > 0);
		if (words.length === 0) {
			res.writeHead(200, {'Content-Type': 'application/json'});
			res.end(JSON.stringify({results: []}));
			return;
		}
		const ftsQuery = words.map(w => `"${w.replace(/"/g, '""')}"*`).join(' AND ');
		console.log('FTS Query:', ftsQuery);
		const rows = searchStmt.all(ftsQuery);
		console.log('Found:', rows.length);
		res.writeHead(200, {'Content-Type': 'application/json'});
		res.end(JSON.stringify({results: rows}));
	}
	else if (url.pathname.startsWith('/lyrics/') && req.method === 'GET') {
		const trackId = url.pathname.split('/')[2];
		console.log('Lyrics for track:', trackId);
		const row = lyricsStmt.get(parseInt(trackId));
		if (row) {
			res.writeHead(200, {'Content-Type': 'application/json'});
			res.end(JSON.stringify({synced_lyrics: row.synced_lyrics, plain_lyrics: row.plain_lyrics}));
		} else {
			res.writeHead(404, {'Content-Type': 'application/json'});
			res.end(JSON.stringify({error: 'No synced lyrics found'}));
		}
	}
	else if (url.pathname === '/download' && req.method === 'POST') {
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const { artist, title } = JSON.parse(body);
				const searchQuery = `${artist} ${title} audio`;
				const outputFile = path.join(OUTPUT_DIR, `${artist.replace(/[^a-z0-9]/gi, '_')}_${title.replace(/[^a-z0-9]/gi, '_')}.mp3`);
				
				console.log('Downloading:', searchQuery);
				
				const ytdlp = spawn('/home/hadrien/.local/bin/yt-dlp', [
					'-x', '--audio-format', 'mp3',
					'-o', outputFile,
					`ytsearch:${searchQuery}`
				]);
				
				let stderr = '';
				ytdlp.stderr.on('data', data => stderr += data);
				
				ytdlp.on('close', code => {
					if (code === 0 && fs.existsSync(outputFile)) {
						console.log('Downloaded:', outputFile);
						res.writeHead(200, {'Content-Type': 'application/json'});
						res.end(JSON.stringify({path: outputFile}));
					} else {
						console.error('Download failed:', stderr);
						res.writeHead(500, {'Content-Type': 'application/json'});
						res.end(JSON.stringify({error: 'Download failed', details: stderr}));
					}
				});
			} catch (e) {
				console.error(e);
				res.writeHead(400, {'Content-Type': 'application/json'});
				res.end(JSON.stringify({error: e.message}));
			}
		});
	}
	else if (url.pathname === '/separate' && req.method === 'POST') {
		let body = '';
		req.on('data', chunk => body += chunk);
		req.on('end', async () => {
			try {
				const { audioPath } = JSON.parse(body);
				
				if (!fs.existsSync(audioPath)) {
					res.writeHead(400, {'Content-Type': 'application/json'});
					res.end(JSON.stringify({error: 'Audio file not found'}));
					return;
				}
				
				console.log('Separating:', audioPath);
				
				const inputBaseName = path.basename(audioPath);
				const docker = spawn('docker', [
					'run', '--rm', '--user', 'root',
					'-e', 'HOME=/root',
					'-e', 'TORCH_HUB_DIR=/root/.cache',
					'-v', `${OUTPUT_DIR}:/output`,
					'-v', `${audioPath}:/output/${inputBaseName}:ro`,
					'-v', '/tmp/demucs-cache:/root/.cache',
					'rakuri255/ultrasinger:latest',
					'demucs', '-n', 'htdemucs', '-o', '/output', `/output/${inputBaseName}`
				]);
				
				let stderr = '';
				docker.stderr.on('data', data => stderr += data);
				
				docker.on('close', code => {
					const baseName = path.basename(audioPath, '.mp3');
					const separatedDir = path.join(OUTPUT_DIR, 'htdemucs');
					
					let instrumentalPath = path.join(separatedDir, baseName.replace(/\.mp3$/i, ''), 'no_vocals.wav');
					
					if (!fs.existsSync(instrumentalPath)) {
						instrumentalPath = path.join(separatedDir, baseName.replace(/\.mp3$/i, ''), 'vocals.wav');
					}
					
					if (code === 0 && fs.existsSync(instrumentalPath)) {
						console.log('Separated:', instrumentalPath);
						res.writeHead(200, {'Content-Type': 'application/json'});
						const urlPath = path.join('htdemucs', path.basename(path.dirname(instrumentalPath)), path.basename(instrumentalPath));
						res.end(JSON.stringify({url: `/audio/${urlPath}`}));
					} else {
						console.error('Separation failed:', stderr);
						res.writeHead(500, {'Content-Type': 'application/json'});
						res.end(JSON.stringify({error: 'Separation failed', details: stderr}));
					}
				});
			} catch (e) {
				console.error(e);
				res.writeHead(400, {'Content-Type': 'application/json'});
				res.end(JSON.stringify({error: e.message}));
			}
		});
	}
	else if (url.pathname.startsWith('/audio/')) {
		const audioPath = path.join(OUTPUT_DIR, url.pathname.replace('/audio/', ''));
		if (fs.existsSync(audioPath)) {
			const stat = fs.statSync(audioPath);
			res.writeHead(200, {
				'Content-Type': 'audio/wav',
				'Content-Length': stat.size
			});
			fs.createReadStream(audioPath).pipe(res);
		} else {
			res.writeHead(404);
			res.end('Not found');
		}
	}
	else if (url.pathname === '/health') {
		res.writeHead(200, {'Content-Type': 'text/plain'});
		res.end('OK');
	}
	else {
		res.writeHead(404, {'Content-Type': 'application/json'});
		res.end(JSON.stringify({error: 'Not found'}));
	}
});

server.listen(3017, '0.0.0.0', () => {
	console.log('Server listening on port 3017');
});
