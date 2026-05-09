const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const frontendRoot = path.join(repoRoot, 'frontend');
const sourceFile = path.join(frontendRoot, 'src', 'lib', 'api.ts');
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zsxq-api-client-test-'));

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

  const api = require(path.join(outDir, 'api.js'));

  assert.strictEqual(
    api.formatApiError(
      { detail: { message: '该群组已有采集或同步任务正在运行', task_id: 'task-1' } },
      'fallback'
    ),
    '该群组已有采集或同步任务正在运行'
  );
  assert.strictEqual(api.formatApiError({ detail: 'plain detail' }, 'fallback'), 'plain detail');
  assert.strictEqual(api.formatApiError({ message: 'top message' }, 'fallback'), 'top message');
  assert.strictEqual(api.formatApiError({}, 'fallback'), 'fallback');

  console.log('frontend api client checks passed');
} finally {
  fs.rmSync(outDir, { recursive: true, force: true });
}
