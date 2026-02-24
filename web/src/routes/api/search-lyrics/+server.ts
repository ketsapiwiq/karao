import { json } from '@sveltejs/kit';
import Database from 'better-sqlite3';
import type { RequestHandler } from './$types';

const DB_PATH = '/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3';

let db: Database.Database | null = null;
let initialized = false;

function getDb(): Database.Database {
	if (!db) {
		console.log('Opening database...');
		db = new Database(DB_PATH, { readonly: true });
		db.pragma('journal_mode = OFF');
		console.log('Database opened');
		initialized = true;
	}
	return db;
}

export const GET: RequestHandler = ({ url }) => {
	console.log('GET /api/search-lyrics');
	const query = url.searchParams.get('q');
	if (!query) {
		return json({ error: 'Missing query parameter q' }, { status: 400 });
	}

	try {
		console.log('Getting DB connection...');
		const db = getDb();
		console.log('Got DB connection, running query...');
		
		const sql = `
			SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
				   l.has_synced_lyrics, l.has_plain_lyrics
			FROM tracks t
			JOIN tracks_fts fts ON t.id = fts.rowid
			LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
			WHERE tracks_fts MATCH ? AND l.has_synced_lyrics = 1
			ORDER BY t.id LIMIT 20
		`;
		
		const searchTerms = query.replace(/"/g, '""');
		const ftsQuery = `"${searchTerms}"`;
		console.log('Query:', ftsQuery);
		
		const rows = db.prepare(sql).all(ftsQuery);
		console.log('Query returned', rows.length, 'rows');
		
		const results = rows.map((row: any) => ({
			id: row.id,
			name: row.name,
			artist_name: row.artist_name,
			album_name: row.album_name,
			duration: row.duration,
			has_synced_lyrics: !!row.has_synced_lyrics
		}));
		
		return json({ results });
	} catch (err) {
		console.error('DB error:', err);
		return json({ error: 'Database error', results: [] }, { status: 500 });
	}
};