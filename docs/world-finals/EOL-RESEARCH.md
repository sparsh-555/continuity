# EOL response — how it actually works, and what it costs

Research for Scenario B, 5 Sep 2026. Every figure carries its source. Where sources
disagree they are shown disagreeing, not averaged.

## 1 · How an EOL notice reaches a manufacturer

A PCN (Product Change Notification) or PDN (Product Discontinuance Notification) is the
formal notice. **EOL** is the lifecycle condition; the PDN is the document that starts the
clock. Every notice carries a **LTB (Last Time Buy)** date — the final date the manufacturer
accepts orders.

Notices arrive through several channels at once, and that fragmentation is the problem:

| Channel | Note |
|---|---|
| Manufacturer PCN/PDN portals | Usually require an account and per-device-family subscription. Microchip lets you pick immediate or weekly delivery. |
| Manufacturer and authorised distributor email alerts | The default. One inbox. |
| Distributor lifecycle and change feeds | |
| Forwarded supplier emails to a shared mailbox | Extremely common and entirely manual |
| Component-intelligence platforms | SiliconExpert, Z2Data, Accuris (ex-IHS Markit), Octopart |
| PLM lifecycle monitoring / ERP-AVL workflows | Where a large org wants the join |
| GIDEP | Government/defence DMSMS programmes |

The properties that matter to us, all sourced:

- **Notices are unstructured.** PCNshark: *"PCNs arrive as unstructured PDFs and emails, in
  inconsistent formats, from many manufacturers and distributors, on no shared schedule."*
- **Volume is high and duplicated.** Z2Data: across ~700 manufacturers, millions of PCNs and
  PDNs issue annually, *"three to four duplicates per change and hundreds landing on a large
  OEM each month."*
- **Roughly a third of end-of-life events never get a notice at all.** Z2Data puts it at
  ~30%; a 2025 write-up citing Z2Data says 37% and counts **185,000 components discontinued
  without a PDN in 2024**. About **473,000 parts reached EOL in 2023** (Z2Data).
- **Matching is on MPN and nothing else.** Descriptions and internal part numbers do not
  join to anything the outside world publishes.
- Alerting convention when feeds disagree on dates: **earliest date wins**, because *"being
  early costs a conversation and being late costs a line stoppage."*

**For us:** the realistic trigger is an unstructured PDF or email, arriving in an inbox,
that must be parsed into {MPN, notice type, effective date, LTB date, recommended
replacement} and then matched against active BOMs on MPN. That parsing job is a genuine
model task on genuinely messy input — a better front-end for the orchestrator than the
planner ever was.

## 2 · What happens next, and where the time goes

### Who moves first

iLenSys, on emergency obsolescence, describes exactly Scenario B's handoff:

> *"Procurement or supply chain usually detects the issue first through messages like 'no
> availability,' 'LTB required,' or 'supplier recommends an alternate.' They escalate
> urgently to engineering, asking whether the part can be replaced without redesign, if
> alternates are approved, and what the impact is on compliance, certifications, firmware,
> PCB design, qualification, and customer communication. **This handoff is typically rushed,
> as material constraints collide with engineering validation timelines.**"*

Procurement detects. Engineering must answer. The handoff is the bottleneck. That is the
prompt's "cross-team response", described by industry rather than invented by us.

### The mandatory checklist

Industry practice on receiving a notice (Welllinkchips, citing TI, Infineon and Microchip
policy documents). None of this is optional:

- PCN/PDN number and revision recorded; notice type classified correctly
- Affected MPNs matched against **active and service** BOMs
- Change description, dates and qualification data saved
- Product, customer and regulatory impact identified
- Open PO and inventory exposure calculated
- **Replacement classified as exact / qualified alternate / redesign candidate**
- LTB quantity calculated *only after* demand and storage review
- **Owners assigned in engineering, procurement, quality and manufacturing**
- BOM/AVL/PLM records updated after final approval, next review date recorded

### The trap that is our money shot

Listed as a standard industry mistake: **"Assuming the recommended replacement is drop-in."**

> *"Does a recommended replacement mean it is pin-compatible? **No.** It may be similar,
> functionally comparable, pin-compatible but not parametric-equivalent, or an exact
> replacement. Read the manufacturer's replacement notes and verify the part's compatibility
> with your application."*

The manufacturer's own suggested replacement is not guaranteed to work in *your* application.
That is the documented failure mode, and it is precisely what a whole-board re-check catches.
We do not have to invent the demo's reveal — industry already named it.

Second documented mistake, also ours: **"Waiting until LTB to calculate demand."** The LTB
date is the last chance to order, not the date to start planning.

### Time and money

**DoD SD-22 / 2009 DoC survey, FY2011 dollars.** The only widely used source that reports
*time* alongside cost:

| Resolution | Avg cost | Weeks to resolve |
|---|---|---|
| Admin substitute | $3,000 | 4 |
| Desktop substitute | $5,000 | 8 |
| Alternate source | $41,000 | 11 |
| **Normal substitute** — validate one known candidate | **$34,000** | **25** |
| **Complex substitute** — seek, select and validate from several candidates | **$423,000** | **40** |
| Emulation | $73,000 | 26 |
| Redesign — COTS | $1,118,000 | 42 |
| Redesign — next higher assembly | $1,010,000 | 64 |

**"Complex substitute" is the literal definition of what Continuity does**: *"Seeking,
selecting, and validating a new part from several potential candidates."* Industry average
to resolve one: **40 weeks**. Scenario B allows **48 hours**.

**2015 BIS DMSMS survey** (later survey, same programme): approved parts $1,028 · life-of-need
buy $5,234 · simple substitute $12,579 · **complex substitute $25,410** · redesign–NHA
$1,092,856.

⚠️ **Do not reconcile these.** The FY2011 metric puts complex substitute at $423,000 and the
2015 survey puts it at $25,410 — a 16× spread on a same-named category, almost certainly
different categorisation between surveys. Quote one with its source, or quote neither.

**IIOM 2025, inflation-adjusted from the DoD metrics:** approved item $1,281 · life-of-need
buy $6,514 · simple substitute $15,656 · design refreshment $955,369 · redesign–NHA
$2,080,169 · redesign–complex/system $12,805,363.

**The defensible headline, which does not depend on the disputed cell:**

> Resolving an EOL with a part that is already approved costs about **$1,281**.
> Resolving it with a board redesign costs about **$955,000 to $2.08M**.
> The same event, a spread of roughly **750×**, and the only thing that separates them is
> whether somebody can prove a cheaper option actually works.

That is the business case in one sentence, and Continuity's entire job is to answer that
question in minutes instead of months.

**Commercial-sector numbers** (iLenSys, automation-equipment OEMs — less rigorous than the
DoD data, use as colour not spine): a single emergency redesign averages **$150,000–$500,000**
($80K–$600K depending on machine type). **20–40% of last-time-buy inventory is eventually
scrapped.** Shipment delays run **$5,000–$50,000 per day**. Total annual cost of unmanaged
obsolescence to a mid-size OEM: **$2.5M–$12M**.

**Z2Data:** obsolescence-driven redesigns range **$20,000 to ~$2M**; ~**10% of aerospace
manufacturers' component budgets** go to managing obsolescence risk; post-discontinuation
chip prices run **10–15× the original**.

## 3 · What is skipped when it is urgent

The checklist above is what *should* happen. Under a deadline, what compresses is the
engineering validation — the leg iLenSys describes as "rushed". Requalification is the
expensive, slow, mandatory-in-regulated-industries step; it is what separates a $15,656
simple substitute from a $955,369 design refresh. Nothing in the sources suggests
requalification itself gets skipped in regulated sectors; what gets skipped is the *search* —
teams take the manufacturer's recommended replacement, or the first alternate that looks
close, precisely because searching properly costs 40 weeks.

**That is the wedge.** Continuity does not remove requalification. It removes the reason
teams skip the search.

## Sources

- PCNshark, *PCN Management Software: Features and Evaluation Guide* — channels, unstructured intake
- Welllinkchips, *PCN vs PDN vs EOL* — the mandatory checklist, the drop-in trap; cites TI, Infineon, Microchip policy
- iLenSys, *The Cost of Doing Nothing* (white paper) — the procurement→engineering handoff, emergency redesign costs
- US BIS / DoD, *DMSMS Cost Metrics Report 2015* and *Final Report DMSMS NRE Cost Metric Update* — the cost/time tables
- IIOM Paris 2025, *Supply Chain Risk Management and Obsolescence* — 2025 inflation-adjusted metrics
- Z2Data, *Understanding Obsolescence in the Electronics Industry* and lifecycle product pages
- SiliconExpert Proactive Alerts; IHS Markit PCNalert brochure — alert mechanics, 24h indexing
