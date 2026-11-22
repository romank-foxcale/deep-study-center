You break one formula into its building blocks for Deep Study Center. To understand a formula, a learner must first hold every block it is built from: the notations it uses and the simpler formulas and ideas it comes from. The app teaches missing blocks first, then builds the formula up from them.

{rules}

The formula: {title}
Its form: ${main}$
What it says: {meaning}

The learner's formula lessons (id: name. Forms):
{known}

Ideas in the learner's knowledge graph around it (id: title (what the learner knows)):
{ideas}

List the 2-6 blocks this formula is DIRECTLY built from, one level down (not the whole tree: each block gets its own blocks later), from the most basic to the most specific:
- `kind`: `notation` for a way of writing (a product sign $\prod$, a sum $\sum$, the bar in $\Pr(y \mid x)$, index subscripts, the $\operatorname{argmin}$ operator, a vector or matrix notation); `formula` for a simpler formula or rule it uses or is derived from (for example $\Pr(A, B) = \Pr(A)\Pr(B)$ for independent events, $\log(ab) = \log a + \log b$); `idea` for a concept without one formula (independence, a probability distribution).
- `name`: the block's usual name, 2-6 words ("Product notation", "Independent events multiply", "Conditional probability").
- `tex`: the block in its standard general form ("" for an idea without one), with general letters, not this formula's letters.
- `meaning`: one sentence in plain, general words. No words from a book's example (no "molecule", no "review"): the block must make sense on its own.
- `ref`: the id of the learner's formula lesson or graph idea that IS this block (same thing, any notation), else "".
- `basic`: true only for school arithmetic every adult reader knows (adding, subtracting, multiplying or dividing two numbers, a fraction, a power, parentheses); such blocks need no lesson. A notation ($\prod$, $\sum$, the bar in $\Pr(A \mid B)$, subscripts, $\operatorname{argmin}$) is NEVER basic: the learner may never have read it.
Do not list the formula itself, and do not list a block that only appears inside another listed block.
Return JSON matching the schema.
