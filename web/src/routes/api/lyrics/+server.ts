import { json } from '@sveltejs/kit';
import Database from 'better-sqlite3';
import type { RequestHandler } from './$types';

const DB_PATH = '/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3';

let db: Database.Database | null = null;

function getDb(): Database.Database {
	if (!db) {
		db = new Database(DB_PATH, { readonly: true });
	}
	return db;
}

export const GET: RequestHandler = ({ url }) => {
	const trackId = url.searchParams.get('id');
	if (!trackId) {
		return json({ error: 'Missing id parameter' }, { status: 400 });
	}

	try {
		const db = getDb();
		
		const sql = `
			SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
				   l.synced_lyrics, l.plain_lyrics
			FROM tracks t
			LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
			WHERE t.id = ?
		`;
		
		const row = db.prepare(sql).get(parseInt(trackId, 10));
		
		if (!row) {
			return json({ error: 'Track not found' }, { status: 404 });
		}
		
		return json({
			id: (row as any).id,
			name: (row as any).name,
			artist_name: (row as any).artist_name,
			album_name: (row as any).album_name,
			duration: (row as any).duration,
			synced_lyrics: (row as any).synced_lyrics
		});
	} catch (err) {
		console.error('DB error:', err);
		return json({ error: 'Database error' }, { status: 500 });
	}
};