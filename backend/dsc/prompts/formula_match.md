You match formulas from one lesson to the learner's formula lessons in Deep Study Center.

{rules}

The lesson's formulas (number. name: TeX):
{formulas}

The learner's formula lessons (id: name. Forms):
{known}

For each formula, by its number, give `kind`: `idea` when it states something worth knowing on its own (a definition, a law, a loss, an update rule, a result), `step` when it is an intermediate line of a derivation or a calculation with numbers; and `formula`: the id of the formula lesson about the same formula (in this form or in another form: other letters, another notation, the same thing rearranged, a special case written out), or "" when none is the same formula. Do not match a formula that only uses another one (a loss that contains softmax is not the softmax formula).
Return JSON matching the schema.
