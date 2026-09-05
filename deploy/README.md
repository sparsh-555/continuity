# deploy/redirect

A tombstone for `continuity-ui.onrender.com`.

The UI and the API used to be two Render services. They are one now — `onrender.com` is on
the Public Suffix List, so two subdomains of it are two different *sites*, the session
cookie was third-party, and WebKit refuses to store those. See
`backend/continuity/api/spa.py`.

The old static site cannot simply be deleted: that URL was submitted as the project link
for the Tencent Cloud Hackathon finals, and judges will click it. So the service stays and
publishes this one file instead of the app.

A Render redirect *rule* is not enough on its own. Render does not apply redirect or rewrite
rules to a path where a resource already exists, and the published site has an `index.html`
at `/` — so a `/*` rule would redirect `/projects` and leave the bare URL, which is the one
that was submitted, serving the old app. A published page redirects unconditionally.

## Static site settings

| Setting | Value |
|---|---|
| Build Command | *(empty)* |
| Publish Directory | `deploy/redirect` |
| Redirect/Rewrite rules | delete the `/*` → `/index.html` rule |

Do this only once the single-service deploy is verified working. Redirecting to something
broken is worse than leaving the old app up.
