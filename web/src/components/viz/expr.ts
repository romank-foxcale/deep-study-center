// A tiny, safe expression evaluator for the `plot` widget: numbers, x, slider parameters,
// + - * / ^, parentheses and whitelisted functions. No eval, no property access.

type Node =
  | { k: 'num'; v: number }
  | { k: 'var'; name: string }
  | { k: 'neg'; a: Node }
  | { k: 'bin'; op: string; a: Node; b: Node }
  | { k: 'call'; fn: string; args: Node[] }

const FUNCS: Record<string, (...a: number[]) => number> = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, exp: Math.exp, log: Math.log, sqrt: Math.sqrt, abs: Math.abs,
  tanh: Math.tanh, sigmoid: (z: number) => 1 / (1 + Math.exp(-z)), relu: (z: number) => Math.max(0, z),
  max: Math.max, min: Math.min,
}
const CONSTS: Record<string, number> = { e: Math.E, pi: Math.PI }

export function parse(src: string): Node {
  const tokens = src.toLowerCase().match(/\d+\.?\d*|\.\d+|[a-z_][a-z0-9_]*|\*\*|[-+*/^(),]/g) ?? []
  if (tokens.join('') !== src.toLowerCase().replace(/\s+/g, '')) throw new Error('unexpected character')
  let i = 0
  const peek = () => tokens[i]
  const next = () => tokens[i++]
  const expect = (t: string) => { if (next() !== t) throw new Error(`expected ${t}`) }

  const primary = (): Node => {
    const t = next()
    if (t === undefined) throw new Error('unexpected end')
    if (/^[\d.]/.test(t)) return { k: 'num', v: parseFloat(t) }
    if (t === '(') { const n = sum(); expect(')'); return n }
    if (t === '-') return { k: 'neg', a: power() }
    if (/^[a-z_]/.test(t)) {
      if (peek() === '(') {
        if (!(t in FUNCS)) throw new Error(`unknown function ${t}`)
        next()
        const args = [sum()]
        while (peek() === ',') { next(); args.push(sum()) }
        expect(')')
        return { k: 'call', fn: t, args }
      }
      return { k: 'var', name: t }
    }
    throw new Error(`unexpected ${t}`)
  }
  const power = (): Node => {
    const base = primary()
    if (peek() === '^' || peek() === '**') { next(); return { k: 'bin', op: '^', a: base, b: power() } }
    return base
  }
  const product = (): Node => {
    let n = power()
    while (peek() === '*' || peek() === '/') { const op = next()!; n = { k: 'bin', op, a: n, b: power() } }
    return n
  }
  const sum = (): Node => {
    let n = product()
    while (peek() === '+' || peek() === '-') { const op = next()!; n = { k: 'bin', op, a: n, b: product() } }
    return n
  }
  const tree = sum()
  if (i !== tokens.length) throw new Error('trailing input')
  return tree
}

export function evaluate(n: Node, vars: Record<string, number>): number {
  switch (n.k) {
    case 'num': return n.v
    case 'var': {
      if (n.name in vars) return vars[n.name]
      if (n.name in CONSTS) return CONSTS[n.name]
      throw new Error(`unknown variable ${n.name}`)
    }
    case 'neg': return -evaluate(n.a, vars)
    case 'call': return FUNCS[n.fn](...n.args.map(a => evaluate(a, vars)))
    case 'bin': {
      const a = evaluate(n.a, vars), b = evaluate(n.b, vars)
      return n.op === '+' ? a + b : n.op === '-' ? a - b : n.op === '*' ? a * b : n.op === '/' ? a / b : Math.pow(a, b)
    }
  }
}
