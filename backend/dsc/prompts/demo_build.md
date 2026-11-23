You build ONE small interactive demo for a lesson step in Deep Study Center: a single self-contained HTML file. The learner operates it to see an idea move: they drag a slider, press a button, or drag a point, and watch what changes.

{rules}

The step: {step}
The step's text (the demo sits under it):
{text}

The brief (what the demo must show; it is your whole specification):
{brief}

The previous version, if you are fixing one:
<previous>
{previous}
</previous>
Problems found in it (fix every one; "(none)" for a first build):
{errors}

Rules for the HTML (it is checked by code and run in a locked sandbox; a demo that breaks a rule is rejected):
- One file: inline `<style>` and inline `<script>` only. No outside files, no `<link>`, no `<script src>`, no web addresses (only the SVG namespace `http://www.w3.org/2000/svg` is allowed), no fonts from the web. It must work offline.
- No network (no fetch, XMLHttpRequest, WebSocket), no storage (no localStorage, cookies), no eval or new Function, no alert/confirm/prompt, no iframes, no access to `window.parent` or `top`.
- Plain JavaScript (no libraries). Draw with `<canvas>` or inline SVG. Keep it under 150 kB.
- At least one control: `<input type="range">` with a visible label and its current value, a `<button>`, a `<select>`, or a point to drag. Every control must work at its minimum and its maximum value without errors: guard against division by zero, `NaN` and empty arrays.
- Show the numbers that matter next to the picture, so the learner can connect the picture to the step's formulas. Use the step's notation in labels.
- Layout: width 100% of its frame (it is about 600-700 px wide), height at most about 420 px, readable on a dark background (`#0b0f17`) with light text (`#e6eaf2`); muted text `#8b95aa`; accent `#8fb3ff`. Draw again when the frame is resized.
- No headings, no long text in the demo: at most one short line of instruction. The step's text explains; the demo shows.
- It must start in a state that already shows something useful, without a click.

Return JSON: `title` (2-5 words), `html` (the whole file, starting with `<!doctype html>`), `watch` (one short sentence for the learner: what to move and what to watch).
