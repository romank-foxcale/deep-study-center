// Mock data for the UI prototype. The "Vectors" lesson is real content so the
// adaptation loop (feedback -> playbook -> renditions) can be tried end to end.

import type {
  Concept, Goal, LessonSection, Module, Playbook, ProviderRoute, Rendition, RoadmapDiff,
  SourceCard, Track,
} from '../types'

export const goal: Goal = {
  id: 'g-ai',
  title: 'Become a world-class AI researcher & engineer',
  why: 'Understand modern AI deeply enough to build frontier-style models from scratch and contribute original research, at the level of people like Andrej Karpathy or DeepMind researchers.',
  doneLooksLike: 'Implement and train a GPT from scratch, reproduce a recent paper end to end, and publish one original result.',
  hoursPerWeek: 10,
  createdAt: '2026-10-14',
}

export const tracks: Track[] = [
  { id: 't-math', title: 'Mathematical foundations', summary: 'The language every later idea is written in.', moduleIds: ['m-la', 'm-calc', 'm-prob', 'm-opt', 'm-info'] },
  { id: 't-ml', title: 'Machine learning fundamentals', summary: 'Learning from data, generalization, the classical toolbox.', moduleIds: ['m-sup', 'm-gen', 'm-classic'] },
  { id: 't-dl', title: 'Deep learning', summary: 'Neural networks from scratch to transformers.', moduleIds: ['m-micrograd', 'm-train', 'm-cnn', 'm-attn', 'm-transformer'] },
  { id: 't-llm', title: 'Large language models', summary: 'Pretraining, scaling, post-training, inference, evals.', moduleIds: ['m-pretrain', 'm-scaling', 'm-post', 'm-infer', 'm-evals'] },
  { id: 't-research', title: 'Research practice', summary: 'Read, reproduce, experiment, write.', moduleIds: ['m-papers', 'm-repro', 'm-exp', 'm-writing'] },
]

const outline = (id: string, trackId: string, title: string, planned: number, research: Module['research'] = 'outline'): Module =>
  ({ id, trackId, title, research, conceptIds: [], plannedConcepts: planned })

export const modules: Module[] = [
  {
    id: 'm-la', trackId: 't-math', title: 'Linear algebra', research: 'ready',
    conceptIds: ['c-vectors', 'c-lincomb', 'c-span', 'c-dot', 'c-matrix-transform', 'c-matmul', 'c-det', 'c-inverse', 'c-eigen', 'c-svd'],
  },
  outline('m-calc', 't-math', 'Calculus for ML', 9, 'researching'),
  outline('m-prob', 't-math', 'Probability & statistics', 12),
  outline('m-opt', 't-math', 'Optimization', 8),
  outline('m-info', 't-math', 'Information theory', 5),
  outline('m-sup', 't-ml', 'Supervised learning', 10),
  outline('m-gen', 't-ml', 'Generalization & regularization', 7),
  outline('m-classic', 't-ml', 'Classical models', 8),
  outline('m-micrograd', 't-dl', 'Neural nets from scratch (autograd)', 9),
  outline('m-train', 't-dl', 'Training deep networks', 10),
  outline('m-cnn', 't-dl', 'Convolutional networks', 6),
  outline('m-attn', 't-dl', 'Sequence models & attention', 8),
  outline('m-transformer', 't-dl', 'Transformers', 10),
  outline('m-pretrain', 't-llm', 'Tokenization & pretraining', 8),
  outline('m-scaling', 't-llm', 'Scaling laws & compute', 5),
  outline('m-post', 't-llm', 'Post-training: SFT, RLHF, DPO', 9),
  outline('m-infer', 't-llm', 'Inference & efficiency', 7),
  outline('m-evals', 't-llm', 'Evals & agents', 7),
  outline('m-papers', 't-research', 'Reading papers', 5),
  outline('m-repro', 't-research', 'Reproducing results', 6),
  outline('m-exp', 't-research', 'Experiment design', 6),
  outline('m-writing', 't-research', 'Writing & communicating', 4),
]

const c = (id: string, title: string, objective: string, minutes: number, prereqs: string[],
  state: Concept['state'] = 'locked', mastery = 0.1): Concept =>
  ({ id, moduleId: 'm-la', title, objective, minutes, prereqs, state, mastery })

export const concepts: Concept[] = [
  c('c-vectors', 'Vectors', 'Represent data as vectors; add, scale and measure them.', 25, [], 'learning', 0.42),
  c('c-lincomb', 'Linear combinations', 'Build new vectors from weighted sums of others.', 20, ['c-vectors'], 'ready', 0.1),
  c('c-span', 'Span, basis & dimension', 'Decide what a set of vectors can reach and how many you need.', 30, ['c-lincomb']),
  c('c-dot', 'Dot product & similarity', 'Compute dot products and read them as similarity and projection.', 25, ['c-vectors']),
  c('c-matrix-transform', 'Matrices as transformations', 'Read a matrix as a function that moves space.', 30, ['c-span']),
  c('c-matmul', 'Matrix multiplication', 'Compose transformations; compute products by hand and with NumPy.', 30, ['c-matrix-transform', 'c-dot']),
  c('c-det', 'Determinant', 'Interpret the determinant as signed volume scaling.', 20, ['c-matrix-transform']),
  c('c-inverse', 'Inverses & linear systems', 'Solve Ax = b and know when no unique solution exists.', 30, ['c-det', 'c-matmul']),
  c('c-eigen', 'Eigenvectors & eigenvalues', 'Find the directions a transformation only stretches.', 35, ['c-inverse']),
  c('c-svd', 'Singular value decomposition', 'Factor any matrix into rotate-stretch-rotate and use it for compression.', 40, ['c-eigen']),
]

export const cards: SourceCard[] = [
  {
    conceptId: 'c-vectors',
    version: 2,
    factCheck: 'passed',
    checkedAt: '2026-10-14',
    objective: 'Represent data as vectors; add, scale and measure them.',
    bloom: 'apply',
    core: 'A vector is an ordered list of numbers that can be added and scaled. Geometrically it is an arrow from the origin; in ML it is how every piece of data is stored.',
    formal: 'A vector in $\\mathbb{R}^n$ is $v = (v_1, \\dots, v_n)$. Addition and scaling are componentwise: $(u+v)_i = u_i + v_i$, $(cv)_i = c\\,v_i$. Length: $\\lVert v \\rVert = \\sqrt{\\sum_i v_i^2}$.',
    why: 'Componentwise rules are exactly what makes "tip-to-tail" geometry work: moving along x and moving along y are independent, so the steps add separately. The length formula is Pythagoras applied repeatedly, one axis at a time.',
    angles: [
      { id: 'geometric', label: 'Geometric', summary: 'Arrows in space; tip-to-tail addition; stretching.' },
      { id: 'algebraic', label: 'Algebraic', summary: 'Ordered lists in R^n; componentwise rules; axioms.' },
      { id: 'computational', label: 'Computational', summary: 'NumPy arrays; data as vectors; embeddings.' },
    ],
    examples: [
      { label: 'A 28×28 image as a 784-dim vector', domain: 'ML' },
      { label: 'Word embeddings: king − man + woman ≈ queen', domain: 'NLP' },
      { label: 'Walking directions as displacement', domain: 'everyday' },
    ],
    misconceptions: [
      'A vector is tied to a location (it is not: the same arrow can be drawn anywhere).',
      'Adding vectors adds their lengths (it does not: |u + v| ≤ |u| + |v|).',
    ],
    sources: [
      { title: '3Blue1Brown: Vectors, what even are they?', url: 'https://www.3blue1brown.com/lessons/vectors', kind: 'video', why: 'The canonical geometric intuition; 10 minutes.' },
      { title: 'Mathematics for Machine Learning, ch. 2', url: 'https://mml-book.github.io/', kind: 'book', why: 'Precise definitions with ML framing; free PDF.' },
      { title: 'Immersive Linear Algebra, ch. 2', url: 'https://immersivemath.com/ila/ch02_vectors/ch02.html', kind: 'interactive', why: 'Interactive figures you can drag.' },
    ],
  },
  {
    conceptId: 'c-lincomb',
    version: 1,
    factCheck: 'pending',
    checkedAt: '2026-10-14',
    objective: 'Build new vectors from weighted sums of others.',
    bloom: 'apply',
    core: 'A linear combination is a weighted sum $a u + b v$. Every output of a linear layer is one.',
    formal: '$w = \\sum_i c_i v_i$ with scalars $c_i$.',
    why: 'Scaling and adding are the only two operations a vector space promises, so weighted sums are everything you can build.',
    angles: [
      { id: 'geometric', label: 'Geometric', summary: 'Reaching points by stretching and chaining arrows.' },
      { id: 'computational', label: 'Computational', summary: 'A neuron = weighted sum of inputs.' },
    ],
    examples: [{ label: 'Mixing paint colors (RGB)', domain: 'everyday' }],
    misconceptions: ['Coefficients must be positive.'],
    sources: [
      { title: '3Blue1Brown: Linear combinations, span, and basis vectors', url: 'https://www.3blue1brown.com/lessons/span', kind: 'video', why: 'Canonical intuition.' },
    ],
  },
]

/** Lesson sections for "Vectors": one body per angle; the rendition picks per section. */
export const vectorSections: LessonSection[] = [
  {
    id: 's-why',
    heading: 'Why this comes first',
    variants: {
      geometric: `Every model you will build, from linear regression to GPT, stores everything as vectors: an image, a sentence, the weights of a network, the gradient that updates them. When Karpathy writes \`x = x + self.attn(x)\`, both sides are vectors. Being fluent with them is the cheapest way to make everything later easier.`,
      algebraic: `Linear algebra is the grammar of ML. Every object you will manipulate (inputs, weights, activations, gradients) lives in a vector space $\\mathbb{R}^n$. Get the rules of that space right now and every later derivation becomes bookkeeping.`,
      computational: `Open any ML codebase and nearly every variable is an array: \`images.shape == (batch, 784)\`, \`embeddings.shape == (vocab, 768)\`. Those arrays are vectors (and stacks of vectors). This lesson is about what you are allowed to do with them, and why.`,
    },
  },
  {
    id: 's-idea',
    heading: 'What a vector is',
    variants: {
      geometric: `Picture an **arrow** starting at the origin. Its tip lands at a point, and the coordinates of that point *are* the vector:

$$v = \\begin{pmatrix} 3 \\\\ 2 \\end{pmatrix}$$

means "go 3 steps along x, then 2 steps along y". Two things define the arrow: **direction** and **length**. Where you draw it does not matter: slide it anywhere without rotating it and it is the same vector.

In 3D you add a third coordinate. In ML you keep going: a 28×28 grayscale image is an arrow in a 784-dimensional space. You can't picture 784 axes, but every rule you learn in 2D still holds.`,
      algebraic: `A vector in $\\mathbb{R}^n$ is an **ordered list** of $n$ real numbers:

$$v = (v_1, v_2, \\dots, v_n)$$

Order matters: $(3, 2) \\neq (2, 3)$. The numbers $v_i$ are the **components**, and $n$ is the dimension. Nothing more is assumed yet; what makes these lists *vectors* is the pair of operations below, addition and scaling, and the rules they obey.`,
      computational: `In code, a vector is a 1-D array of numbers:

\`\`\`python
import numpy as np
v = np.array([3.0, 2.0])     # a 2-D vector
img = np.random.rand(784)    # a flattened 28x28 image: a 784-D vector
\`\`\`

The position of each number carries meaning (pixel 0, pixel 1, ...), so order matters. A word embedding is the same thing: \`emb["king"]\` is a vector with, say, 768 numbers that the model learned.`,
    },
  },
  {
    id: 's-ops',
    heading: 'Adding and scaling',
    variants: {
      geometric: `**Add** by chaining arrows **tip to tail**: walk along $u$, then along $v$; where you end up is $u + v$. Because the x-steps and y-steps don't interfere, you can also just add coordinates:

$$\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix} + \\begin{pmatrix} 3 \\\\ -1 \\end{pmatrix} = \\begin{pmatrix} 4 \\\\ 1 \\end{pmatrix}$$

**Scale** by stretching: $2v$ is the same direction, twice as long; $-v$ flips it around; $0.5v$ shrinks it by half.`,
      algebraic: `Both operations are **componentwise**:

$$(u + v)_i = u_i + v_i, \\qquad (c\\,v)_i = c\\,v_i$$

So $(1, 2) + (3, -1) = (4, 1)$ and $2 \\cdot (1, 2) = (2, 4)$. These operations satisfy the vector-space axioms (commutativity, associativity, a zero vector, inverses, distributivity), which is exactly what lets you rearrange expressions like ordinary algebra.`,
      computational: `NumPy does both componentwise, with no loops:

\`\`\`python
u = np.array([1.0, 2.0]); v = np.array([3.0, -1.0])
u + v      # array([4., 1.])
2 * u      # array([2., 4.])
\`\`\`

This is the whole of a gradient-descent step: \`w = w - lr * grad\` scales the gradient vector and adds it to the weight vector.`,
    },
    check: {
      id: 'q-ops',
      prompt: 'What is $2 \\cdot (1, -3) + (0, 4)$?',
      options: ['$(2, -2)$', '$(2, 10)$', '$(1, 1)$', '$(3, -2)$'],
      answer: 0,
      explanation: 'Scale first: $2 \\cdot (1, -3) = (2, -6)$. Then add componentwise: $(2 + 0, -6 + 4) = (2, -2)$.',
    },
  },
  {
    id: 's-length',
    heading: 'Length (the norm)',
    variants: {
      geometric: `The length of $v = (3, 4)$ is the hypotenuse of a right triangle with legs 3 and 4, so by Pythagoras:

$$\\lVert v \\rVert = \\sqrt{3^2 + 4^2} = 5$$

In 3D, apply Pythagoras twice; in $n$ dimensions, keep going: square every component, add, take the root.`,
      algebraic: `The Euclidean norm is

$$\\lVert v \\rVert = \\sqrt{\\textstyle\\sum_{i=1}^{n} v_i^2}$$

It is never negative, is zero only for the zero vector, scales as $\\lVert c v \\rVert = |c|\\,\\lVert v \\rVert$, and obeys the triangle inequality $\\lVert u + v \\rVert \\le \\lVert u \\rVert + \\lVert v \\rVert$.`,
      computational: `\`\`\`python
np.linalg.norm(np.array([3.0, 4.0]))   # 5.0
\`\`\`

You will meet this constantly: gradient clipping caps \`norm(grad)\`, and dividing by the norm gives a **unit vector** (length 1), which is how embeddings are normalized before comparing them.`,
    },
    check: {
      id: 'q-norm',
      prompt: 'What is the length of $(1, 2, 2)$?',
      options: ['$5$', '$3$', '$\\sqrt{5}$', '$9$'],
      answer: 1,
      explanation: '$\\sqrt{1^2 + 2^2 + 2^2} = \\sqrt{9} = 3$.',
    },
  },
  {
    id: 's-misc',
    heading: 'A common trap',
    variants: {
      geometric: `"Adding two vectors adds their lengths." It doesn't. Walk 3 m east, then 4 m north: you walked 7 m, but you are only **5 m** from the start. Lengths add only when the arrows point the same way, which is the triangle inequality: $\\lVert u + v \\rVert \\le \\lVert u \\rVert + \\lVert v \\rVert$.`,
      algebraic: `Norms are not additive. With $u = (3, 0)$ and $v = (0, 4)$: $\\lVert u \\rVert + \\lVert v \\rVert = 7$ but $\\lVert u + v \\rVert = 5$. In general $\\lVert u + v \\rVert \\le \\lVert u \\rVert + \\lVert v \\rVert$, with equality only when one is a non-negative multiple of the other.`,
      computational: `Try it:

\`\`\`python
u, v = np.array([3., 0.]), np.array([0., 4.])
np.linalg.norm(u) + np.linalg.norm(v)  # 7.0
np.linalg.norm(u + v)                   # 5.0
\`\`\`

Summing per-example gradients therefore gives a total gradient whose norm can be much smaller than the sum of norms: the gradients partly cancel.`,
    },
    check: {
      id: 'q-misc',
      prompt: 'If $\\lVert u \\rVert = 2$ and $\\lVert v \\rVert = 3$, which value is **impossible** for $\\lVert u + v \\rVert$?',
      options: ['$1$', '$3.5$', '$5$', '$6$'],
      answer: 3,
      explanation: 'By the triangle inequality, $\\lVert u + v \\rVert \\le 2 + 3 = 5$, and it is at least $|3 - 2| = 1$. So 6 is impossible.',
    },
  },
  {
    id: 's-code',
    heading: 'Build it yourself',
    variants: {
      geometric: `Implement the three operations with plain Python lists (no NumPy), so the rules are in your fingers, not just your head.`,
    },
    code: {
      id: 'x-vec',
      prompt: 'Implement `add(u, v)`, `scale(c, v)` and `norm(v)` for vectors given as Python lists.',
      starter: `import math

def add(u, v):
    # componentwise sum
    ...

def scale(c, v):
    # multiply every component by c
    ...

def norm(v):
    # Euclidean length
    ...
`,
      tests: `assert add([1, 2], [3, -1]) == [4, 1], "add([1, 2], [3, -1]) should be [4, 1]"
assert scale(2, [1, -3]) == [2, -6], "scale(2, [1, -3]) should be [2, -6]"
assert abs(norm([3, 4]) - 5) < 1e-9, "norm([3, 4]) should be 5"
assert abs(norm([1, 2, 2]) - 3) < 1e-9, "norm([1, 2, 2]) should be 3"
print("All tests passed")`,
    },
  },
]

export const initialPlaybook: Playbook = {
  version: 3,
  adjust: { pace: 0, depth: 1, rigor: 0 },
  entries: [
    { id: 'p-geo', dimension: 'angle', value: 'geometric', score: 0.74, evidence: 2.5, verdict: 'works', note: 'You said: "pictures before formulas". Placement answers on geometry questions were strong.' },
    { id: 'p-comp', dimension: 'angle', value: 'computational', score: 0.6, evidence: 1.0, verdict: 'trying', note: 'You code daily; one good outcome so far.' },
    { id: 'p-alg', dimension: 'angle', value: 'algebraic', score: 0.5, evidence: 0.5, verdict: 'trying', note: 'Not tried yet.' },
    { id: 'p-ml', dimension: 'example-domain', value: 'ML / AI', score: 0.8, evidence: 2.0, verdict: 'works', note: 'Stated interest; matches your goal.' },
    { id: 'p-code', dimension: 'format', value: 'code next to math', score: 0.62, evidence: 1.0, verdict: 'trying', note: 'You asked to see code alongside formulas.' },
  ],
}

export const initialRenditions: Rendition[] = [
  {
    conceptId: 'c-vectors', cardVersion: 2, playbookVersion: 3, studied: false,
    sectionAngles: { 's-why': 'geometric', 's-idea': 'geometric', 's-ops': 'geometric', 's-length': 'geometric', 's-misc': 'geometric', 's-code': 'geometric' },
  },
  { conceptId: 'c-lincomb', cardVersion: 1, playbookVersion: 2, studied: false, sectionAngles: {} },
]

export const initialDiffs: RoadmapDiff[] = [
  {
    id: 'd-placement', ts: '2026-10-14T09:12:00', status: 'approved',
    reason: 'Placement diagnostic: you answered all algebra-refresher questions correctly.',
    changes: [{ op: 'compress', title: 'Algebra & functions refresher', detail: 'Marked as known; one spaced review in 7 days instead of 4 lessons.' }],
  },
]

export const providerRoutes: ProviderRoute[] = [
  { role: 'Research', description: 'Parallel researchers, one per perspective', provider: 'claude', model: 'opus' },
  { role: 'Source curation', description: 'Dedupe sources, pick canonical ones', provider: 'claude', model: 'opus' },
  { role: 'Curriculum', description: 'Roadmap outline and prerequisite graph', provider: 'claude', model: 'opus' },
  { role: 'Source cards', description: 'Write concept cards (knowledge center #1)', provider: 'claude', model: 'opus' },
  { role: 'Fact-check', description: 'Independent check of every card', provider: 'codex', model: 'default' },
  { role: 'Renditions', description: 'Your version of each lesson (knowledge center #2)', provider: 'claude', model: 'sonnet' },
  { role: 'Tutor chat', description: 'Socratic help inside a lesson', provider: 'claude', model: 'sonnet' },
  { role: 'Grading', description: 'Free-text and explain-back answers', provider: 'claude', model: 'sonnet' },
  { role: 'Code review', description: 'Feedback on exercise solutions', provider: 'cursor', model: 'default' },
  { role: 'Roadmap review', description: 'Propose roadmap changes from feedback', provider: 'claude', model: 'opus' },
]
