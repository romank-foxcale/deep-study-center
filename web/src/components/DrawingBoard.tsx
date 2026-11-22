import { useEffect, useRef, useState } from 'react'

const W = 900
const H = 420
const INK = ['#e8e6df', '#7cc4ff', '#ffb35c', '#ff6b8a']

/** A drawing board for calculations and sketches (SPEC §31): pen, colors, eraser, undo and clear. The picture is sent
 * with the answer as a PNG and the grader reads it. Works with a mouse, a pen or a finger. */
export default function DrawingBoard({ onChange }: { onChange: (png: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const strokes = useRef<{ color: string; width: number; pts: [number, number][] }[]>([])
  const drawing = useRef(false)
  const [color, setColor] = useState(INK[0])
  const [erase, setErase] = useState(false)
  const [count, setCount] = useState(0)

  const paint = () => {
    const c = canvas.current
    const ctx = c?.getContext('2d')
    if (!c || !ctx) return
    ctx.fillStyle = '#14161c'
    ctx.fillRect(0, 0, W, H)
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 1
    for (let x = 30; x < W; x += 30) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke() }
    for (let y = 30; y < H; y += 30) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke() }
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    for (const st of strokes.current) {
      ctx.strokeStyle = st.color
      ctx.lineWidth = st.width
      ctx.beginPath()
      st.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
      if (st.pts.length === 1) ctx.lineTo(st.pts[0][0] + 0.1, st.pts[0][1])
      ctx.stroke()
    }
  }
  useEffect(paint, [])

  const point = (e: React.PointerEvent): [number, number] => {
    const r = canvas.current!.getBoundingClientRect()
    return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H]
  }
  const done = () => {
    setCount(strokes.current.length)
    onChange(strokes.current.length ? canvas.current!.toDataURL('image/png') : null)
  }
  const down = (e: React.PointerEvent) => {
    e.preventDefault()
    canvas.current!.setPointerCapture(e.pointerId)
    drawing.current = true
    strokes.current.push({ color: erase ? '#14161c' : color, width: erase ? 22 : 2.6, pts: [point(e)] })
    paint()
  }
  const move = (e: React.PointerEvent) => {
    if (!drawing.current) return
    strokes.current[strokes.current.length - 1].pts.push(point(e))
    paint()
  }
  const up = () => {
    if (!drawing.current) return
    drawing.current = false
    done()
  }

  return (
    <div className="drawing-board">
      <div className="row drawing-tools">
        {INK.map(c => (
          <button key={c} type="button" className={`ink${!erase && color === c ? ' ink-on' : ''}`} style={{ background: c }}
            onClick={() => { setColor(c); setErase(false) }} aria-label={`Pen color ${c}`} />
        ))}
        <button type="button" className={`btn btn-small${erase ? ' btn-primary' : ''}`} onClick={() => setErase(x => !x)}>Eraser</button>
        <button type="button" className="btn btn-small" disabled={!count} onClick={() => { strokes.current.pop(); paint(); done() }}>Undo</button>
        <button type="button" className="btn btn-small" disabled={!count} onClick={() => { strokes.current = []; paint(); done() }}>Clear</button>
        <span className="muted small">The grader reads the board with your words.</span>
      </div>
      <canvas ref={canvas} width={W} height={H} className="drawing-canvas"
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up} />
    </div>
  )
}
