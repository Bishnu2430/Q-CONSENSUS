const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });

  await page.goto('http://localhost:8000', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.fill('#query', 'python?');
  await page.click('button:has-text("Async + Stream")');

  await page.waitForTimeout(40000);

  const stats = await page.evaluate(() => {
    const streamFooter = Array.from(document.querySelectorAll('div')).find(d => /events$/.test((d.textContent || '').trim()));
    const footerText = streamFooter?.textContent?.trim() || '';
    const match = footerText.match(/(\d+)\s*\/\s*(\d+)\s*events/i);
    const visible = match ? Number(match[1]) : -1;
    const total = match ? Number(match[2]) : -1;

    const hasNoResult = Array.from(document.querySelectorAll('p')).some(p => (p.textContent || '').includes('No result yet'));
    const finalSection = Array.from(document.querySelectorAll('section')).find(s => (s.textContent || '').includes('Final Reasoning'));
    const finalText = finalSection?.textContent || '';

    return {
      footerText,
      visible,
      total,
      hasNoResult,
      finalHasAnswer: finalText.includes('Final Answer') || finalText.length > 200,
    };
  });

  console.log('STATS=' + JSON.stringify(stats));
  console.log('ERRORS=' + errors.length);
  if (errors.length) console.log(errors.join('\n'));

  await browser.close();
  if (stats.total <= 1 || stats.hasNoResult) process.exit(2);
})();
