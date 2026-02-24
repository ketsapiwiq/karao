import { stat, readFile } from 'fs/promises';
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import path from 'path';
import { Readable } from 'stream';

const DATA_DIR = '/data';

export const GET: RequestHandler = async ({ params, request }) => {
	const filePath = path.join(DATA_DIR, params.path);
	
	try {
		const stats = await stat(filePath);
		if (!stats.isFile()) {
			throw error(404, 'Not found');
		}
	} catch {
		throw error(404, 'Not found');
	}
	
	const fileBuffer = await readFile(filePath);
	const range = request.headers.get('range');
	const fileSize = fileBuffer.length;
	
	if (range) {
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
				'Content-Type': filePath.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg'
			}
		});
	}
	
	return new Response(fileBuffer, {
		headers: {
			'Content-Length': fileSize.toString(),
			'Content-Type': filePath.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg'
		}
	});
};