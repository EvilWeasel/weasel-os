// Usage: node tests/test-chatgpt-startup.cjs /nix/store/...-chatgpt-VERSION
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

async function main() {
  const packagePath = process.argv[2];
  assert(packagePath, 'Pass the built ChatGPT package path');
  const modules = path.join(packagePath, 'lib/chatgpt/resources/app.asar.unpacked/node_modules');
  const watcherRoot = path.join(modules, '@parcel/watcher');
  const libcRoot = path.join(watcherRoot, 'node_modules/detect-libc/lib');
  const filesystem = require(path.join(libcRoot, 'filesystem.js'));
  const originalRead = filesystem.readFileSync;
  const originalReport = process.report.getReport;

  // Reproduce the failed ELF interpreter probe after autoPatchelf relocates
  // PT_INTERP beyond detect-libc's small read buffer. The filesystem fallback
  // must identify glibc without entering Electron's crashing report API.
  filesystem.readFileSync = (file) => {
    if (file === filesystem.SELF_PATH) throw new Error('ELF probe unavailable');
    return originalRead(file);
  };
  process.report.getReport = () => {
    throw new Error('Unsafe Electron worker report fallback was invoked');
  };
  try {
    assert(filesystem.LDD_PATH.startsWith('/nix/store/'));
    assert.match(fs.readFileSync(filesystem.LDD_PATH, 'utf8'), /GNU C Library/);
    assert.equal(require(path.join(libcRoot, 'detect-libc.js')).familySync(), 'glibc');
  } finally {
    filesystem.readFileSync = originalRead;
    process.report.getReport = originalReport;
  }

  // Exercise the packaged native binding, not only the JavaScript selector.
  const watcher = require(watcherRoot);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'chatgpt-watcher-test-'));
  let subscription;
  let timer;
  try {
    let onEvent;
    const observed = new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new Error('No native file event within 10 seconds')), 10000);
      onEvent = (error, events) => {
        if (error) reject(error);
        if (events.some((event) => event.path === path.join(directory, 'probe'))) resolve();
      };
    });
    subscription = await watcher.subscribe(directory, onEvent);
    fs.writeFileSync(path.join(directory, 'probe'), 'startup regression probe\n');
    await observed;
  } finally {
    clearTimeout(timer);
    if (subscription) await subscription.unsubscribe();
    fs.rmSync(directory, { recursive: true, force: true });
  }
  console.log('PASS: glibc fallback avoids process.report and native file watching works');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
