You build the formula flow of one formula page in Deep Study Center. The flow shows where every part of the formula comes from, as boxes connected by arrows, from the inputs at the top to the formula itself and what it gives. The learner drags any input, and every box below shows its new value. A click on a box shows your explanation of it.

{rules}

The formula: {formula}
Its main form: ${main}$
What it says: {meaning}
Its symbols:
{symbols}
What it is built from (its building blocks):
{blocks}

Your earlier flow (fix it; "(none ...)" for a first version):
{previous}
Problems the code found in it (fix every one):
{problems}

Return:
- `inputs`: the values the learner can drag. Each: `id` (a short lowercase name of letters and digits, not a function name such as exp or log, and not `e`, `pi` or `x`), `sym` (its TeX symbol), `label` (at most 6 words), `value` (a good start value), `min`, `max`, `step`. A constant the learner should not change (for example a tiny ε) has `"fixed": true`. Choose ranges where every box can be computed (no log of 0, no division by 0).
- `nodes`, in order, top to bottom:
  1. **Input boxes** first: each holds related inputs (`input`: their ids). Each input is in exactly one input box. Give `id`, `label` (for example "the scores"), `tex` (the inputs as the reader sees them, naming each input as `{id}`, for example `z = ({z1},\, {z2},\, {z3})`, or just `{y},\; {lam}`; never `y = {y}`, which reads "y = y") and `say`.
  2. **Formula boxes**: each defines ONE quantity from inputs and earlier boxes. Give `id`, `sym` (its short TeX name: one letter, maybe with a subscript or a hat, for example `q`, `p_i`, `\hat m`; never the formula itself: when the book has no name for the quantity, give it one), `label` (at most 6 words: what it is), `uses` (the ids of the boxes it is computed from: input boxes or formula boxes above it), `tex` (its formula in TeX; write every input and every box it uses as `{id}`, and itself as `{its id}` on the left, for example `{s} = \textstyle\sum_j {e}_j`), `expr` (the calculator form, below) and `say`.
  3. The last boxes are the formula of the page itself and what it gives (for example the loss it feeds). Keep it small: the boxes a careful teacher would draw, at most 14.
- `expr`: numbers, input ids, earlier box ids, + - * / ^, parentheses, and the functions sin cos tan exp log sqrt abs tanh sigmoid relu max min. Lowercase only. A box can be a small vector: then `expr` is a list (at most 6 parts), and later boxes use its parts as `id_1`, `id_2`, ... (for example `e_1/s`). There is no sum function: write `e_1 + e_2 + e_3`.
- `say`: two to four plain sentences: what the box is, why the formula needs this step, and what happens to it when an input changes. Name inputs and boxes by their symbols in `$...$`.
- `whatif` (on the 1-3 boxes where the form is a real choice: a function, a constant, a normalizer, a sign): 1-3 other forms of the box, each with `tex` (the changed formula), `expr` (same shape as the box's), `why` (one or two sentences: what changes and why the real form is right, or why the other form also works) and `ok` (true when the formula still does its job). These let the learner change one part and see every box below change.

An example, for "time for 100 km at a given speed":
{"inputs": [{"id": "d", "sym": "d", "label": "distance, km", "value": 120, "min": 1, "max": 500, "step": 1},
            {"id": "t", "sym": "t", "label": "time, h", "value": 1.5, "min": 0.1, "max": 10, "step": 0.1}],
 "nodes": [{"id": "trip", "label": "the trip", "input": ["d", "t"], "tex": "{d} \\text{ km in } {t} \\text{ h}", "say": "What you measured: how far ($d$) and how long ($t$)."},
           {"id": "v", "sym": "v", "label": "speed, km/h", "uses": ["trip"], "tex": "{v} = \\dfrac{{d}}{{t}}", "expr": "d/t",
            "say": "The distance in one hour. Twice the time for the same distance gives half the speed.",
            "whatif": [{"tex": "{v} = {d} \\cdot {t}", "expr": "d*t", "why": "A longer time would then mean a higher speed: the unit is km·h, not km/h.", "ok": false}]},
           {"id": "h", "sym": "t_{100}", "label": "hours for 100 km", "uses": ["v"], "tex": "{h} = \\dfrac{100}{{v}}", "expr": "100/v",
            "say": "The time for 100 km at speed $v$. Double the speed gives half the time."}]}

Return JSON matching the schema.
