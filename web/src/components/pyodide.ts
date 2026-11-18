// Python in the browser (Pyodide), shared by exercises and the runnable code blocks in lessons.
// Loaded once, on first use (about 10 MB, cached by the browser afterwards). Packages a snippet imports (for example
// NumPy) are loaded before it runs. No file system access outside Pyodide's own memory, and no network for the code.

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js'

export interface PyProxy { destroy?: () => void }
interface Pyodide {
  runPythonAsync: (code: string, opts?: { globals?: PyProxy }) => Promise<unknown>
  loadPackagesFromImports: (code: string) => Promise<unknown>
  setStdout: (o: { batched: (s: string) => void }) => void
  setStderr: (o: { batched: (s: string) => void }) => void
  globals: { get: (name: string) => () => PyProxy }
}
declare global {
  interface Window { loadPyodide?: (opts?: object) => Promise<Pyodide> }
}

let pyodidePromise: Promise<Pyodide> | null = null

export const pyodideLoaded = () => pyodidePromise !== null

export function getPyodide(): Promise<Pyodide> {
  if (!pyodidePromise) {
    pyodidePromise = new Promise<void>((resolve, reject) => {
      const s = document.createElement('script')
      s.src = PYODIDE_URL
      s.onload = () => resolve()
      s.onerror = () => reject(new Error('Could not load Pyodide'))
      document.head.appendChild(s)
    }).then(() => window.loadPyodide!())
    pyodidePromise.catch(() => { pyodidePromise = null })
  }
  return pyodidePromise
}

// One Python namespace per lesson, like a notebook: a block can use the names that earlier blocks defined.
const namespaces = new Map<string, PyProxy>()

export async function namespaceFor(key: string): Promise<PyProxy> {
  const py = await getPyodide()
  let ns = namespaces.get(key)
  if (!ns) {
    ns = py.globals.get('dict')()
    namespaces.set(key, ns)
  }
  return ns
}

export function resetNamespace(key: string) {
  namespaces.get(key)?.destroy?.()
  namespaces.delete(key)
}

/** Run code and return what it printed. A failure throws an Error whose message is the last traceback line. */
export async function runPython(code: string, globals?: PyProxy): Promise<string> {
  const py = await getPyodide()
  let out = ''
  py.setStdout({ batched: s => { out += s + '\n' } })
  py.setStderr({ batched: s => { out += s + '\n' } })
  try {
    await py.loadPackagesFromImports(code)
    await py.runPythonAsync(code, globals ? { globals } : undefined)
  } catch (e) {
    const msg = String(e instanceof Error ? e.message : e)
    const last = msg.trim().split('\n').filter(Boolean).pop() ?? msg
    throw new Error((out ? out : '') + last)
  }
  return out
}
