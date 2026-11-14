// Turn what the learner picked in a lesson into a feedback/note reference: selected text (formulas inside it
// as their LaTeX source), one formula, or one interactive graph.

import type { FeedbackRef } from '../types'

const latexOf = (el: Element) => el.querySelector('annotation[encoding="application/x-tex"]')?.textContent?.trim() ?? ''

export const sectionOf = (node: Node | null): string | undefined =>
  (node instanceof Element ? node : node?.parentElement)?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId

/** The formula a node is in (KaTeX output keeps the LaTeX source in an annotation). */
export function formulaAt(node: Node | null): Element | null {
  return (node instanceof Element ? node : node?.parentElement)?.closest('.katex') ?? null
}

export function refFromSelection(sel: Selection): FeedbackRef | null {
  if (!sel.rangeCount || sel.isCollapsed) return null
  const range = sel.getRangeAt(0)
  const sectionId = sectionOf(range.commonAncestorContainer)
  const a = formulaAt(sel.anchorNode), b = formulaAt(sel.focusNode)
  if (a && a === b) return { kind: 'formula', quote: latexOf(a).slice(0, 600), sectionId }
  // Mixed text: copy the selection and put each formula back as $LaTeX$, so the quote stays readable.
  const box = document.createElement('div')
  box.appendChild(range.cloneContents())
  box.querySelectorAll('.katex').forEach(k => k.replaceWith(document.createTextNode(`$${latexOf(k)}$`)))
  box.querySelectorAll('.katex-mathml, .katex-html').forEach(k => k.remove())
  const quote = (box.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 600)
  return quote.length >= 3 ? { kind: 'text', quote, sectionId } : null
}

export const describeRef = (r: FeedbackRef) =>
  r.kind === 'formula' ? 'the selected formula' : r.kind === 'viz' ? 'the interactive graph' : 'the selected text'
