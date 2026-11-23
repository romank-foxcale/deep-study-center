You write the lesson plan (card) for a short NOTATION LESSON in Deep Study Center: one way of writing mathematics (for example $\prod$, $\sum$, $\Pr(y \mid x)$, index subscripts, $\operatorname{argmin}$), taught so the learner can read it anywhere. About 5 minutes. The normal lesson writer then writes the text from your card.

{rules}

The notation: {title}
Its general form: ${main}$
What it means: {meaning}

What it is built from:
{blocks}

Ideas around it in the learner's graph, with what the learner knows:
{known}

Where the learner met it (use only for the last section):
<card>
{context}
</card>

Write a card with 3 sections:
1. `s-read` "Read it": what each part of the notation means, said aloud as a sentence; why it is written this way; the plain long form it is short for (for example $\prod_{i=1}^{3} a_i = a_1 \cdot a_2 \cdot a_3$).
2. `s-numbers` "Try it": two tiny worked examples in a neutral setting, the second with the last step left to the learner. No multiple-choice `check` in a notation lesson (SPEC §40). Add a `viz` only when moving a value makes the notation clearer.
3. `s-used` "Where you will see it": the source's formula with this notation in it, read aloud piece by piece; every domain word explained in plain words. Give this section the `explain`: the learner writes a formula with this notation out in long form (`work: true`, 2-3 rubric points).
Each section: `id` (as above), `heading`, `purpose`, `angles`. Card fields: `core`, `formal` (the general form), `why`, `bloom` ("understand"), `examples`, `misconceptions` (1-2 misreadings).

A board task (`work: true`) is only for a calculation that is hard to do in the head: a matrix product, a derivative, an integral, a probability with numbers, an algebraic derivation of several steps. Its `prompt` must give everything the learner needs: the exact inputs (the numbers, the matrices, the function, the value of each symbol), what to compute, and the form of the answer (for example "Give p(y=1) with 2 decimals" or "Write L(w) for y=1 and for y=0"). A derivation states where it starts and where it must end. Never "derive X" with no start, and never a question that only asks for an opinion. For an explanation in words, set `work: false`.

Return JSON matching the schema.
