Sort one piece of a learner's feedback on a lesson into one kind.

{rules}

Lesson: {concept}
Target: {target}
<feedback>
Tags: {tags}
Words: {text}
</feedback>

Kinds:
- "lesson": about this lesson only (this example, this section, this explanation). It changes only this lesson.
- "me": about how this person learns in general (pace, rigor, preferred angles, example domains, their background). It also changes their teaching playbook, so all lessons adapt.
- "fact": the learner says the material is wrong (a wrong formula, number, definition, claim or answer key). It goes to a fact check of the source card.

When unsure between "lesson" and "me", choose "lesson": a wrong "me" changes every lesson.
Return JSON matching the schema: the kind and a one-sentence reason.
