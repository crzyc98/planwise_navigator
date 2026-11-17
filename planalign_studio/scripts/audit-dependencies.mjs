// Blocking npm audit gate with reviewed, expiring exceptions.
//
// Fails on any high or critical advisory except those listed in EXCEPTIONS.
// Every entry needs a matching row under "Approved Studio Dependency
// Exceptions" in SECURITY.md. An entry past its review date fails the gate,
// so exceptions can't go stale silently.
import { execFileSync } from 'node:child_process';

const EXCEPTIONS = {
  // picomatch ReDoS, no patched release. Build tooling only (vite, tinyglobby).
  'GHSA-fc5q-39xc-vjpf': '2026-12-15',
};

const BLOCKING = new Set(['high', 'critical']);
const today = new Date().toISOString().slice(0, 10);

let raw;
try {
  raw = execFileSync('npm', ['audit', '--json'], { encoding: 'utf8' });
} catch (error) {
  // npm audit exits non-zero when it finds anything; the JSON is still on stdout.
  raw = error.stdout;
  if (!raw) throw error;
}

const report = JSON.parse(raw);
if (!report.vulnerabilities) {
  // A failed audit (e.g. registry unreachable) has no report; never pass on it.
  console.error(`npm audit returned no report:\n${raw}`);
  process.exit(1);
}

const advisories = new Map();
for (const vuln of Object.values(report.vulnerabilities)) {
  for (const via of vuln.via) {
    if (typeof via === 'object' && BLOCKING.has(via.severity)) {
      advisories.set(via.url.split('/').pop(), `${via.name} (${via.severity}): ${via.title}`);
    }
  }
}

const failures = [];
for (const [id, summary] of advisories) {
  const reviewBy = EXCEPTIONS[id];
  if (!reviewBy) failures.push(`${id} ${summary}`);
  else if (reviewBy < today) failures.push(`${id} exception expired ${reviewBy}; re-review it in SECURITY.md`);
  else console.log(`Allowed until ${reviewBy}: ${id} ${summary}`);
}

if (failures.length > 0) {
  console.error(`Blocking npm advisories:\n  ${failures.join('\n  ')}`);
  process.exit(1);
}
console.log('npm audit: no unapproved high or critical advisories.');
