import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const outdir = path.join(root, 'dist');
await mkdir(outdir, { recursive: true });
const result = await build({
  absWorkingDir: root,
  entryPoints: ['app.js', 'styles.css', 'locations.css'],
  entryNames: '[name]-[hash]',
  bundle: true,
  minify: true,
  target: ['es2022'],
  outdir,
  metafile: true,
  legalComments: 'eof',
  charset: 'utf8',
});
let html = await readFile(path.join(root, 'index.html'), 'utf8');
const manifest = {};
for (const [output, metadata] of Object.entries(result.metafile.outputs)) {
  if (!metadata.entryPoint) continue;
  const input = path.basename(metadata.entryPoint);
  const filename = path.basename(output);
  html = html.replace(`/static/${input}`, `/static/${filename}`);
  manifest[input] = { file: filename, bytes: metadata.bytes };
}
if (!manifest['app.js'] || !manifest['styles.css'] || !manifest['locations.css']) throw new Error('Missing built entry points');
// Write the entry document last, so it never references a partially written build.
await writeFile(path.join(outdir, 'manifest.json'), JSON.stringify(manifest, null, 2));
await writeFile(path.join(outdir, 'index.html'), html);
console.log('Production frontend ready:', manifest);
