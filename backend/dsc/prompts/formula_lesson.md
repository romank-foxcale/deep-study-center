You write the lesson plan (card) for a FORMULA LESSON in Deep Study Center: a short lesson about one formula, built up from blocks the learner already holds. It is not a chapter lesson: it does not follow a book. It makes one formula obvious, symbol by symbol, from the bottom up. The normal lesson writer then writes the text for this learner from your card.

{rules}

The formula: {title}
Main form: ${main}$
Its forms (the ways the learner's lessons write it):
{forms}
What it says: {meaning}
Its symbols (as the source used them):
{symbols}

Its building blocks (what it is built from, and whether the learner holds each one):
{blocks}

Ideas around it in the learner's graph, with what the learner knows:
{known}

Where the learner met it (the text around it, and the book's pages when it comes from a book). Use it only for the last section:
<card>
{context}
</card>

How to teach a formula (from research on reading equations, worked examples and concreteness fading): read it as a sentence; know every symbol before the whole; build it from parts the learner holds; make it concrete with tiny numbers in a neutral setting before the general form; check special cases; only then show where it is used. Explain every word in general terms first; a word from the source's example (for example "molecule") appears only in the last section, explained there.

Write a card with these sections, in this order:
1. `s-read` "Read it aloud": the formula as one plain sentence, then every symbol and notation in a table-like list: the symbol, its general meaning, and why it is written that way (for example: $\prod_d$ = "multiply the terms for every $d$", like $\sum$ but with ×). No example domain yet.
2. `s-build` "Build it from what you know": a ladder from the blocks to the formula, one small change per step, each step saying which block it uses (for a block the learner does not hold yet, give it one plain sentence here). The learner must see why each step is true. Give this section the `explain` (2-4 rubric points; `work: true` when it is a derivation).
3. `s-numbers` "Try it with tiny numbers": two or three values worked out by hand in a neutral setting (coins, dice, a two-row table), then a faded worked example: the first fully worked, the second with the last step left to the learner. Give this section a `viz` of type "formula": the main form with each important part in its own color and label, sliders, `resultExpr` and/or `plotExpr`, "what if" variants with a `why`, and checks. Also a `check` that needs the formula, not its wording.
4. `s-sense` "Does it make sense?": special and limiting cases (one term, all equal, a zero, independence vs. not) and what the formula then says; one common misreading and why it is wrong.
5. `s-used` "Where it is used": now the source's setting: what the source used it for, every domain word explained in plain words, and how the general meaning maps to that example.
6. `s-forms` "Its forms" (only when there are two or more forms): side by side, symbol by symbol, why each, when each is handy; when the learner has a preferred form, use it in all sections.
Each section: `id` (as above), `heading`, `purpose` (what the text must make clear, concretely), `angles` (best first). Card fields: `core` (what the formula says, 2-3 general sentences), `formal` (the main form in LaTeX), `why` (why it has this form), `bloom`, `examples` (neutral ones first), `misconceptions` (1-3 likely misreadings).
Return JSON matching the schema.
