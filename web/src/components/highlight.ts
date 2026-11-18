// A small Python syntax highlighter for lesson code (no dependency): comments, strings, numbers, keywords, builtins,
// function names and decorators. Returns tokens; unknown text stays plain.

export type TokenKind = 'comment' | 'string' | 'number' | 'keyword' | 'builtin' | 'function' | 'decorator' | 'operator' | 'plain'
export interface Token { kind: TokenKind; text: string }

const KEYWORDS = new Set(['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
  'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not',
  'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield', 'match', 'case'])
const BUILTINS = new Set(['print', 'len', 'range', 'sum', 'min', 'max', 'abs', 'round', 'list', 'dict', 'set', 'tuple', 'int',
  'float', 'str', 'bool', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'isinstance', 'type', 'any', 'all', 'self',
  'np', 'numpy', 'math', 'random'])

// Order matters: comments and strings first, so a '#' or keyword inside them is not split out.
const RULES: [TokenKind, RegExp][] = [
  ['comment', /^#[^\n]*/],
  ['string', /^(?:[rRbBuUfF]{0,2})(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?)/],
  ['decorator', /^@[A-Za-z_][\w.]*/],
  ['number', /^(?:0[xX][\da-fA-F_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?j?)/],
  ['plain', /^[A-Za-z_]\w*/],
  ['operator', /^(?:\*\*|\/\/|==|!=|<=|>=|->|[-+*/%=<>&|^~@:.,()[\]{}])/],
  ['plain', /^\s+/],
  ['plain', /^[^\s]/],
]

export function highlightPython(code: string): Token[] {
  const out: Token[] = []
  let rest = code
  while (rest) {
    let matched = false
    for (const [kind, re] of RULES) {
      const m = re.exec(rest)
      if (!m || !m[0]) continue
      const text = m[0]
      let k: TokenKind = kind
      if (kind === 'plain' && /^[A-Za-z_]/.test(text)) {
        if (KEYWORDS.has(text)) k = 'keyword'
        else if (BUILTINS.has(text)) k = 'builtin'
        else if (/^\s*\(/.test(rest.slice(text.length))) k = 'function'
      }
      const last = out[out.length - 1]
      if (last && last.kind === k && k === 'plain') last.text += text
      else out.push({ kind: k, text })
      rest = rest.slice(text.length)
      matched = true
      break
    }
    if (!matched) { out.push({ kind: 'plain', text: rest[0] }); rest = rest.slice(1) }
  }
  return out
}
