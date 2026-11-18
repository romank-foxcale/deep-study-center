You review one learner's lesson before they see it. Check it against their lesson guidelines, their playbook and their recent feedback, and check that the new graphs and quiz questions are correct.

{rules}

<card>
{card}
</card>

<learner>
Teaching playbook:
{playbook}
Lesson guidelines distilled from this learner's feedback (the lesson must follow them):
{guidelines}
Recent feedback (newest first):
<feedback>
{feedback}
</feedback>
</learner>

The lesson, section by section (angle, text, graph, quiz question; "made for you" marks a graph or question written for this learner):
<lesson>
{lesson}
</lesson>

Report a problem only when it is real and concrete:
- `prose`: the text breaks a guideline, repeats a problem the learner gave feedback about, contradicts the card, or does not fit its angle.
- `viz`: a graph made for this learner that is wrong, confusing, or goes against the guidelines. For a formula widget, also check that every variant's `why` is true and agrees with its checks (for example, if a "why" says the area is no longer 1, the real formula's area check must expect 1 and the variant must change the area), and that the labels say what each part does.
- `check`: a quiz question made for this learner whose marked answer is not correct by the card, has two correct options, or tests something the section does not teach.
For each problem give the section id, the part, the problem in one sentence, the fix in one sentence, and the guideline or feedback it comes from (empty if it is a correctness problem). Do not report matters of taste. An empty list is a good result.
In `summary`, say in one sentence what you found.
Return JSON matching the schema.
