You write a placement diagnostic for Deep Study Center: one quick question per module, to find where a learner should start.

{rules}

<learner>
Goal: {goal}
Profile: {profile}
</learner>

Modules (id: title - summary):
{modules}

For each module write one multiple-choice question that someone who has genuinely mastered the module answers quickly (under 2 minutes), and someone who hasn't cannot guess: test application, not vocabulary. 4 options, one correct, plausible distractors based on real misconceptions. The UI adds an "I don't know" option itself; don't include one.
Return JSON with one item per module id.
