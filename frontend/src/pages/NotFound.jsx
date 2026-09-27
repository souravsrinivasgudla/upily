import { ButtonLink, Kicker } from '../components/ui'

export default function NotFound({ title = 'This page is not in today’s edition.', message }) {
  return (
    <section className="border-4 border-ink px-6 py-16 text-center">
      <Kicker accent className="block mb-4">Correction</Kicker>
      <h1 className="font-serif text-4xl font-black leading-tight sm:text-5xl text-balance">{title}</h1>
      <p className="mx-auto mt-4 max-w-lg font-body text-neutral-600">
        {message || 'It may have been archived, or the link is mistyped.'}
      </p>
      <ButtonLink to="/" className="mt-8 w-full md:w-auto">Back to the front page</ButtonLink>
    </section>
  )
}
