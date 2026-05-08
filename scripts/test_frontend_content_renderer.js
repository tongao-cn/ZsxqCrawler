const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const frontendRoot = path.join(repoRoot, 'frontend');
const sourceFile = path.join(frontendRoot, 'src', 'lib', 'zsxq-content-renderer.ts');
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zsxq-renderer-test-'));

try {
  execFileSync(
    process.execPath,
    [
      path.join(frontendRoot, 'node_modules', 'typescript', 'bin', 'tsc'),
      sourceFile,
      '--outDir',
      outDir,
      '--module',
      'commonjs',
      '--target',
      'es2020',
      '--esModuleInterop',
      '--skipLibCheck',
    ],
    { cwd: frontendRoot, stdio: 'inherit' }
  );

  const purifyStub = path.join(outDir, 'node_modules', 'dompurify');
  fs.mkdirSync(purifyStub, { recursive: true });
  fs.writeFileSync(
    path.join(purifyStub, 'index.js'),
    `
const allowedTags = new Set(['a', 'br', 'del', 'em', 'img', 'mark', 'path', 'span', 'strong', 'svg', 'u']);
const allowedAttrs = new Set(['alt', 'class', 'd', 'fill', 'height', 'href', 'rel', 'src', 'stroke', 'stroke-linecap', 'stroke-linejoin', 'stroke-width', 'style', 'target', 'viewBox', 'width']);
function sanitize(html) {
  return html
    .replace(/<\\/?([a-zA-Z0-9-]+)(\\s[^>]*)?>/g, (match, tag, attrs = '') => {
      const lowerTag = tag.toLowerCase();
      if (!allowedTags.has(lowerTag)) return '';
      if (match.startsWith('</')) return \`</\${lowerTag}>\`;
      const safeAttrs = [];
      attrs.replace(/\\s([\\w:-]+)="([^"]*)"/g, (_attrMatch, name, value) => {
        if (allowedAttrs.has(name)) safeAttrs.push(\`\${name}="\${value}"\`);
        return '';
      });
      return \`<\${lowerTag}\${safeAttrs.length ? ' ' + safeAttrs.join(' ') : ''}>\`;
    });
}
module.exports = { sanitize, default: { sanitize } };
`,
    'utf8'
  );

  const renderer = require(path.join(outDir, 'zsxq-content-renderer.js'));

  const escaped = renderer.createSafeHtml('<img src=x onerror=alert(1)>hello<script>alert(1)</script>').__html;
  assert(escaped.includes('&lt;img'), 'raw img payload should be escaped');
  assert(!escaped.includes('<img'), 'raw img tag should not be rendered');
  assert(!escaped.includes('<script'), 'script tag should not be rendered');

  const unsafeHref = renderer.createSafeHtml(
    '<e type="web_url" href="javascript%3Aalert(1)" title="%E6%81%B6%E6%84%8F" />'
  ).__html;
  assert(unsafeHref.includes('恶意'), 'unsafe link title should remain visible');
  assert(!unsafeHref.includes('javascript'), 'javascript href should be dropped');
  assert(!unsafeHref.includes('href='), 'unsafe href attribute should not be emitted');

  const zsxqTags = renderer.renderZsxqContent(
    '<e type="hashtag" hid="abc" title="%23A%E8%82%A1%23" /><e type="mention" uid="u1" title="%40%E5%B0%8F%E6%98%8E" />'
  );
  assert(zsxqTags.includes('https://wx.zsxq.com/tags'), 'hashtag link should be preserved');
  assert(zsxqTags.includes('#A股'), 'hashtag title should be decoded');
  assert(zsxqTags.includes('@小明'), 'mention title should be decoded');

  const highlightedText = renderer.createSafeHtmlWithHighlight(
    '<e type="web_url" href="https%3A%2F%2Fexample.com%2Ffoo" title="Example%20Link" />',
    'Example'
  ).__html;
  assert(highlightedText.includes('href="https://example.com/foo"'), 'safe href should survive highlighting');
  assert(highlightedText.includes('<mark'), 'visible matching text should be highlighted');
  assert(!highlightedText.includes('href="<mark'), 'highlight should not be injected inside href');

  const highlightedAttr = renderer.createSafeHtmlWithHighlight(
    '<e type="web_url" href="https%3A%2F%2Fexample.com%2Ffoo" title="Example%20Link" />',
    'http'
  ).__html;
  assert(highlightedAttr.includes('href="https://example.com/foo"'), 'safe href should remain intact');
  assert(!highlightedAttr.includes('<mark'), 'attribute-only matches should not be highlighted');

  console.log('frontend content renderer checks passed');
} finally {
  fs.rmSync(outDir, { recursive: true, force: true });
}
