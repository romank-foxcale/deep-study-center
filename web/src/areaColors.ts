/** The colors of the map's areas (books, goals, study sessions). The backend gives each area a fixed number
 *  (`graph.area_colors`), so a book has the same color on its card and on every map view. */
export const AREA_COLORS = ['#22c08a', '#9b7bff', '#ff6fa8', '#4c9dff', '#d9a066', '#2ec4d6', '#c77dff', '#ff9f43', '#7bd389', '#f06595']
export const LOOSE_COLOR = '#8b95aa'

export const areaColor = (n: number | null | undefined) =>
  n == null || n < 0 ? LOOSE_COLOR : AREA_COLORS[n % AREA_COLORS.length]
