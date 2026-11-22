import { Link } from 'react-router-dom'
import { jobActive, useStore } from '../store'
import type { LessonView } from '../types'
import Markdown from './Markdown'

const KIND: Record<string, string> = { notation: 'notation', formula: 'formula', idea: 'idea' }

/** The formula tree of a formula lesson (SPEC §37): the blocks it is built from (green: you hold it; gray: new), with
 * "Learn these first", and the formulas and lessons built from it. Learn from the bottom up. */
export default function FormulaTree({ id, info }: { id: string; info: NonNullable<LessonView['formulaLesson']> }) {
  const { s, dispatch } = useStore()
  const busy = jobActive(s, 'formula_lesson', { concept_id: id })
  return (
    <div className="formula-tree">
      <div className="row"><div className="eyebrow">Built from</div><span className="spacer" />
        <Link className="link small" to={`/formulas?focus=${encodeURIComponent(id)}`}>See the whole formula tree</Link></div>
      {!info.blocksReady && <p className="muted small">{busy ? 'Finding the building blocks…' : 'The building blocks are found when the lesson is written.'}</p>}
      {info.blocksReady && info.blocks.length === 0 && <p className="muted small">Nothing below it: it is a basic block.</p>}
      <ul className="formula-blocks">
        {info.blocks.map(b => (
          <li key={b.id} className={`fb fb-${b.state}`}>
            <span className={`fb-dot fb-dot-${b.state}`} aria-hidden />
            <span className="fb-main">
              {b.link?.id ? <Link to={`/lesson/${b.link.id}`}>{b.name}</Link> : <strong>{b.name}</strong>}
              {b.tex && <> <Markdown inline>{`$${b.tex}$`}</Markdown></>}
              <span className="muted small"> · {KIND[b.kind]}{b.basic ? ' · basic' : ''}{b.state === 'known' ? ' · you hold it' : b.link ? ' · lesson not learned yet' : ' · new'}</span>
              <div className="small muted"><Markdown inline>{b.meaning}</Markdown></div>
            </span>
          </li>
        ))}
      </ul>
      {info.missing > 0 && (
        <div className="row small">
          <span>{info.missing} block{info.missing > 1 ? 's are' : ' is'} new to you. Learn {info.missing > 1 ? 'them' : 'it'} first: each is a short lesson
            placed before this one.</span>
          <button className="btn btn-small btn-primary" onClick={() => dispatch({ type: 'learnBlocksFirst', formulaId: id })}>
            Learn {info.missing > 1 ? `these ${info.missing}` : 'it'} first</button>
        </div>
      )}
      {info.usedIn.length > 0 && <>
        <div className="eyebrow">Used in</div>
        <div className="row small formula-used">
          {info.usedIn.map(u => <Link key={u.id} to={`/lesson/${u.id}`} className="pill">{u.kind === 'formula' ? '∑ ' : ''}{u.title}</Link>)}
        </div>
      </>}
    </div>
  )
}
