# Hyper-Agent

**Chief test agent** — an AI employee that shadows the Test Manager: vendor oversight (e.g. TCS), delivery collaboration, daily orchestration.

---

## What it is

Hyper-Agent is a private repo for building an AI test architect that acts as your context keeper, evidence gatherer, and draft producer so you can focus on directing vendors, aligning with delivery, and making the calls only you can make.

## Vision

The product vision and how the agent supports a Test Manager’s daily work is documented for review:

**[→ Vision: AI Test Architect / Shadow](docs/VISION-ai-test-architect.md)**

Covers: daily brief & meeting prep, vendor (TCS) oversight, delivery collaboration, decision support, governance, and your “second brain.”

### Capability diagram

```mermaid
flowchart TB
    subgraph agent["Hyper-Agent: AI Test Architect / Shadow"]
        CORE["Context keeper · Evidence gatherer · Draft producer"]
    end

    subgraph daily["1. Daily orchestration & focus"]
        direction TB
        D1["Morning brief"]
        D2["Priority stack"]
        D3["Meeting prep"]
    end

    subgraph vendor["2. Vendor (TCS) oversight"]
        direction TB
        V1["Commitment vs actuals"]
        V2["Single view"]
        V3["Escalation support"]
        V4["Consistency"]
    end

    subgraph delivery["3. Delivery collaboration"]
        direction TB
        L1["Scope ↔ test alignment"]
        L2["Release readiness"]
        L3["Communication"]
    end

    subgraph decision["4. Decision support"]
        direction TB
        S1["Go/no-go evidence"]
        S2["Prioritization"]
        S3["Impact of changes"]
    end

    subgraph gov["5. Governance & consistency"]
        direction TB
        G1["Standards"]
        G2["Patterns"]
    end

    subgraph brain["6. Second brain"]
        direction TB
        B1["Status on demand"]
        B2["Your preferences"]
    end

    CORE --- daily
    CORE --- vendor
    CORE --- delivery
    CORE --- decision
    CORE --- gov
    CORE --- brain
```

*Full diagram set:* [docs/DIAGRAM-capabilities.md](docs/DIAGRAM-capabilities.md)

## Next steps

**[→ Recommended next steps](docs/NEXT-STEPS.md)** — first capability, data and tools, form factor, tech baseline, and how to build the first slice.

---

## Repo

- **Private** — your space to design and build the agent.
- **Status** — vision documented; implementation to follow.
