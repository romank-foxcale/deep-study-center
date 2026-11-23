You sort formulas into fields of mathematics for the learner's knowledge map in Deep Study Center.

{rules}

The fields (id: name):
{fields}

The formulas (number. name: TeX):
{formulas}

For each formula, by its number, give `fields`: the ids of the fields where this formula is commonly used, the most important first. Give 1 field for most formulas, 2 or 3 when the formula really belongs to several fields (Bayes' rule: probability, ml), and 4 only for a formula used across most of mathematics (the rules of logarithms). Judge the formula itself, not the lesson it came from: a loss function is `ml`, a probability rule is `probability` even inside a machine learning book, a gradient step is `calculus`.
Return JSON matching the schema.
