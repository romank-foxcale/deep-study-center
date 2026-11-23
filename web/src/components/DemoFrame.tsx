import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import type { StepDemo } from '../types'

// A generated interactive demo (SPEC §45). It runs in a sandboxed iframe: scripts only, no same origin (so no cookies
// and no app API), and a Content-Security-Policy that blocks every request. Before the learner sees a new demo, it is
// loaded hidden and operated (every slider to both ends, every select option, every button once); errors go back to
// the server, which fixes the demo once or leaves it out. A tested demo shows at once.

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:"

/** The bridge, first in the demo's head: reports errors and its height, and in test mode operates every control. */
function bridge(token: string, test: boolean): string {
  return `<script>(function(){var T=${JSON.stringify(token)},errs=[];
function send(m){m.dscDemo=T;parent.postMessage(m,'*')}
addEventListener('error',function(e){errs.push(String(e.message||'error')+(e.lineno?' (line '+e.lineno+')':''))});
addEventListener('unhandledrejection',function(e){errs.push('promise: '+String(e.reason))});
function fire(el,t){el.dispatchEvent(new Event(t,{bubbles:true}))}
function operate(){try{
[].slice.call(document.querySelectorAll('input[type=range],input[type=number]')).forEach(function(i){
[i.min||'0',i.max||'100',i.defaultValue].forEach(function(v){i.value=v;fire(i,'input');fire(i,'change')})});
[].slice.call(document.querySelectorAll('select')).forEach(function(s){for(var k=0;k<s.options.length;k++){s.selectedIndex=k;fire(s,'change')}s.selectedIndex=0;fire(s,'change')});
[].slice.call(document.querySelectorAll('button')).slice(0,8).forEach(function(b){b.click()});
}catch(e){errs.push(String(e))}}
addEventListener('load',function(){
var ro=new ResizeObserver(function(){send({height:document.documentElement.scrollHeight})});ro.observe(document.documentElement);
${test ? "setTimeout(function(){operate();setTimeout(function(){send(errs.length?{error:errs}:{ok:true})},900)},400);" : "setTimeout(function(){if(errs.length)send({error:errs})},1500);"}
})})();</script>`
}

function srcDoc(html: string, token: string, test: boolean): string {
  const head = `<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}">${bridge(token, test)}`
  const m = /<head[^>]*>/i.exec(html)
  if (m) return html.slice(0, m.index + m[0].length) + head + html.slice(m.index + m[0].length)
  const d = /<!doctype[^>]*>/i.exec(html)
  return d ? html.slice(0, d.index + d[0].length) + `<head>${head}</head>` + html.slice(d.index + d[0].length) : `<head>${head}</head>${html}`
}

export default function DemoFrame({ conceptId, sectionId, demo }: { conceptId: string; sectionId: string; demo: StepDemo }) {
  const { dispatch } = useStore()
  const [passed, setPassed] = useState(false)
  const [failed, setFailed] = useState(false)
  const [height, setHeight] = useState(360)
  const shown = useRef<HTMLIFrameElement>(null)
  const tester = useRef<HTMLIFrameElement>(null)
  const token = useMemo(() => `${sectionId}:${demo.version}:${Math.random().toString(36).slice(2)}`, [sectionId, demo.version])
  const testing = demo.status === 'ready' && !demo.tested && !passed && !failed
  useEffect(() => { setPassed(false); setFailed(false) }, [demo.version])

  useEffect(() => {
    const on = (e: MessageEvent) => {
      const d = e.data as { dscDemo?: string; ok?: boolean; error?: string[]; height?: number } | null
      if (!d || d.dscDemo !== token) return
      if (e.source === shown.current?.contentWindow && typeof d.height === 'number') setHeight(Math.max(160, Math.min(640, d.height + 4)))
      if (e.source !== tester.current?.contentWindow) return
      if (d.ok) {
        setPassed(true)
        void dispatch({ type: 'demoResult', conceptId, sectionId, version: demo.version, ok: true })
      } else if (d.error) {
        setFailed(true)
        void dispatch({ type: 'demoResult', conceptId, sectionId, version: demo.version, ok: false, errors: d.error })
      }
    }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [token, conceptId, sectionId, demo.version, dispatch])

  if (demo.status === 'building') return <div className="demo-note skeleton">Building an interactive demo for this step…</div>
  if (demo.status !== 'ready' || !demo.html) return null
  if (failed) return <div className="demo-note muted small">The demo did not work when it was tried. It is being fixed.</div>
  return (
    <div className="demo">
      {testing && <>
        <div className="demo-note skeleton">Trying the demo before you see it…</div>
        <iframe ref={tester} className="demo-tester" title="Demo test" sandbox="allow-scripts" srcDoc={srcDoc(demo.html, token, true)} aria-hidden tabIndex={-1} />
      </>}
      {!testing && <>
        <div className="demo-head row"><span className="eyebrow">Try it{demo.title ? ` · ${demo.title}` : ''}</span></div>
        {demo.watch && <p className="small muted demo-watch">{demo.watch}</p>}
        <iframe ref={shown} className="demo-frame" title={demo.title || 'Interactive demo'} sandbox="allow-scripts"
          srcDoc={srcDoc(demo.html, token, false)} style={{ height }} />
      </>}
    </div>
  )
}
