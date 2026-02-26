# Zava Signal Analyst — Strategic Roadmap

**Created:** 25 February 2026  
**Purpose:** Phased roadmap for evolving the Signal Analyst from a tactical crawl-and-alert tool into a comprehensive UK education sector intelligence platform.

---

## Current State Summary

The platform today collects signals from **6 web sources** (via Playwright) and **2 REST APIs**, enriches them with Companies House data and GPT-4o analysis, routes them through a confidence-based approval pipeline, and distributes intelligence across 9 output formats. Copilot Studio acts as the orchestrator, with live MCP connections to Salesforce CRM and Microsoft 365.

**What works well:** The collection → enrichment → distribution pipeline is solid. The 18-tool interactive agent gives users genuine self-service capability. The Copilot Studio morning trigger automates the daily briefing.

**What's missing:** The platform monitors a narrow band of publicly visible signals. There are significant blind spots in government data, financial health indicators, regulatory outcomes, and sector dynamics that competitors in market intelligence routinely cover.

---

## Phase 1 — Foundation Hardening (Sprint 1–2)

*Fix what's fragile before building more on top.*

### 1.1 Signal Decay & Auto-Expiry
- **What:** Signals have an `EXPIRED` status but nothing sets it. Old signals accumulate forever.
- **Action:** Add a configurable TTL (default 30 days). Run expiry check at start of each sweep. Transition stale `APPROVED` signals to `EXPIRED`. Add `days_since_detected` to signal cards.
- **Effort:** Small
- **Impact:** Prevents stale intelligence from polluting dashboards and reports.

### 1.2 Source Health Monitoring
- **What:** If a Playwright crawl silently returns empty content (site redesign, 403, Cloudflare block), the sweep completes successfully with fewer signals. Nobody knows a source went dark.
- **Action:** Track per-source success/fail/byte-count per sweep. If a source returns <500 chars or errors twice consecutively, flag it in the run history and post a Teams alert to the admin channel.
- **Effort:** Small
- **Impact:** Operational reliability — know immediately when a data source breaks.

### 1.3 Content Change Detection
- **What:** The same 4 education news pages are crawled daily, but there's no diff against yesterday's content. The LLM re-processes unchanged text every run, burning tokens on duplicate extraction.
- **Action:** Store a content hash per URL per run. Skip LLM parsing if hash matches previous run. Log "no new content" for that source. Compare only when hash changes.
- **Effort:** Small
- **Impact:** 30–60% reduction in daily GPT-4o token costs. Faster sweep times.

### 1.4 Crawl Resilience
- **What:** If one of six Playwright pages times out, all signals for that source are lost for the day. No individual retry.
- **Action:** Add per-page retry (2 attempts, exponential backoff with jitter). Respect `robots.txt` for each domain. Add 2–5 second random delay between parallel crawls to avoid bot detection.
- **Effort:** Small
- **Impact:** Reliability + politeness. Gov.uk in particular rate-limits aggressive crawlers.

### 1.5 A2A Endpoint Authentication
- **What:** Zero authentication — anyone who discovers the Container App URL can query the agent, trigger sweeps, and approve/dismiss signals.
- **Action:** Add API key validation via `X-API-Key` header. Store key in Azure Key Vault, inject as env var. Copilot Studio can send custom headers in A2A connections. Fall back to Azure AD managed identity validation as a future step.
- **Effort:** Small
- **Impact:** Security baseline. Currently the biggest risk in the deployment.

### 1.6 Audit Trail
- **What:** No record of who approved/dismissed which signal, who generated reports, or what was distributed.
- **Action:** Add an append-only audit log (JSON lines file initially, Application Insights custom events for production). Log: action, actor, signal ID, timestamp, metadata.
- **Effort:** Small
- **Impact:** Compliance and accountability for sales intelligence decisions.

---

## Phase 2 — UK Education Data Enrichment (Sprint 3–5)

*Tap into the government datasets that drive the sector. These are the signals competitors aren't watching.*

### 2.1 Ofsted Inspection Outcomes
- **Source:** [Ofsted Management Information](https://www.gov.uk/government/statistical-data-sets/monthly-management-information-ofsteds-school-inspections-outcomes) (CSV download, updated monthly) + [Ofsted reports RSS](https://reports.ofsted.gov.uk/)
- **Signal value:** A rating downgrade from "Good" to "Requires Improvement" is one of the strongest triggers for leadership change, trust restructure, and re-procurement. A new "Outstanding" rating signals stability — different sales approach.
- **Categories generated:** `STRUCTURAL_STRESS` (downgrade), `LEADERSHIP_CHANGE` (post-inspection leadership review)
- **Effort:** Medium — structured CSV data, need to join on URN (Unique Reference Number)

### 2.2 DfE Get Information About Schools (GIAS)
- **Source:** [GIAS download](https://get-information-schools.service.gov.uk/Downloads) — full school/trust dataset updated daily
- **Signal value:** The canonical source for academy trust membership. Detects when schools join or leave a trust (transfer), when new trusts form, and when trusts close. Also contains school type, phase, pupil count, and local authority.
- **Categories generated:** `STRUCTURAL_STRESS` (trust transfers, closures), `PROCUREMENT_SHIFT` (new trusts forming = greenfield opportunity)
- **Why critical:** Without GIAS, entity resolution is guesswork. GIAS provides the definitive list of which schools belong to which trust, plus the trust's Companies House number — eliminating Jaccard matching ambiguity.
- **Effort:** Medium — large CSV, need delta processing

### 2.3 DfE Financial Benchmarking (FBIT)
- **Source:** [Schools Financial Benchmarking](https://schools-financial-benchmarking.service.gov.uk/) — per-trust income, expenditure, staff costs, reserves
- **Signal value:** Trusts spending disproportionately on back-office staff vs. teaching staff may be looking to outsource. Declining reserves signal financial pressure. High spend on temporary staff indicates scaling problems.
- **Categories generated:** `FINANCIAL_STRESS` (declining reserves, deficit), `PROCUREMENT_SHIFT` (outsourcing indicators)
- **Effort:** Medium — structured data but requires ratio analysis and trend comparison

### 2.4 ESFA Financial Notices to Improve
- **Source:** [ESFA Notices](https://www.gov.uk/government/collections/academies-financial-notices-to-improve) — published when a trust breaches financial control standards
- **Signal value:** A Financial Notice to Improve (FNtI) is the most severe financial warning. Trusts under FNtI are typically barred from taking on new schools and face mandatory governance changes. Strong indicator of leadership change and systems re-evaluation.
- **Categories generated:** `FINANCIAL_STRESS` (FNtI), `LEADERSHIP_CHANGE` (forced governance changes)
- **Effort:** Small — published as gov.uk pages, can be crawled or RSS-monitored

### 2.5 Regional Director Decisions (formerly RSC)
- **Source:** [Regional Director decisions](https://www.gov.uk/government/collections/regional-schools-commissioners-decisions) — academy orders, trust transfers, interventions
- **Signal value:** When a Regional Director orders a school to transfer between trusts, both the losing and gaining trust are in play. The gaining trust needs to absorb new schools (systems, payroll, HR) — a strong procurement signal.
- **Categories generated:** `STRUCTURAL_STRESS` (forced transfers), `PROCUREMENT_SHIFT` (onboarding new schools)
- **Effort:** Small — published as gov.uk pages

### 2.6 Charity Commission Data
- **Source:** [Charity Commission API](https://register-of-charities.charitycommission.gov.uk/api/) — free, structured JSON
- **Signal value:** Most MATs are registered charities. Annual returns reveal income, expenditure, trustee changes, and purposes. Cross-referencing with Companies House catches governance shifts that appear in charity filings before company filings.
- **Categories generated:** `LEADERSHIP_CHANGE` (trustee appointments), `FINANCIAL_STRESS` (income trends)
- **Effort:** Small — REST API, similar to Companies House integration

---

## Phase 3 — Intelligence Depth (Sprint 6–8)

*Move from "what happened" to "what it means" and "what to do about it".*

### 3.1 Entity Registry & Resolution
- **What:** Build a canonical entity database mapping trust names → Companies House number → Charity Commission number → GIAS UID → Salesforce Account ID.
- **Why:** Today "Harris Federation", "Harris Federation Trust", and "The Harris Federation" are treated as potentially different entities. The Jaccard matching works but is fragile. A proper registry enables cross-source correlation and CRM synchronisation.
- **Action:** Bootstrap from GIAS (which includes Companies House numbers). Enrich with Charity Commission numbers. Build a lookup table that all agents use.
- **Effort:** Medium

### 3.2 Signal Correlation & Clustering
- **What:** If a trust has a leadership change + financial notice + procurement notice in the same fortnight, that's not three independent signals — it's a converging opportunity pattern.
- **Action:** After enrichment, run a clustering step: group signals by entity + time window (14 days). Score cluster severity. Surface clusters as "Opportunity Alerts" with composite confidence scores.
- **Effort:** Medium
- **Impact:** This is the "so what" that turns a list of signals into actionable intelligence. Sales reps care about patterns, not individual data points.

### 3.3 Sentiment & Directionality Scoring
- **What:** "New CFO appointed" is neutral. "CFO resigned amid financial investigation" is strongly negative. "Trust rated Outstanding for second consecutive inspection" is positive. The LLM extracts facts but doesn't score sentiment or direction.
- **Action:** Add `sentiment` (positive/negative/neutral) and `direction` (improving/deteriorating/stable) fields to the Signal model. Have the LLM score these during parsing.
- **Effort:** Small (prompt change + model fields)

### 3.4 Trend Detection & Acceleration Alerts
- **What:** "Harris Federation: 5 signals in 14 days vs 0 in previous 90 days" is a meaningful change in velocity. Auto-detect acceleration patterns across entities.
- **Action:** Track signal frequency per entity over rolling windows (7d, 30d, 90d). When the short-window count exceeds 2× the long-window average, trigger an acceleration alert.
- **Effort:** Small–Medium

### 3.5 Competitive Landscape Mapping
- **What:** Expand from 2 competitor sources to a structured competitor registry. Track which competitors serve which trusts (from G-Cloud records, Find a Tender awards, LinkedIn).
- **Action:** Build a competitor-trust matrix. When a signal appears for a trust, annotate it with known competitors serving that trust. Generate displacement opportunity scores.
- **Effort:** Medium

### 3.6 Full-Text Signal Search
- **What:** Users can filter by category/status/recency but can't search "show me everything mentioning merger" across signal content.
- **Action:** Add a `search_signals` tool using keyword matching initially. Migrate to embedding-based semantic search (Azure AI Search) when signal volume justifies it.
- **Effort:** Small (keyword) / Medium (semantic)

---

## Phase 4 — Operational Maturity (Sprint 9–11)

*Scale, secure, and make it enterprise-grade.*

### 4.1 Database Migration
- **What:** Replace `signals.json` with a proper database. Options: Azure Cosmos DB (natural for JSON documents, serverless pricing), or PostgreSQL Flexible Server (if SQL query capability is needed for reporting).
- **Why:** JSON file doesn't survive concurrent writes safely, has no query language, and makes archival/retention impossible to manage. Container restarts risk data loss if the write isn't flushed.
- **Effort:** Large
- **Impact:** Unlocks scale, concurrent users, proper querying, and retention policies.

### 4.2 Application Insights & Observability
- **What:** No APM, no distributed tracing, no sweep duration metrics, no LLM token usage tracking.
- **Action:** Add Application Insights SDK. Track: sweep duration, signals per source, LLM token consumption per call, Companies House API latency, Playwright page load times, error rates.
- **Effort:** Medium
- **Impact:** Operational visibility. Can't optimise what you can't measure.

### 4.3 Wire Gate 2 — Content Approval
- **What:** The Content Approval gate is built (approve/reject/rework for AI-generated outreach) but not wired into the interactive tools.
- **Action:** Add `generate_outreach_email` tool that drafts a personalised email based on approved signals, submits it to Gate 2, and on approval sends via M365 MCP.
- **Effort:** Medium
- **Dependencies:** M365 MCP email sending

### 4.4 Wire Gate 3 — Strategy Pivot
- **What:** VP-level controls for enabling/disabling categories, adjusting confidence thresholds, managing the competitor watchlist. Built but not exposed.
- **Action:** Add `update_strategy_config` and `get_strategy_config` tools. Restrict to users with "strategy" role (future RBAC). Changes take effect on next sweep.
- **Effort:** Medium

### 4.5 Salesforce Feedback Loop
- **What:** Deal outcomes from Salesforce (won/lost/stalled) should feed back into signal scoring to improve accuracy over time.
- **Action:** Periodically query Salesforce for closed opportunities that were linked to signals. Feed into `feedback_loop.py`. Loss reasons adjust category weights; win factors reinforce successful patterns.
- **Effort:** Medium
- **Dependencies:** Entity registry (#3.1) for signal-to-Account matching

### 4.6 Data Retention & GDPR
- **What:** Signals contain officer PII from Companies House (names, appointment dates). No retention policy, no purging mechanism.
- **Action:** Define retention periods: active signals 90 days, archived signals 1 year (PII stripped), audit logs 2 years. Auto-archive on expiry. GDPR Article 6(1)(f) legitimate interest basis for business intelligence, documented in a DPIA.
- **Effort:** Medium

---

## Phase 5 — Strategic Differentiators (Sprint 12+)

*The capabilities that turn a good tool into an indispensable one.*

### 5.1 RSS/Atom Feed Ingestion
- **What:** TES, Schools Week, and BESA all publish RSS feeds. Structured feeds are faster, lighter, and more resilient than Playwright crawls.
- **Action:** Add an RSS ingestion path alongside Playwright. Use RSS for article discovery and metadata; fall back to Playwright only when full article content is needed for LLM parsing.
- **Effort:** Small
- **Impact:** Reduced crawl costs, faster detection (RSS polls every 15 mins vs daily sweep), more resilient to site redesigns.

### 5.2 LinkedIn & Social Monitoring
- **What:** Leadership changes often appear on LinkedIn before Companies House filings. "Excited to join [Trust] as new CFO" posts appear weeks before the official appointment record.
- **Action:** Integrate LinkedIn API (organisation posts, people updates) or use a social listening proxy. Challenging due to LinkedIn TOS — may need a commercial data provider (e.g., Proxycurl, PhantomBuster).
- **Effort:** Large (API access challenges)
- **Impact:** Early detection of leadership changes — days or weeks ahead of current sources.

### 5.3 Budget Cycle Intelligence
- **What:** Academy trusts operate on an August–July financial year. Key procurement decisions cluster around January–March (budget planning) and May–July (year-end spend). Timing sales outreach to budget cycles dramatically improves conversion.
- **Action:** Add a "budget cycle" dimension to signal scoring. Boost confidence for procurement signals detected during planning season. Generate "budget cycle alert" in January for all tracked trusts.
- **Effort:** Small (rule-based calendar logic)
- **Impact:** Aligns sales effort with buying intent windows.

### 5.4 Peer Comparison & Contagion Signals
- **What:** When three trusts in a region all adopt a new HR platform, the fourth is likely evaluating too. Peer behaviour is a leading indicator of procurement intent.
- **Action:** Cluster trusts by region, size, and phase. When a signal affects multiple members of a peer group, generate a "peer contagion" signal for the remaining members.
- **Effort:** Medium
- **Dependencies:** Entity registry (#3.1), GIAS data (#2.2)

### 5.5 Parliamentary & Policy Monitoring
- **What:** Parliamentary questions, select committee reports, and DfE policy announcements create sector-wide shifts. A new policy on executive pay disclosure or academy trust transparency changes the landscape for every trust simultaneously.
- **Source:** [Parliament API](https://members-api.parliament.uk/), [TheyWorkForYou](https://www.theyworkforyou.com/api/), [Gov.uk announcements](https://www.gov.uk/search/news-and-communications?topical_events%5B%5D=education)
- **Effort:** Medium
- **Impact:** Strategic foresight — knowing a policy change is coming before trusts react to it.

### 5.6 Event & Conference Intelligence
- **What:** BETT Show (January), Schools & Academies Show (multiple dates), ASCL Conference, NAHT Conference — these drive procurement decisions. Who's exhibiting, who's speaking, what topics dominate.
- **Action:** Monitor event agendas and exhibitor lists. Cross-reference exhibitors with competitor registry. Detect when target trusts have speakers presenting (senior attention, likely budget holder).
- **Effort:** Medium

### 5.7 Inbound Signal Webhook
- **What:** No way for external systems to push signals into the platform. CRM triggers, partner tips, manual submissions from sales reps — all currently excluded.
- **Action:** Add `POST /signals/inbound` endpoint accepting a simplified signal payload. Validate, enrich, and route through the same pipeline as crawled signals.
- **Effort:** Small
- **Impact:** Turns the platform from pull-only to push+pull. Sales reps can submit "I heard Trust X is looking at payroll providers" and get it enriched automatically.

### 5.8 Predictive Scoring
- **What:** Move from "here's what happened" to "here's what's likely to happen next". Use historical signal patterns (leadership change → procurement in 3–6 months) to predict future opportunities.
- **Action:** Train a lightweight model on historical signal sequences and deal outcomes (from Salesforce). Score each trust with a "propensity to buy" metric updated with each new signal.
- **Effort:** Large
- **Dependencies:** Salesforce feedback loop (#4.5), sufficient historical data (6–12 months)

---

## Strategic Signal Source Priority Matrix

Sources ranked by **signal quality** (how actionable) × **accessibility** (how easy to integrate):

| Priority | Source | Signal Quality | Accessibility | Current Status |
|----------|--------|---------------|---------------|----------------|
| **P0** | Contracts Finder / Find a Tender | ★★★★★ | ★★★★★ REST API | ✅ Live |
| **P0** | Companies House | ★★★★★ | ★★★★★ REST API | ✅ Live |
| **P0** | TES / Schools Week / BESA | ★★★★ | ★★★★ Playwright | ✅ Live |
| **P0** | G-Cloud / Indeed | ★★★ | ★★★★ Playwright | ✅ Live |
| **P1** | GIAS (DfE) | ★★★★★ | ★★★★★ CSV download | ❌ Not started |
| **P1** | Ofsted | ★★★★★ | ★★★★ CSV + RSS | ❌ Not started |
| **P1** | ESFA Financial Notices | ★★★★★ | ★★★★ Gov.uk pages | ❌ Not started |
| **P2** | Charity Commission | ★★★★ | ★★★★★ REST API | ❌ Not started |
| **P2** | Regional Directors | ★★★★ | ★★★★ Gov.uk pages | ❌ Not started |
| **P2** | DfE Financial Benchmarking | ★★★★ | ★★★ Web scrape | ❌ Not started |
| **P3** | Parliament / Policy | ★★★ | ★★★★ REST API | ❌ Not started |
| **P3** | RSS feeds (existing sources) | ★★★ | ★★★★★ Standard | ❌ Not started |
| **P4** | LinkedIn | ★★★★★ | ★ TOS restrictions | ❌ Not started |
| **P4** | Events / Conferences | ★★★ | ★★ Manual/scrape | ❌ Not started |
| **P4** | Trade union publications | ★★ | ★★★ Web scrape | ❌ Not started |

---

## Phased Timeline

```
Phase 1 ──────── Phase 2 ──────── Phase 3 ──────── Phase 4 ──────── Phase 5
Sprint 1-2       Sprint 3-5       Sprint 6-8       Sprint 9-11      Sprint 12+
                                                                     
Foundation       UK Education     Intelligence     Operational      Strategic
Hardening        Data Sources     Depth            Maturity         Differentiators
                                                                     
• Signal decay   • Ofsted         • Entity         • Database       • RSS feeds
• Source health   • GIAS            registry       • App Insights   • LinkedIn
• Content diff   • FBIT           • Correlation    • Gate 2 wire    • Budget cycles
• Crawl retry    • ESFA FNtI      • Sentiment      • Gate 3 wire    • Peer contagion
• Auth           • Regional Dir   • Trends         • Salesforce     • Parliament
• Audit trail    • Charity Comm   • Competitors      feedback       • Events
                                  • Search         • GDPR/Retention • Inbound webhook
                                                                    • Predictive
```

---

## Success Metrics

| Metric | Phase 1 Target | Phase 3 Target | Phase 5 Target |
|--------|---------------|---------------|---------------|
| Data sources monitored | 8 (current) | 14 | 20+ |
| Signal categories | 5 | 5 + sentiment | 5 + sentiment + prediction |
| Avg signals per sweep | ~10–20 | ~30–50 | ~50–100 |
| False positive rate | Unknown | <20% (via feedback loop) | <10% |
| Time to detect (leadership change) | Days–weeks | Same day (Ofsted/GIAS) | Hours (LinkedIn) |
| Entity resolution accuracy | ~70% (Jaccard) | >95% (GIAS registry) | >99% |
| GPT-4o tokens per sweep | Unknown | -40% (content diffing) | -50% (RSS + diffing) |
| Sales team adoption | Pilot | Cross-team | Company-wide |
