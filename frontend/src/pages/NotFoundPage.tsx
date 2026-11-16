import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-start px-4 py-32 sm:px-6">
      <p className="eyebrow">404</p>
      <h1 className="mt-3 font-display text-4xl font-light text-paper">Nothing grows here.</h1>
      <p className="mt-4 text-sage-300">The page you were looking for doesn’t exist.</p>
      <Link to="/" className="mt-8 text-sm text-wheat-300 underline-offset-4 hover:underline">
        Back to overview →
      </Link>
    </div>
  )
}
