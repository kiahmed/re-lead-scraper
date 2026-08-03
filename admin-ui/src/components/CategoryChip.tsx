import { categoryClass } from '../lib/format'

export function CategoryChip({ category }: { category: string }) {
  if (!category) return <span className="chip cat-others">Unclassified</span>
  return <span className={`chip cat-${categoryClass(category)}`}>{category}</span>
}
