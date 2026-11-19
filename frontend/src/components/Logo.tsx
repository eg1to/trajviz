import { Link } from 'react-router-dom'

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label="trajviz — biblioteca">
      <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="6" fill="#0072B2" /><rect x="5" y="14" width="4" height="4" rx="1" fill="#fff" /><rect x="11" y="14" width="4" height="4" rx="1" fill="#E69F00" /><rect x="17" y="14" width="4" height="4" rx="1" fill="#CC79A7" /><rect x="23" y="14" width="4" height="4" rx="1" fill="#009E73" /></svg>
      <span>trajviz</span>
    </Link>
  )
}
