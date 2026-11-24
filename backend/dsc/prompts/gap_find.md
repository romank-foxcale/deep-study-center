You look for gaps in a learner's map of ideas in Deep Study Center. The map has one cell per idea. An arrow "A -> B" means the learner should hold A before B. A gap is a place where B really needs one to three ideas that are on no cell of the map: the step from A to B is too big without them.

{rules}

The ideas on the map (id: title — what it says), with the learner's state:
{ideas}

Arrows between ideas the learner has started or learned, and their neighbours (A -> B):
{arrows}

{focus}

Find at most {limit} gaps. For each gap:
- `between`: the two ids of the arrow, in its direction [A, B]. Use only ids from the list above.
- `ideas`: 1-3 missing ideas, in the order to learn them. Each idea: `title` (2-6 words) and `says` (one or two plain sentences: what it is and why the step from A to B needs it).

Rules:
- Only real gaps: an idea a careful teacher would add between A and B. Do not invent gaps to fill the number. Return an empty list when the map has none.
- Never propose an idea that is already on the map, even with another name or notation (for example "matmul" and "matrix multiplication" are the same idea).
- Prefer gaps next to ideas the learner has started or learned: that is where they study next.
- Each idea is one idea, small enough for one short lesson.

Return JSON matching the schema.
