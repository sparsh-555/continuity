import { useCallback, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import { ApiError } from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { Wordmark } from '../shell/Wordmark'

type AuthMode = 'signin' | 'signup'

type AuthCardProps = {
  mode: AuthMode
}

/** One rule for where a signed-in user goes, used by both the guard and the submit. */
function landingRouteFor() {
  // Everybody lands on the product lines. The tour that used to play here taught a
  // story the product no longer tells — you describe what you ship, and Continuity
  // watches it for end-of-life parts — and `onboarded` is now only a record of when an
  // account was created.
  return '/lines'
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return 'Email or password is incorrect'
    }

    if (error.status === 409) {
      return 'An account with that email already exists'
    }

    if (error.status === 422) {
      return 'Enter a valid email and a password of at least 8 characters'
    }
  }

  return 'Could not reach the server'
}

function AuthCard({ mode }: AuthCardProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, loading, signIn, signUp } = useAuth()

  const [email, setEmail] = useState(() => {
    const state = location.state as { email?: unknown } | null
    return typeof state?.email === 'string' ? state.email : ''
  })
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  /** One press, four sessions. The engineer last, so that is the desk left active. */
  const signInEveryDesk = useCallback(async () => {
    setSubmitting(true)
    setErrorMessage(null)
    try {
      for (const desk of ['procurement', 'production', 'quality', 'engineer']) {
        await signIn(`${desk}@northwind.example`, DEMO_PASSWORD)
      }
      navigate(landingRouteFor(), { replace: true })
    } catch {
      setErrorMessage('The demo world refused one of its own accounts.')
    } finally {
      setSubmitting(false)
    }
  }, [navigate, signIn])

  if (loading) {
    return null
  }

  // Where a signed-in visitor to /login or /signup belongs. This has to agree with the
  // redirect after a successful submit, because it *races* it: signing in populates the
  // auth context, this component re-renders, and this guard navigates before the explicit
  // one below gets to.
  if (user) {
    return <Navigate replace to={landingRouteFor()} />
  }

  const isSignIn = mode === 'signin'
  const submitLabel = isSignIn ? 'SIGN_IN' : 'CREATE_ACCOUNT'
  const submittingLabel = isSignIn ? 'SIGNING_IN…' : 'CREATING…'
  const sectionLabel = isSignIn ? 'SIGN IN' : 'CREATE ACCOUNT'

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) {
      return
    }

    setSubmitting(true)
    setErrorMessage(null)

    try {
      if (isSignIn) {
        await signIn(email, password)
      } else {
        await signUp(email, password)
      }

      navigate(landingRouteFor(), { replace: true })
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    // Transparent, and no `grid-bg`. `AppFrame` already paints the shared PCB background
    // behind every non-workspace route — this page was covering it with an opaque
    // `bg-background` and then drawing a second, different grid on top, so the two screens
    // that precede every session were the only ones without the product's own backdrop.
    <div className="min-h-screen bg-transparent flex items-center justify-center p-container-margin text-on-background font-body-md antialiased">
      <div className="w-full max-w-[400px] bg-surface-container border border-outline-variant rounded-lg p-xl shadow-2xl flex flex-col gap-lg">
        <div className="flex flex-col items-center gap-md">
          <Wordmark size="lg" />
          <h1 className="font-label-caps text-label-caps uppercase tracking-widest text-primary-container">
            {sectionLabel}
          </h1>
        </div>

        <form className="flex flex-col gap-lg" onSubmit={handleSubmit}>
          <div className="flex items-center bg-surface-container-lowest border border-outline-variant rounded-DEFAULT glow-focus transition-all">
            <span className="material-symbols-outlined text-outline pl-sm text-[18px]">mail</span>
            <input
              autoComplete="email"
              className="w-full bg-transparent border-none focus:ring-0 text-on-surface font-data-tabular text-data-tabular py-sm px-sm placeholder:font-data-tabular placeholder:text-outline"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="ENTER_EMAIL"
              required
              type="email"
              value={email}
            />
          </div>

          <div className="flex flex-col gap-xs">
            <div className="relative flex items-center bg-surface-container-lowest border border-outline-variant rounded-DEFAULT glow-focus transition-all">
              <span className="material-symbols-outlined text-outline pl-sm text-[18px]">lock</span>
              <input
                autoComplete={isSignIn ? 'current-password' : 'new-password'}
                className="w-full bg-transparent border-none focus:ring-0 text-on-surface font-data-tabular text-data-tabular py-sm pl-sm pr-[44px] placeholder:font-data-tabular placeholder:text-outline"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="ENTER_PASSWORD"
                required
                type={showPassword ? 'text' : 'password'}
                value={password}
              />
              <button
                className="absolute right-sm text-outline hover:text-primary-container transition-colors"
                onClick={() => setShowPassword((current) => !current)}
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">
                  {showPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
            {!isSignIn ? (
              <p className="font-body-sm text-body-sm text-on-surface-variant pl-xs">
                8 characters minimum
              </p>
            ) : null}
          </div>

          {errorMessage ? (
            <div className="bg-error-container/20 border border-error rounded-DEFAULT py-xs px-sm flex items-center gap-sm">
              <span className="material-symbols-outlined text-error text-[16px]">warning</span>
              <span className="font-body-sm text-body-sm text-error">{errorMessage}</span>
            </div>
          ) : null}

          <button
            className="w-full bg-primary-container text-on-primary-fixed font-headline-sm text-headline-sm py-md px-lg rounded-DEFAULT hover:bg-primary-fixed transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
            disabled={submitting}
            type="submit"
          >
            {submitting ? submittingLabel : submitLabel}
          </button>
        </form>

        {isSignIn && import.meta.env.DEV ? (
          <>
            <div className="border-t border-outline-variant" />
            {/* **The four seeded desks, signed in at once, before the camera rolls.**
                Development only, and that is the whole point: a control that authenticates
                four fixed accounts belongs to the demo world, and anybody opening the
                deployed application must not find it. `import.meta.env.DEV` is true under
                `bun run dev`, which is what `./demo.sh` runs, and false in every build — so
                this cannot reach a deployment by being forgotten. **The four seeded desks, signed in at once, before the camera rolls.**
                Demo craft guidance is explicit that a presenter should pre-authenticate and
                never sign in live, and the product already holds every session this browser
                has authenticated — so this is four calls rather than a new mechanism.

                The accounts are the demo world's own and their shared password is published
                in RUNNER.md, so writing it here discloses nothing: it is a demo world in a
                scratch database, and this control exists for that world alone. The engineer
                is signed in last so the session left active is the desk the run-through
                opens with. */}
            <button
              className="w-full border border-outline-variant text-on-surface-variant font-body-sm text-body-sm py-sm rounded-DEFAULT hover:bg-surface-container transition-colors disabled:opacity-60"
              disabled={submitting}
              onClick={() => void signInEveryDesk()}
              type="button"
            >
              {submitting ? 'SIGNING IN…' : 'SIGN IN ALL FOUR DESKS · DEMO WORLD'}
            </button>
          </>
        ) : null}

        <div className="border-t border-outline-variant" />

        <div className="text-center">
          {isSignIn ? (
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              No account?{' '}
              <Link
                className="text-primary-container hover:text-primary-fixed underline decoration-primary-container/30 underline-offset-2"
                to="/signup"
              >
                Create one
              </Link>
            </p>
          ) : (
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Already have an account?{' '}
              <Link
                className="text-primary-container hover:text-primary-fixed underline decoration-primary-container/30 underline-offset-2"
                to="/login"
              >
                Sign in
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

/** The demo world's four accounts, and the password RUNNER.md publishes for them. */
const DEMO_PASSWORD = 'continuity-demo-2026'

export function SignInRoute() {
  return <AuthCard mode="signin" />
}

export function SignUpRoute() {
  return <AuthCard mode="signup" />
}
