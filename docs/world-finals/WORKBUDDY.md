# WorkBuddy — install, first run, and what to evaluate

Sourced from `workbuddy.ai/docs/workbuddy` (Overview and FAQ) and Tencent Cloud's own
product pages, 5 Sep 2026. Anything I could not verify from those is marked.

**Mental model: it is Claude Cowork.** Desktop agent, natural-language brief, a working
directory it reads and writes, an artifacts panel, installable skills, scheduled tasks.
The comparison holds well enough that instincts from Cowork transfer directly.

**Current position: WorkBuddy is a build aid, budgeted at about one hour.** Install it, run
the EOL research below, keep the artifacts as a true usage story. Do not integrate it into
the product unless the organiser confirms 4.2 means WorkBuddy specifically — question sent
5 Sep, answer pending.

Note there are two builds. `workbuddy.ai` is the international one, in English, and
`workbuddy.cn` / `codebuddy.cn/work` is the mainland one. They do **not** offer the same
connectors — see Limits below. Use the international build.

## Install

1. Download from **workbuddy.ai**. Builds exist for macOS (Apple Silicon and Intel) and
   Windows (x64 and ARM64).
2. Sign in with **Google OAuth or GitHub OAuth**. Those are the only two methods listed —
   no Chinese phone number or ID required, which is the thing that usually blocks overseas
   accounts on Tencent products.
3. First launch takes **30–60 seconds**. That is documented, not a hang.
4. An internet connection is required; it calls hosted models.

Support address if something breaks: `workbuddy@tencent.com`.

## First task — make it one we actually need

Do not run a toy. Run the EOL research we owe the pitch, which is exactly WorkBuddy's
"Deep Research" use case and tests the product properly at the same time.

Create an empty folder first — the docs recommend one directory per task, and the working
directory is where it reads and saves. Then brief it. Their guidance is that a good brief
carries four things: the goal, the source material, the constraints, and the output format.

```
Research how electronics manufacturers actually respond when a component goes
end-of-life. I need the real workflow, not a vendor pitch.

Cover: how a PCN or EOL notice arrives and who receives it; which roles get
involved and in what order; how a replacement part is qualified and approved;
what an approved-vendor list is and who owns it; how long each stage takes in
practice; and what the response typically costs.

Prefer industry sources, standards bodies, distributor documentation and
practitioner accounts over marketing pages. Cite every source. Where sources
disagree on timings, say so rather than averaging them.

Output a Markdown report with a summary table of the stages and their typical
durations.
```

Watch the conversation pane while it plans and executes. The deliverable lands in
**Artifacts**; **Changes** shows what it wrote to disk. There is a human acceptance step by
design — check the citations before we use a single number from it.

## What to evaluate while you are in there

The whole point is deciding whether any feature is *insanely useful* to us. Four questions,
in priority order:

1. **Connectors — Slack and Gmail.** Can a task read a mailbox and post to a channel? This
   is the one that matters. Documented connectors are Google Drive, Gmail, Slack, Notion,
   GitHub, GitLab, Jira and Confluence.
2. **Automation.** Schedules are hourly, daily, weekly or one-time. Can a scheduled task
   fire on a *condition* (a new mail matching a pattern), or only on a clock? If only on a
   clock, the "PCN arrives and triggers a run" story needs a poll, not an event.
3. **Can a task shell out?** Continuity has an HTTP API and an MCP server. If WorkBuddy can
   call either, it can drive a run. If it cannot, the integration is decorative and we drop
   it.
4. **Skills.** A skill is `skill.yml` plus implementation files, and the docs say you can ask
   WorkBuddy to generate one for you. Worth ten minutes to see the shape, not more.

## Parked — the integration hypothesis

**Not on the critical path.** The deck never says to use WorkBuddy. Its one scoring mention
is a bonus box whose Chinese reads 让决赛作品优化得更顺畅 — "makes *refining your finals
work* go more smoothly." The thing being optimized is our entry, so WorkBuddy is offered as
a **build aid**, the way CodeBuddy was for the preliminary, not as a component to integrate.

What follows is kept only in case the organiser confirms that criterion 4.2 means WorkBuddy
specifically. Until then, do not build it.

Continuity keeps the inner loop untouched: engine proves what is broken, model proposes the
repair, engine re-checks the whole board. WorkBuddy would only ever be the **outer loop**,
at the two edges where Continuity has no capability:

- **In.** A PCN or EOL notice arrives by mail. WorkBuddy notices it and starts a run against
  the affected BOMs.
- **Out.** The engine escalates a decision it cannot make — *"the only candidate that passes
  design is not on the approved list"* — and WorkBuddy delivers that question to the role
  that owns it, on Slack. The reply comes back and resumes the run through `/resume`.

That is the cross-team coordination Scenario B asks about, and it is the piece Continuity
structurally cannot do: it has no inbox and no channel.

**The trap to avoid:** making the three roles WorkBuddy Experts in an Expert Group. It looks
like the deepest possible product use and it would hand compatibility verdicts back to
language models, destroying the claim that won Singapore. Engine keeps the verdicts.

**The trade if it ever reopens:** product depth is 10 points; live demo runnability and
quality are 17. Putting a desktop app, a mailbox and a Slack workspace into the critical path
of a live demo risks the larger number to chase the smaller one.

## What "product depth" actually means — from judges

Criterion 4.2 is 10 points. What follows is filtered from people who have judged sponsor
tracks, keeping only what recurs independently or changes a decision.

**Depth is load-bearing, not present.** A Cloudinary developer advocate with ten years of
judging: he scores a sponsor track on *"not just the use of the platform as a place to dump
images and video, but a deep use of the APIs"* — the platform doing real work inside the
pipeline. DoraHacks states the test as explaining *"how you used their tool, what it enabled
you to build, and why it was **essential**."* If the demo still works with the integration
removed, it was not depth.

**Breadth is the opposite of depth.** The same judge names the failure mode:
*"platformmaxxing"* — using every bell and whistle to prove you tried. One necessary
integration beats five decorative ones.

**Nail the prompt with it.** Warren Marusiak, Atlassian: *"If the prompt is to build
something that does collaboration across multiple products, really show off that use case.
Ancillary benefits are cool, but if it doesn't really nail the prompt, it's going to be hard
to give it full points."* Ours is a coordination prompt, so the product use has to *be* how
the coordination happens.

**Assume a product specialist is comparing all 22 entries.** A Devpost judge describes
panels where *"judges who specialize in a particular product view all the submissions
involved with that product to see which one is the best reflection of the use of the
product."* Best reflection, not most usage.

**Do not let it take the centre.** From a year of judging notes: judges score partly on
whether they can imagine explaining the project to someone else, and *"projects with three
features and no center do not survive that conversation, even when they are technically
stronger than the winners."*

The rule that follows: **WorkBuddy at the edges, Continuity in the middle.** If the demo
opens inside WorkBuddy's UI we are demoing Tencent's product for them. If it opens with a
PCN landing, spends its minutes inside Continuity's validation trace, and returns to
WorkBuddy only to carry one escalation into Slack, Continuity is unambiguously the centre.

The one-line identity has to survive intact — *Continuity proves which substitute actually
works, across three boards, in minutes instead of days.* WorkBuddy does not appear in that
sentence.

## No custom connector needed

Continuity serves plain HTTP: `/bom/validate`, `/design`, `/resume`,
`/threads/{id}/board`, `/export/{id}.csv` (`api/app.py`). Anything that can make an HTTP
request can drive a run, so the integration question reduces to whether a WorkBuddy task can
issue one.

Building a Connector to their open-platform protocol would be platformmaxxing and buys
nothing the HTTP call does not. If a more native surface is ever wanted, wrapping those
endpoints in an MCP server is small and well understood — Continuity already speaks MCP as a
**client** (`parts/mcp.py:109` calls JLC and Mouser tools), it just does not serve one.

## Unresolved: is there a cloud tier?

The FAQ says WorkBuddy must be running on your computer to execute remote tasks. Tencent's
product page advertises a *"Continuously Working Cloud Assistant"* where *"tasks continue to
run in the cloud and can be completed even after the client is closed"*, plus Managed Agents
on WorkBuddy Enterprise. Both cannot be fully true; most likely a tier difference. This
matters for what we can **claim** on stage, not for whether the demo works. Verify in the
app or ask.

## Limits worth knowing now

| | |
|---|---|
| Desktop-bound | WorkBuddy must be **running on your machine** to execute remote tasks. It is not a hosted service. |
| Assistant channels | Slack, Telegram and Discord only on the international build. **WeCom, Feishu and DingTalk are on the mainland build**, so a WeCom demo means switching builds and probably a mainland account. |
| Online only | No offline mode. Inherits whatever network we have at the venue. |
| Direction of travel | Documented flow is WorkBuddy → tools. Whether anything can call *into* WorkBuddy, beyond sending it a command from Slack/Telegram/Discord, is unverified. |
