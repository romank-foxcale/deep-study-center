/** The colors of the map's areas (books, goals, study sessions). The backend gives each area a fixed number
 *  (`graph.area_colors`), so a book has the same color on its card and on every map view. */
export const AREA_COLORS = ['#22c08a', '#9b7bff', '#ff6fa8', '#4c9dff', '#d9a066', '#2ec4d6', '#c77dff', '#ff9f43', '#7bd389', '#f06595']
export const LOOSE_COLOR = '#8b95aa'
/** The Formulas country (SPEC §41): number -2. */
export const FORMULA_COLOR = '#a3e635'

/** The provinces of the Formulas country: one color per field of mathematics, in the backend's ring order
 *  (formula_fields.FIELDS). A formula in 4 or more fields is "Essential" (gray); one with no fields yet is "Not sorted". */
export const FIELD_COLORS: Record<string, string> = {
  algebra: '#d9a066', probability: '#ff6fa8', information: '#ff9f43', ml: '#22c08a', calculus: '#4c9dff',
  linalg: '#2ec4d6', geometry: '#7bd389', physics: '#f06595', algorithms: '#9b7bff', discrete: '#c77dff',
}
export const FIELD_ORDER = Object.keys(FIELD_COLORS)
export const ESSENTIAL_COLOR = '#a3acbd'
export const UNSORTED_COLOR = '#5f6a80'
/** The colors of one formula hex: its fields (1 to 3), gray for 4 or more, dark gray when not sorted yet. */
export const fieldColors = (fields: string[] | undefined): string[] => {
  const f = (fields ?? []).filter(x => FIELD_COLORS[x])
  return f.length >= 4 ? [ESSENTIAL_COLOR] : f.length ? f.map(x => FIELD_COLORS[x]) : [UNSORTED_COLOR]
}

export const areaColor = (n: number | null | undefined) =>
  n === -2 ? FORMULA_COLOR : n == null || n < 0 ? LOOSE_COLOR : AREA_COLORS[n % AREA_COLORS.length]
