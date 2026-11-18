import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import RunnableCode from './RunnableCode'

/** A line that is only $$...$$ is meant as a display formula, but remark-math reads a one-line $$...$$ as inline math.
 * Rewrite it as a block ($$ on their own lines), so it renders as a centered display formula. */
const ONE_LINE_DISPLAY = /^([ \t]*)\$\$([^\n]+?)\$\$[ \t]*$/gm
const displayBlocks = (md: string) =>
  md.replace(ONE_LINE_DISPLAY, (_m, indent: string, tex: string) => `${indent}$$\n${indent}${tex.trim()}\n${indent}$$`)

interface HastNode { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: HastNode[] }
const textOf = (n: HastNode): string => n.value ?? (n.children ?? []).map(textOf).join('')

/** ``runnable``: the lesson id; Python code blocks then become editable and runnable (one namespace per lesson). */
export default function Markdown({ children, inline, runnable }: { children: string; inline?: boolean; runnable?: string }) {
  return (
    <div className={inline ? 'md md-inline' : 'md'}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}
        components={runnable ? {
          pre: ({ node, children: body, ...props }) => {
            const code = (node as HastNode | undefined)?.children?.find(c => c.tagName === 'code')
            const cls = (code?.properties?.className as string[] | undefined) ?? []
            if (code && cls.some(c => c === 'language-python' || c === 'language-py')) {
              return <RunnableCode source={textOf(code)} lesson={runnable} />
            }
            return <pre {...props}>{body}</pre>
          },
        } : undefined}>
        {inline ? children : displayBlocks(children)}
      </ReactMarkdown>
    </div>
  )
}
