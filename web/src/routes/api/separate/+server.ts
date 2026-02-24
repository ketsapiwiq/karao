import { json, error } from '@sveltejs/kit';
import { spawn } from 'child_process';
import { access } from 'fs/promises';
import path from 'path';
import type { RequestHandler } from './$types';

const OUTPUT_DIR = '/data/audio';
const SEPARATED_DIR = '/data/separated';

async function fileExists(p: string): Promise<boolean> {
	try {
		await access(p);
		return true;
	} catch {
		return false;
	}
}

export const POST: RequestHandler = async ({ request }) => {
	const { audioPath } = await request.json();
	
	if (!audioPath) {
		throw error(400, 'Missing audioPath');
	}
	
	const basename = path.basename(audioPath, path.extname(audioPath));
	const instrumentalPath = path.join(SEPARATED_DIR, 'htdemucs', basename, 'no_vocals.wav');
	
	if (await fileExists(instrumentalPath)) {
		return json({ 
			status: 'cached', 
			instrumentalPath,
			url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav`
		});
	}
	
	return new Promise((resolve) => {
		const demucs = spawn('demucs', [
			'--two-stems', 'vocals',
			'-d', 'cpu',
			'--float32',
			'-n', 'htdemucs',
			'--out', SEPARATED_DIR,
			audioPath
		]);
		
		let stderr = '';
		demucs.stderr.on('data', (d) => stderr += d.toString());
		
		demucs.on('close', async (code) => {
			if (code !== 0) {
				resolve(json({ error: 'Separation failed', details: stderr }, { status: 500 }));
				return;
			}
			
			resolve(json({ 
				status: 'separated',
				instrumentalPath,
				url: `/api/audio/separated/htdemucs/${basename}/no_vocals.wav`
			}));
		});
	});
};