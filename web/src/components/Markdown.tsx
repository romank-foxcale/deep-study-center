import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import RunnableCode from './RunnableCode'
import IdeaLink, { IDEA_HREF } from './IdeaLink'
import type { Components } from 'react-markdown'
import type { ReactElement } from 'react'

/** A line that is only $$...$$ is meant as a display formula, but remark-math reads a one-line $$...$$ as inline math.
 * Rewrite it as a block ($$ on their own lines), so it renders as a centered display formula. */
const ONE_LINE_DISPLAY = /^([ \t]*)\$\$([^\n]+?)\$\$[ \t]*$/gm
/** A display formula over several lines with text on the fence lines ("$$\begin{aligned}" … "\end{aligned}$$"):
 * remark-math drops what follows an opening $$ and needs the closing $$ on its own line, so the formula breaks and the
 * text after it turns into one red KaTeX error. Put both fences on their own lines. */
const MULTI_LINE_DISPLAY = /^([ \t]*)\$\$([^\n$]*\n[\s\S]*?)\$\$[ \t]*$/gm
export const displayBlocks = (md: string) =>
  md.replace(ONE_LINE_DISPLAY, (_m, indent: string, tex: string) => `${indent}$$\n${indent}${tex.trim()}\n${indent}$$`)
    .replace(MULTI_LINE_DISPLAY, (_m, indent: string, tex: string) => `${indent}$$\n${tex.trim()}\n${indent}$$`)

interface HastNode { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: HastNode[] }
const textOf = (n: HastNode): string => n.value ?? (n.children ?? []).map(textOf).join('')

/** Links to ideas in the knowledge graph (`#idea/<id>`, SPEC §28) become hover cards; other links stay links. */
const LINKS: Components = {
  a: ({ href, title, children: body }) => {
    const m = href ? IDEA_HREF.exec(href) : null
    return m ? <IdeaLink id={m[1]}>{body}</IdeaLink> : <a href={href} title={title}>{body}</a>
  },
}

/** Writers sometimes fold a part away with `<details><summary>…</summary>…</details>`. Raw HTML is never rendered, so
 * this one block is cut out of the text and drawn as a real collapsible block, its parts as Markdown again. */
const DETAILS = /<details>\s*<summary>([\s\S]*?)<\/summary>([\s\S]*?)<\/details>/g

/** The components for a lesson's runnable code. One object per lesson, made once: a new `pre` function at each render
 * would be a new component type to React, so every refresh of the page (the app polls while jobs run) would remount the
 * code blocks and throw away what the learner typed. */
const RUNNABLE = new Map<string, Components>()
function runnableComponents(lesson: string): Components {
  let c = RUNNABLE.get(lesson)
  if (!c) {
    c = { ...LINKS,
      pre: ({ node, children: body, ...props }) => {
        const code = (node as HastNode | undefined)?.children?.find(x => x.tagName === 'code')
        const cls = (code?.properties?.className as string[] | undefined) ?? []
        if (code && cls.some(x => x === 'language-python' || x === 'language-py')) {
          return <RunnableCode source={textOf(code)} lesson={lesson} />
        }
        return <pre {...props}>{body}</pre>
      },
    }
    RUNNABLE.set(lesson, c)
  }
  return c
}

/** ``runnable``: the lesson id; Python code blocks then become editable and runnable (one namespace per lesson). */
export default function Markdown({ children, inline, runnable }: { children: string; inline?: boolean; runnable?: string }) {
  if (!inline && children.includes('<details>')) {
    const parts: ReactElement[] = []
    let at = 0
    for (const m of children.matchAll(DETAILS)) {
      if (m.index! > at) parts.push(<Markdown key={at} runnable={runnable}>{children.slice(at, m.index)}</Markdown>)
      parts.push(<details key={`d${m.index}`} className="md-details"><summary><Markdown inline>{m[1].trim()}</Markdown></summary>
        <Markdown runnable={runnable}>{m[2].trim()}</Markdown></details>)
      at = m.index! + m[0].length
    }
    if (parts.length) {
      if (at < children.length) parts.push(<Markdown key={at} runnable={runnable}>{children.slice(at)}</Markdown>)
      return <div className="md-parts">{parts}</div>
    }
  }
  return (
    <div className={inline ? 'md md-inline' : 'md'}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
        components={runnable ? runnableComponents(runnable) : LINKS}>
        {inline ? children : displayBlocks(children)}
      </ReactMarkdown>
    </div>
  )
}
