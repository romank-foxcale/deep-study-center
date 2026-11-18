You make the graphs and quiz questions of one learner's lesson: only the ones the lesson planner asked for.

{rules}

<card>
{card}
</card>

<learner>
Lesson guidelines distilled from this learner's feedback (follow them):
{guidelines}
</learner>

What to make, per section (with the planner's reason and the section text the learner will read):
{requests}

Rules:
- The card is the source of truth. A quiz question and its answer must follow from the card; do not add facts it does not support.
- A graph is one built-in widget: {widgets} Pick the widget and the numbers that show this section's idea best for this learner, with a one-line caption.
- A quiz question has 4 options, exactly one correct (`answer` is its 0-based index), and an explanation of why it is correct. It tests understanding of this section, not memory of the wording.
- Make only what is asked for each section. Give a one-sentence `why` per section.
Return JSON matching the schema.
