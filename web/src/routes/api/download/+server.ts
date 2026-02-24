import { json, error } from '@sveltejs/kit';
import { spawn } from 'child_process';
import { mkdir, access } from 'fs/promises';
import path from 'path';
import type { RequestHandler } from './$types';

const OUTPUT_DIR = '/data/audio';

async function fileExists(p: string): Promise<boolean> {
	try {
		await access(p);
		return true;
	} catch {
		return false;
	}
}

export const POST: RequestHandler = async ({ request }) => {
	const { artist, title } = await request.json();
	
	if (!artist || !title) {
		throw error(400, 'Missing artist or title');
	}
	
	const slug = `${artist} - ${title}`.replace(/[^a-zA-Z0-9 \-]/g, '');
	const outputTemplate = path.join(OUTPUT_DIR, slug, '%(title)s.%(ext)s');
	const finalPath = path.join(OUTPUT_DIR, slug, `${slug}.mp3`);
	
	if (await fileExists(finalPath)) {
		return json({ 
			status: 'cached', 
			path: finalPath,
			url: `/api/audio/${slug}/${slug}.mp3`
		});
	}
	
	await mkdir(path.join(OUTPUT_DIR, slug), { recursive: true });
	
	return new Promise((resolve) => {
		const ytDlp = spawn('yt-dlp', [
			'-x', '--audio-format', 'mp3',
			'--audio-quality', '0',
			'-o', outputTemplate,
			`ytsearch1:${artist} ${title}`
		]);
		
		let stderr = '';
		ytDlp.stderr.on('data', (d) => stderr += d.toString());
		
		ytDlp.on('close', async (code) => {
			if (code !== 0) {
				resolve(json({ error: 'Download failed', details: stderr }, { status: 500 }));
				return;
			}
			
			resolve(json({ 
				status: 'downloaded',
				path: finalPath,
				url: `/api/audio/${slug}/${slug}.mp3`
			}));
		});
	});
};