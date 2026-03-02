import type { PageLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageLoad = async ({ fetch, params }) => {
  const { id } = params;
  
  const res = await fetch(`/api/lyrics?id=${id}`);
  if (!res.ok) {
    throw error(404, 'Track not found');
  }
  
  const track = await res.json();
  return { track };
};
