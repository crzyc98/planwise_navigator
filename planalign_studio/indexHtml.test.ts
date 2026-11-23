import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const EXTERNAL_URL_RE = /https?:\/\/[^\s"'<>)]+/gi;
const XMLNS_ATTR_RE = /\bxmlns(?::[a-z0-9_-]+)?\s*=\s*(?:"https?:\/\/[^"]*"|'https?:\/\/[^']*')/gi;

function findExternalAssetUrls(html: string): string[] {
  // Ignore XML namespace URIs (e.g. xmlns="http://www.w3.org/2000/svg") inside inline SVGs.
  const withoutXmlns = html.replace(XMLNS_ATTR_RE, '');
  return withoutXmlns.match(EXTERNAL_URL_RE) ?? [];
}

describe('index.html offline asset guard', () => {
  it('references no external http(s) assets', () => {
    const htmlPath = fileURLToPath(new URL('./index.html', import.meta.url));
    const html = readFileSync(htmlPath, 'utf8');

    expect(findExternalAssetUrls(html)).toEqual([]);
  });

  it('detects external scripts, stylesheets, fonts, images, and preconnects while ignoring SVG xmlns', () => {
    const sample = `
      <link rel="preconnect" href="https://fonts.gstatic.com" />
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto" />
      <script src="http://cdn.example.com/app.js"></script>
      <img src="https://example.com/logo.png" />
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"></svg>
    `;

    expect(findExternalAssetUrls(sample)).toEqual([
      'https://fonts.gstatic.com',
      'https://fonts.googleapis.com/css2?family=Roboto',
      'http://cdn.example.com/app.js',
      'https://example.com/logo.png',
    ]);
  });
});
