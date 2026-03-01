import { test, expect } from '@playwright/test';

test.describe('Karaokeke', () => {
    test('should search and select a track', async ({ page }) => {
        await page.goto('http://localhost:3010');
        
        // Debugging
        console.log('Page URL:', page.url());
        const content = await page.content();
        console.log('Page content length:', content.length);
        await page.screenshot({ path: 'test-results/screenshot.png' });
        
        // Check title
        await expect(page.locator('h1')).toHaveText('Karaokeke');
        
        // Search
        const searchInput = page.locator('input[placeholder="Search for a song..."]');
        await searchInput.fill('Bashung');
        await page.keyboard.press('Enter');
        
        // Wait for results
        const results = page.locator('ul.results li');
        await expect(results).not.toHaveCount(0, { timeout: 60000 });
        
        // Select first track
        await results.first().click();
        
        // Check selection
        await expect(page.locator('.selected h2')).toContainText('Bashung');
        await expect(page.locator('.lyrics-preview')).toBeVisible();
        
        const startButton = page.locator('.actions button', { hasText: 'Start Karaoke' });
        await expect(startButton).toBeEnabled();
        
        // Start Karaoke
        await startButton.click();
        
        // Wait for preparation and player (this might take a while if downloading/separating)
        // Since we tested 'Bashung' which is likely cached or already prepared in my prev curls
        await expect(page.locator('button.back')).toBeVisible({ timeout: 60000 });
        await expect(page.locator('audio')).toBeVisible();
    });
});