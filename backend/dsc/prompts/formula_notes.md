You write short notes for the formulas of one lesson in Deep Study Center. A learner hovers a formula and sees your note: what the formula is, what each symbol means, and where in their knowledge graph they met it.

{rules}

Lesson: {lesson}

The lesson's text (for context; the formulas appear in it):
<card>
{text}
</card>

The formulas to explain (number. TeX):
{formulas}

Ideas in the learner's knowledge graph (id: title). These are this lesson's own idea, the ideas it builds on or leads to, and ideas from other books and goals:
{ideas}

The learner's formula lessons (id: name. Forms):
{known}

For each formula, by its number, write:
- `name`: what the formula is called or does, 2-8 words ("Binary cross-entropy loss", "Gradient descent update", "Chain rule for one weight"). For a step in a derivation, say which step ("Log of a product becomes a sum").
- `meaning`: 1-2 sentences: first what it says in general, plain words (a reader who never saw the lesson's example must understand it), then, after "Here:", what it means in this lesson's example. Never use a word from the example (for example "molecule") without saying what it is.
- `symbols`: each symbol a learner must know to read it, with `tex` (the symbol as TeX, e.g. "\\lambda", "y_i", "\\nabla L") and `meaning` (a few words, in this lesson's sense). Skip plain numbers and standard functions (log, exp, sin) unless the lesson gives them a special sense.
- `kind`: `idea` when the formula states something worth knowing on its own (a definition, a law, a loss, an update rule, a result); `step` when it is an intermediate line of a derivation or a calculation with numbers.
- `formula`: when this formula is the same formula as one of the learner's formula lessons below, in this form or in another form (other letters, another notation, the same thing rearranged), that lesson's id; else "".
- `ideas`: 0-3 ids from the list above that this formula is, uses or comes from (for example the formula of softmax inside a cross-entropy loss gives the softmax idea). Only ids from the list. Put the most direct one first.

Never refer to a formula by its number in this list (the learner does not see the numbers); name it instead.
Return JSON matching the schema, one entry per formula number.
