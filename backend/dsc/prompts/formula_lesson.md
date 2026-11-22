You write the lesson plan (card) for a FORMULA LESSON in Deep Study Center: a short lesson about one formula that a learner met in another lesson and wants to understand fully. The normal lesson writer then writes the text for this learner from your card.

{rules}

The formula: {title}
Main form: ${main}$
Its forms (the ways the learner's lessons write it):
{forms}
What it says: {meaning}
Its symbols:
{symbols}

Ideas around it in the learner's graph, with what the learner knows (learned, mastered, learning, new):
{known}

Where the learner met it (the lesson text around it, and the book's pages when it comes from a book):
<card>
{context}
</card>

Write a card with 3-4 sections:
1. `s-parts` "What each part means": the formula part by part. This section MUST have a `viz` of type "formula": the main form with each important part in its own color and label, a slider for each parameter, `resultExpr` and/or `plotExpr`, "what if" variants for parts whose form is a choice (each with a `why` that says what breaks), and checks. This explorable formula is the heart of the lesson.
2. `s-origin` "Where it comes from": how the formula follows from ideas the learner already knows (use the list above; start from a learned idea when there is one). Show the derivation or the reasoning step by step, not only the result.
3. `s-use` "Use it": a worked example with small numbers, in the setting where the learner met it; give this section a `check` (a question that needs the formula, not its wording).
4. `s-forms` "Its forms" (only when there are two or more forms): put the forms side by side, map them symbol by symbol, say why each is written that way (the book's convention, a shortcut, a special case), and when each is handier. When the learner has a preferred form, say why it is a good choice and use it in the other sections too.
Give exactly one section an `explain` (usually `s-origin`): a question that asks the learner to explain or derive the formula in their own words, with a rubric of 2-4 points; set `work: true` when the answer is a calculation or a derivation.
Each section: `id` (as above), `heading`, `purpose` (what the text must make clear), `angles` (best first). Card fields: `core` (what the formula says, 2-3 sentences), `formal` (the main form in LaTeX), `why` (why it has this form), `bloom`, `examples`, `misconceptions` (1-3 likely mistakes when reading or using it).
Return JSON matching the schema.
