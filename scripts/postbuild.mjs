/**
 * Assemble the self-hosted standalone bundle.
 *
 * `next build` with output:"standalone" emits .next/standalone/server.js but
 * deliberately leaves out .next/static and public/, so they have to be copied
 * in by hand before the bundle can serve anything.
 *
 * This is a no-op when .next/standalone is absent, which is the case on Vercel
 * (it builds its own output format, so next.config.ts disables standalone
 * there). Previously this ran as `cp -r` chained into the build script, which
 * failed the whole build on Vercel because the target directory did not exist,
 * and on Windows because cmd.exe has no `cp`.
 */
import { cpSync, existsSync } from "node:fs";

const STANDALONE = ".next/standalone";

if (!existsSync(STANDALONE)) {
  console.log("postbuild: no .next/standalone, nothing to assemble");
  process.exit(0);
}

for (const [from, to] of [
  [".next/static", `${STANDALONE}/.next/static`],
  ["public", `${STANDALONE}/public`],
]) {
  if (!existsSync(from)) {
    console.log(`postbuild: ${from} missing, skipped`);
    continue;
  }
  cpSync(from, to, { recursive: true });
  console.log(`postbuild: ${from} -> ${to}`);
}
