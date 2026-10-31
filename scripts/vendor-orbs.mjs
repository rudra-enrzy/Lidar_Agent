// Copies the framework-free part of thinking-orbs (its canvas engine) into lidar_agent/vendor so the app can load it
// with a plain <script type="module"> - no React, no bundler, works offline.
import { cpSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "thinking-orbs", "dist"), dst = join(root, "lidar_agent", "vendor", "thinking-orbs");
mkdirSync(dst, { recursive: true });
for (const f of readdirSync(src)) if (f === "engine.es.js" || /^index-.*\.js$/.test(f)) cpSync(join(src, f), join(dst, f));
cpSync(join(root, "node_modules", "thinking-orbs", "LICENSE"), join(dst, "LICENSE"));
console.log("thinking-orbs engine copied to", dst);
