You write one learner's personal version of a lesson ("rendition") from a canonical concept card.

{rules}

<card>
{card}
</card>

<learner>
Goal: {goal}
Profile: {profile}
Teaching playbook (what works for this person):
{playbook}
Style knobs (-3..+3): pace {pace} (negative = smaller steps, more worked examples), depth {depth} (negative = essentials only), rigor {rigor} (positive = formal statements and proofs earlier).
</learner>

Write the prose for these sections, each through the given teaching angle:
{sections}

Angles: geometric = pictures, arrows, spatial intuition; algebraic = definitions, symbols, rules; computational = code (Python/NumPy), data, how it shows up in ML practice.
Rules:
- Use the card as the source of truth; do not contradict it or add claims it does not support.
- Pick examples from the learner's world (see playbook example domains).
- Each section 80-220 words unless the style knobs say otherwise. Do not repeat the section heading. Do not include the check question or exercise; they are shown separately.
Return JSON matching the schema: one entry per requested section id.
