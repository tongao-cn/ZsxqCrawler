const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const frontendRoot = path.join(repoRoot, 'frontend');
const sourceFile = path.join(frontendRoot, 'src', 'lib', 'group-workbench-read-model.ts');
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zsxq-group-workbench-model-test-'));

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

  const model = require(path.join(outDir, 'group-workbench-read-model.js'));

  assert.strictEqual(model.isRetryableLoadError('API返回空数据，可能是反爬虫机制'), true);
  assert.strictEqual(model.isRetryableLoadError('未找到指定的群组'), false);

  assert.deepStrictEqual(model.resolveGroupDetailRetry('空数据', 0), {
    shouldRetry: true,
    nextRetryCount: 1,
    delayMs: 1500,
    finalError: null,
  });
  assert.deepStrictEqual(model.resolveTopicsRetry('反爬虫', 5), {
    shouldRetry: false,
    nextRetryCount: 5,
    delayMs: 0,
    finalError: '反爬虫，自动重试已达上限',
  });
  assert.deepStrictEqual(model.normalizeGroupLocalFileStats({
    download_stats: {
      total_files: 4,
      downloaded: 2,
      pending: 1,
      failed: 1,
    },
  }), {
    total: 4,
    downloaded: 2,
    pending: 1,
    failed: 1,
  });
  assert.deepStrictEqual(model.normalizeGroupLocalFileStats(null), model.EMPTY_LOCAL_FILE_STATS);

  console.log('group workbench read model checks passed');
} finally {
  fs.rmSync(outDir, { recursive: true, force: true });
}
