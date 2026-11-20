/** Layered layout for the knowledge map (SPEC §23): basic ideas at the bottom, reasoning goes up.
 * Depth = the longest path from a root (an idea with no prerequisite). Inside a layer, nodes are ordered by the mean
 * position of their neighbours (barycenter sweeps, down and up), which removes most crossing links. No library. */

export interface LayoutLink { src: string; dst: string }
export interface Placed { x: number; y: number; depth: number }

export const LAYER_GAP = 120
export const NODE_GAP = 150

export function layout(ids: string[], links: LayoutLink[], group: (id: string) => string = () => ''): Map<string, Placed> {
  const known = new Set(ids)
  const ins = new Map<string, string[]>()
  const outs = new Map<string, string[]>()
  for (const id of ids) { ins.set(id, []); outs.set(id, []) }
  for (const l of links) {
    if (!known.has(l.src) || !known.has(l.dst) || l.src === l.dst) continue
    ins.get(l.dst)!.push(l.src)
    outs.get(l.src)!.push(l.dst)
  }

  // depth = longest path from a root; a cycle (should not happen) is cut where it is found
  const depth = new Map<string, number>()
  const visiting = new Set<string>()
  const depthOf = (id: string): number => {
    const d = depth.get(id)
    if (d !== undefined) return d
    if (visiting.has(id)) return 0
    visiting.add(id)
    const v = Math.max(-1, ...ins.get(id)!.map(depthOf)) + 1
    visiting.delete(id)
    depth.set(id, v)
    return v
  }
  ids.forEach(depthOf)

  const layers: string[][] = []
  for (const id of ids) (layers[depth.get(id)!] ??= []).push(id)
  // start: keep ideas of the same goal or session together, then by id for a stable picture
  for (const layer of layers) layer?.sort((a, b) => group(a).localeCompare(group(b)) || a.localeCompare(b))

  const pos = new Map<string, number>()
  const index = () => layers.forEach(layer => layer?.forEach((id, i) => pos.set(id, i - (layer.length - 1) / 2)))
  index()
  const sweep = (from: number, to: number, step: number, nbrs: Map<string, string[]>) => {
    for (let d = from; step > 0 ? d < to : d > to; d += step) {  // `<`/`>`, not `!==`: an empty graph must end at once
      const layer = layers[d]
      if (!layer) continue
      const bary = new Map(layer.map(id => {
        const ns = nbrs.get(id)!.filter(n => pos.has(n))
        return [id, ns.length ? ns.reduce((s, n) => s + pos.get(n)!, 0) / ns.length : pos.get(id)!] as const
      }))
      layer.sort((a, b) => bary.get(a)! - bary.get(b)!)
      layer.forEach((id, i) => pos.set(id, i - (layer.length - 1) / 2))
    }
  }
  for (let it = 0; it < 6; it++) {
    sweep(1, layers.length, 1, ins)       // upward: follow prerequisites
    sweep(layers.length - 2, -1, -1, outs) // downward: follow what builds on it
  }

  const top = layers.length - 1
  const out = new Map<string, Placed>()
  for (const id of ids) {
    const d = depth.get(id)!
    out.set(id, { x: pos.get(id)! * NODE_GAP, y: (top - d) * LAYER_GAP, depth: d })
  }
  return out
}

/** Every node from which ``targets`` can be reached (their prerequisites, all the way down). */
export function ancestors(targets: Iterable<string>, links: LayoutLink[]): Set<string> {
  const ins = new Map<string, string[]>()
  for (const l of links) (ins.get(l.dst) ?? ins.set(l.dst, []).get(l.dst)!).push(l.src)
  const seen = new Set<string>()
  const stack = [...targets]
  while (stack.length) {
    const id = stack.pop()!
    for (const p of ins.get(id) ?? []) if (!seen.has(p)) { seen.add(p); stack.push(p) }
  }
  return seen
}
