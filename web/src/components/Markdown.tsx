import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import RunnableCode from './RunnableCode'
import IdeaLink, { IDEA_HREF } from './IdeaLink'
import type { Components } from 'react-markdown'

/** A line that is only $$...$$ is meant as a display formula, but remark-math reads a one-line $$...$$ as inline math.
 * Rewrite it as a block ($$ on their own lines), so it renders as a centered display formula. */
const ONE_LINE_DISPLAY = /^([ \t]*)\$\$([^\n]+?)\$\$[ \t]*$/gm
const displayBlocks = (md: string) =>
  md.replace(ONE_LINE_DISPLAY, (_m, indent: string, tex: string) => `${indent}$$\n${indent}${tex.trim()}\n${indent}$$`)

interface HastNode { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: HastNode[] }
const textOf = (n: HastNode): string => n.value ?? (n.children ?? []).map(textOf).join('')

/** Links to ideas in the knowledge graph (`#idea/<id>`, SPEC §28) become hover cards; other links stay links. */
const LINKS: Components = {
  a: ({ href, title, children: body }) => {
    const m = href ? IDEA_HREF.exec(href) : null
    return m ? <IdeaLink id={m[1]}>{body}</IdeaLink> : <a href={href} title={title}>{body}</a>
  },
}

/** ``runnable``: the lesson id; Python code blocks then become editable and runnable (one namespace per lesson). */
export default function Markdown({ children, inline, runnable }: { children: string; inline?: boolean; runnable?: string }) {
  return (
    <div className={inline ? 'md md-inline' : 'md'}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
        components={runnable ? { ...LINKS,
          pre: ({ node, children: body, ...props }) => {
            const code = (node as HastNode | undefined)?.children?.find(c => c.tagName === 'code')
            const cls = (code?.properties?.className as string[] | undefined) ?? []
            if (code && cls.some(c => c === 'language-python' || c === 'language-py')) {
              return <RunnableCode source={textOf(code)} lesson={runnable} />
            }
            return <pre {...props}>{body}</pre>
          },
        } : LINKS}>
        {inline ? children : displayBlocks(children)}
      </ReactMarkdown>
    </div>
  )
}
