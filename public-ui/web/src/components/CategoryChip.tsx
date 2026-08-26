const SLUGS: Record<string, string> = {
  'Subject-To': 'subject-to',
  'Seller Finance': 'seller-finance',
  Hybrid: 'hybrid',
  'Fix & Flip': 'fix-flip',
  'JV or Wholesale': 'jv-wholesale',
  'Buyers Looking': 'buyers-looking',
  Regular: 'regular',
}

export function categorySlug(category: string): string {
  return SLUGS[category] ?? 'others'
}

export function CategoryChip({ category }: { category: string }) {
  const label = category || 'Unclassified'
  return <span className={`chip cat-${categorySlug(category)}`}>{label}</span>
}

export function HoaChip({ hoa }: { hoa: 'none' | 'zero' | 'has' }) {
  if (hoa === 'none') return null
  return (
    <span className={`chip hoa-${hoa}`}>{hoa === 'zero' ? 'No HOA' : 'Has HOA'}</span>
  )
}
