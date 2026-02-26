# Customer Follow-Up Email

---

**Subject:** Update on Your Market Intelligence Solution — Proposed Approach

---

Hi [Name],

I hope you're well. I wanted to drop you a line to share some progress on the market intelligence solution we discussed.

I've been exploring how we can bring this together using the Microsoft stack alongside your existing tools, and I'm pleased to say we've landed on an approach that I think ticks all the boxes. Let me walk you through the high-level thinking.

## The Short Version

The centrepiece of the solution is **Microsoft Copilot Studio** — this acts as the orchestrator that ties everything together. Your team interacts with a single conversational agent (in Teams, or wherever suits), and behind the scenes Copilot Studio connects out to the different systems and services needed to get the job done.

Here's a simplified view of the architecture:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COPILOT STUDIO (Orchestrator)                       │
│                                                                             │
│   User ──▶ Conversational AI ──▶ Routes to connected services              │
│                                                                             │
│   ┌──────────────┐   ┌──────────────────┐   ┌────────────────────────────┐ │
│   │ Salesforce    │   │ Microsoft 365    │   │ Signal Analyst             │ │
│   │ Connector     │   │ Services         │   │ (Custom Intelligence Tool) │ │
│   │               │   │                  │   │                            │ │
│   │ • Query CRM   │   │ • Send email     │   │ • Scan for market signals  │ │
│   │ • Search      │   │ • Post to Teams  │   │ • Enrich with public data  │ │
│   │   accounts    │   │ • Create tasks   │   │ • Generate reports         │ │
│   │ • Retrieve    │   │ • Book meetings  │   │ • Flag items for review    │ │
│   │   documents   │   │ • Retrieve docs  │   │                            │ │
│   └──────┬───────┘   └────────┬─────────┘   └────────────┬───────────────┘  │
│          │                    │              ⏰ Morning     │               │
│          │                    │◀── Trigger: get report ────┘                │
│          │                    │    & email to stakeholders                  │
└──────────┼────────────────────┼─────────────────────────────────────────────┘
           │                    │                            │
           ▼                    ▼                            ▼
┌──────────────────┐ ┌─────────────────────┐ ┌──────────────────────────────┐
│   Salesforce     │ │   Microsoft 365     │ │   Signal Analyst Engine      │
│                  │ │                     │ │                              │
│ Accounts         │ │ Outlook  SharePoint │ │ Scans procurement portals,   │
│ Opportunities    │ │ Teams    Planner    │ │ Companies House, competitor  │
│ Contacts         │ │ Calendar            │ │ websites & education news.   │
│ Documents        │ │                     │ │ Produces reports & alerts.   │
└──────────────────┘ └─────────────────────┘ └──────────────────────────────┘
```

## What This Means in Practice

There are three main pieces working together:

### 1. Copilot Studio — The Front Door

This is what your team sees and interacts with. They can ask questions in plain English — things like *"What's happening with Harris Federation?"* or *"Show me this week's procurement signals"* — and Copilot Studio works out which service to call to get the answer. It lives inside Teams, so there's nothing new for your team to learn.

### 2. Salesforce Integration

Copilot Studio connects to your Salesforce platform via a **Salesforce connector**, allowing the agent to query accounts, search opportunities, and pull back relevant CRM data without your team needing to context-switch between applications.

For documents stored within Salesforce, we can use **SharePoint HTTP request connectors within Power Platform** to retrieve those files and surface them alongside the intelligence the agent produces. This means your team gets a joined-up view — market signals enriched with your own CRM data and documents — all in one place.

### 3. Signal Analyst — The Intelligence Engine

This is a custom-built tool that runs behind the scenes. It's what we call a "pro-code" component — purpose-built to do things that off-the-shelf connectors can't easily handle:

- **Automated scanning** of UK procurement portals, Companies House filings, competitor websites, and education sector news
- **Enrichment** of raw signals with financial data, officer changes, and trust structure information
- **Classification** into actionable categories (procurement shifts, leadership changes, competitor movements, etc.)
- **Report generation** — professional Word documents with summaries, recommended actions, and competitive talk tracks

Copilot Studio connects to the Signal Analyst seamlessly, so from your team's perspective it's just another thing the agent knows how to do.

### Morning Automation

We've also built in a **daily trigger** — each morning, the system automatically generates a fresh intelligence report and emails it out to your nominated stakeholders. No manual steps required.

## Tools & Services at a Glance

| Tool / Service | What It Does |
|----------------|-------------|
| **Microsoft Copilot Studio** | Conversational AI orchestrator — the single front door for your team |
| **Salesforce MCP Connector** | Query and search accounts, opportunities, and contacts in your CRM |
| **SharePoint HTTP Request Connector** | Retrieve documents stored within Salesforce via Power Platform |
| **Playwright (Headless Browser)** | Automated browsing of procurement portals, competitor sites, and education news |
| **Companies House API** | Look up trust financials, officer changes, and filing history |
| **Contracts Finder API** | Pull live UK government procurement notices |
| **Azure OpenAI (GPT-4o)** | Parse raw data into structured signals, generate summaries and talk tracks |
| **Azure Blob Storage** | Host generated Word and PDF reports with secure download links |
| **Microsoft 365 (via Copilot Studio)** | Send emails, post to Teams, create Planner tasks, book meetings |
| **Power Automate (Morning Trigger)** | Automatically generate and distribute the daily intelligence report |

## Next Steps

I'm more than happy to set up a follow-up call to walk through this in more detail, answer any questions, and do a live demo of the solution in action. Just let me know what works for your diary and I'll get something booked in.

Looking forward to hearing your thoughts.

Best regards,
Graham
