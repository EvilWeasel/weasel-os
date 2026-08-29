import { readFileSync, writeFileSync } from "node:fs";

const [target] = process.argv.slice(2);

if (!target) {
    throw new Error("usage: patch-vesktop-wayland-capture.mjs <compiled-main.js>");
}

const source = readFileSync(target, "utf8");
const brokenWaylandHandler =
    'if(vy){let c=i[0];if(c&&await it("screenshare:picker",{screens:[c],skipPicker:!0}).catch(()=>null)===null)return t({});t(c?{video:n[0]}:{});return}';
const directWaylandCapture = 'if(vy){let c=i[0];t(c?{video:n[0]}:{});return}';
const matches = source.split(brokenWaylandHandler).length - 1;

if (matches !== 1) {
    throw new Error(`expected exactly one Vesktop 1.6.7 Wayland capture handler, found ${matches}`);
}

writeFileSync(target, source.replace(brokenWaylandHandler, directWaylandCapture));
