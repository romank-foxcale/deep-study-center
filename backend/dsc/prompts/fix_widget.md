You fix one interactive widget of a lesson. The app computed it the way the page will, and found problems.

{rules}

<card>
{card}
</card>

Section: "{section}" ({purpose}).

The widget as written:
{widget}

Problems the app found (each one is real; the app removed what could not work):
{problems}

Widget rules: {widgets}

Return the corrected widget: the same idea and the same parts where they work, with every problem fixed. Keep every fact consistent with the card. A check with `expect` must pass for the real formula at the start values. Every value the learner can set must be the `param` of a part that shows it. A result may use only values the learner sets.
Return JSON matching the schema.
