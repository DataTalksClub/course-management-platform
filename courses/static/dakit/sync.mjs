#!/usr/bin/env node
// Zero-dependency vendoring and local drift verification.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const usage = 'Usage: node sync.mjs --dest <dir> [--files <dist names...>] [--fonts-dir <relative dir>] [--check]';
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
function safePath(root, name) {
  if (typeof name !== 'string' || !name || isAbsolute(name) || name.includes('\\')) throw new Error(`Invalid relative path: ${name}`);
  const path = resolve(root, name);
  const rel = relative(root, path);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) throw new Error(`Path escapes destination: ${name}`);
  // Existing symlinks must not redirect writes/checks outside the vendored tree.
  for (let current = path; current !== root; current = dirname(current)) {
    if (existsSync(current)) {
      const real = relative(realpathSync(root), realpathSync(current));
      if (real === '..' || real.startsWith(`..${sep}`) || isAbsolute(real)) throw new Error(`Symlink escapes destination: ${name}`);
    }
  }
  return path;
}
function parse(args) {
  const opts = { files: [], fontsDir: 'fonts', check: false };
  for (let i = 0; i < args.length; i++) {
    const flag = args[i];
    if (flag === '--check') opts.check = true;
    else if (flag === '--help') { console.log(usage); process.exit(0); }
    else if (flag === '--files') {
      const start = opts.files.length;
      while (args[i + 1] && !args[i + 1].startsWith('--')) opts.files.push(...args[++i].split(','));
      if (opts.files.length === start) throw new Error('--files needs at least one dist filename');
    } else if (flag === '--dest' || flag === '--fonts-dir') {
      const value = args[++i];
      if (!value || value.startsWith('--')) throw new Error(`${flag} needs a value`);
      opts[flag === '--dest' ? 'dest' : 'fontsDir'] = value;
    } else throw new Error(`Unknown argument: ${flag}`);
  }
  if (!opts.dest) throw new Error('--dest is required');
  opts.dest = resolve(opts.dest);
  return opts;
}
function check(dest) {
  const lock = JSON.parse(readFileSync(join(dest, 'dakit.lock.json'), 'utf8'));
  if (typeof lock.version !== 'string' || typeof lock.commit !== 'string' || !lock.files || Array.isArray(lock.files) || typeof lock.files !== 'object' || !Object.keys(lock.files).length) throw new Error('Invalid dakit.lock.json');
  const drift = [];
  for (const [name, expected] of Object.entries(lock.files)) {
    if (!/^[a-f0-9]{64}$/.test(expected)) throw new Error(`Invalid checksum: ${name}`);
    const path = safePath(dest, name);
    if (!existsSync(path)) drift.push(`${name}: missing`);
    else if (hash(readFileSync(path)) !== expected) drift.push(`${name}: changed`);
  }
  if (drift.length) throw new Error(`Vendored dakit drift:\n${drift.join('\n')}`);
  console.log(`dakit ${lock.version} ${lock.commit}: ${Object.keys(lock.files).length} files match lock`);
}
function sync({ dest, files, fontsDir }) {
  const script = fileURLToPath(import.meta.url);
  const source = resolve(dirname(script), '..');
  if (!existsSync(join(source, 'build.mjs'))) throw new Error('Sync requires the dakit checkout; the vendored script supports --check');
  const dist = join(source, 'dist');
  const names = files.length ? [...new Set(files)] : readdirSync(dist).filter((name) => !name.startsWith('.'));
  // Read and validate all source bytes before writing any destination files.
  const output = new Map();
  let metadata;
  for (const name of names) {
    if (!/^[a-zA-Z0-9._-]+$/.test(name)) throw new Error(`Use a dist filename, not a path: ${name}`);
    let bytes = readFileSync(join(dist, name));
    const stamp = bytes.toString().match(/^\/\* dakit (\S+) ([a-f0-9]+) \*\//);
    if (!stamp) throw new Error(`Missing build stamp in ${name}; run node build.mjs`);
    const current = { version: stamp[1], commit: stamp[2] };
    if (metadata && (metadata.version !== current.version || metadata.commit !== current.commit)) throw new Error('Mixed dist revisions; run node build.mjs');
    metadata = current;
    if (name.endsWith('.css')) bytes = Buffer.from(bytes.toString().replaceAll('../fonts/', `./${fontsDir}/`));
    output.set(name, bytes);
  }
  if (!/^[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(fontsDir)) throw new Error('--fonts-dir must be a relative directory within --dest');
  for (const name of readdirSync(join(source, 'fonts'))) output.set(`${fontsDir}/${name}`, readFileSync(join(source, 'fonts', name)));
  output.set('check-borders.mjs', readFileSync(join(source, 'scripts/check-borders.mjs')));
  output.set('check-colors.mjs', readFileSync(join(source, 'scripts/check-colors.mjs')));
  output.set('check-scale.mjs', readFileSync(join(source, 'scripts/check-scale.mjs')));
  output.set('sync.mjs', readFileSync(script));
  if (dest === source || dest === dist || relative(source, dest).startsWith(`fonts${sep}`) || dest === join(source, 'fonts')) throw new Error('Destination must not overwrite dakit sources or dist');
  mkdirSync(dest, { recursive: true });
  for (const name of output.keys()) safePath(dest, name);
  const sums = {};
  for (const [name, bytes] of output) {
    const path = safePath(dest, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, bytes);
    sums[name] = hash(bytes);
  }
  writeFileSync(safePath(dest, 'dakit.lock.json'), JSON.stringify({ ...metadata, files: sums }, null, 2) + '\n');
  console.log(`Synced dakit ${metadata.version} ${metadata.commit} to ${dest}`);
}
try {
  const opts = parse(process.argv.slice(2));
  if (opts.check) check(opts.dest);
  else sync(opts);
} catch (error) {
  console.error(`${error.message}\n${usage}`);
  process.exitCode = 1;
}
