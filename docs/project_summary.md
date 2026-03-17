# Sinovation 2026 — Team 8 Project Summary
## AI-Powered Car Park Monitoring for China Hong Kong City

**Last updated:** 2026-03-17

---

## 1. Competition Overview

| Field | Detail |
|---|---|
| Program | SINO x HKUST Sinovation 2026 |
| Organizers | HKUST (Sustainable Smart Campus), Sino Group, HKSTP |
| Team | Team 8 — "CHKC Team" |
| Project | AI-powered loading bay monitoring at China Hong Kong City (中港城), TST |

### Judging Criteria

| Criteria | Weight |
|---|---|
| Feasibility | 30% |
| Cost-effectiveness | 30% |
| Innovativeness | 30% |
| Presentation skills | 10% |
| Teamwork (bonus) | 10% |

### Timeline

| Date | Event | Status |
|---|---|---|
| 2026-01-09 | Project Kickoff + Design Thinking Workshop | Done |
| 2026-02-04 | Site visit to CHKC | Done |
| 2026-02-06 | Workshop 2 at HKSTP | Done (team absent) |
| 2026-02-13 | Team meeting — aligned on car park project | Done |
| 2026-03-10 | Workshop 3 at HKPC | Done |
| 2026-03-17 | 1-on-1 with Prof. Kenneth Leung (SUST Director) | Done |
| **2026-04-30** | **Submission: 3-5 min video + 15-page deck + prototype** | **44 days** |
| 2026-05-14 | Judging by Sino management (10 min Q&A, online) | Upcoming |
| 2026-06-04 | Award Ceremony (1 hour) | Upcoming |

### Deliverables (April 30)

1. **Video**: 3-5 minutes
2. **Deck**: 15 pages max
3. **Prototype**: working demo (if available)

---

## 2. Team

### Student Team (Competitors)

| Name | Role | Status |
|---|---|---|
| **Andy Yung (Ka Shing)** | AI/Tech Lead — sole developer | Active, paying out of pocket |
| **Sharon Wun (Suet Ling)** | Business/Coordination, Sino liaison | Largely unresponsive |
| **Florence Siu (Xiao Fenglin)** | Data/BI/Presentation | Largely unresponsive |

### Sino Group

| Name | Title |
|---|---|
| Ellen Lim | AGM, Innovation, Sino Group |
| Elvin (E.Man) | CHKC on-site staff, provides CCTV footage |

### HKUST Program Admin

| Name | Role | Contact |
|---|---|---|
| Hanna Jepps | Program manager, main liaison | hannajepps@ust.hk |
| Clara Wong | Assistant manager, budget/reimbursement | clarawong@ust.hk |
| Prof. Kenneth Leung | SUST Director | — |
| Marcus Leung-Shea | Assistant Director | — |
| Plato Ho | SUST coordinator | — |

### HKSTP Mentor

| Name | Role |
|---|---|
| Edmond Lam | Technical mentor |

---

## 3. The Problem

### Situation
China Hong Kong City has a loading bay / car park area that **cannot install barriers** due to fire safety regulations. Currently, **two security guards work in shifts (24/7)** to manually monitor trucks, record parking duration, and collect fees.

### Pain Points
- **Cost**: 2 guards × HK$20,000/month = **HK$480,000/year** for manual monitoring
- **Manual process**: Guards use stopwatch / manual records — no data, no accountability
- **No historical data**: Zero records of past transactions, vehicle patterns, or fee collection
- **No barriers**: Cannot physically block vehicles → enforcement relies entirely on human presence

### Rules
- **20-minute free parking** — timer starts when vehicle enters
- Overtime charged per occurrence (exact rate TBD)
- Trucks go to loading bay; private cars go to parking lot (different directions)

---

## 4. Solution Strategy

### Kenneth Leung's Framework: "Workflow First, Then Automate"

> "This is a business management problem, not a coding problem."

#### Phase 1 — Registration Mandate (Month 1)
- Station a guard at the gate
- Force all incoming vehicles to register: plate number + payment method
- Could attach to Sino's existing property app (TBD if they have one)
- Property owner's right to enforce rules

#### Phase 2 — AI Automation Kicks In
- ALPR camera detects plate → database lookup
- **Registered vehicle**: auto-log entry/exit, calculate duration, auto-charge if >20 min, send report
- **Unregistered vehicle**: real-time WhatsApp alert to nearest security group → dispatch someone

#### Phase 3 — Progressive Human Reduction
- Over time, most vehicles registered → alerts decrease
- Guard shifts can be reduced or eliminated
- System becomes self-sustaining

#### Phase 4 — Data Analytics (Value-Add)
- Average parking duration per vehicle
- Repeat offenders (consistently exceed free period)
- Peak usage patterns (confirmed: weekdays 10am-4pm)
- Vehicle type vs. parking behavior
- Revenue reporting and accounting

### Edmond's Input: "Lean into AI Innovation"
- Don't get stuck on implementability — emphasize innovative AI concepts
- Balance with Kenneth's practical workflow for a compelling pitch

### Pitch Formula
```
Problem (省钱) → Workflow (how it works step by step)
→ Which steps AI automates → Progressive cost reduction
→ Data analytics bonus → ROI: HK$480K/yr saved vs HK$23K system cost
```

---

## 5. Technical Stack (Current)

### ALPR Pipeline
- **Detection**: fast-alpr (YOLO v9 + ONNX) — local processing
- **Validation**: HK plate regex (`[A-HJ-NP-Z]{1,2}\s?[0-9]{1,4}`)
- **Deduplication**: temporal tracking + edit distance + confusion map
- **Storage**: SQLite (raw detections + plate sessions)
- **Web UI**: FastAPI + Jinja2 dashboard

### CHKC Infrastructure (Existing)
- **Cameras**: Bosch + Sony (10 models), including GF15-18 covering the car park
- **NVR**: VidoNet (8/16/32 ch, with face recognition)
- **VMS**: iNEX Video Management System
- **Network**: Allied Telesis PoE + L3 managed switches

### Camera Assessment

| Camera | Location | Quality | Notes |
|---|---|---|---|
| GF15 | Main entrance/exit | Good | Primary. Cars drive fast — challenge |
| GF16 | Secondary entrance | Good | Clean reads |
| GF17 | Internal lane (cargo lift) | Poor | Too far from plates, low traffic |
| GF18 | Internal lane | Noisy | Dominated by one parked vehicle |

---

## 6. Budget

### Allocation: HK$27,500 per team

### Actual Spend (as of 2026-03-17)

| Item | Cost | HKD Equiv. |
|---|---|---|
| Claude Max 20x (3 months) | USD $250 | ~$1,950 |
| OpenRouter API topup | USD $10.8 | ~$84 |
| Tencent Cloud | RMB 42 | ~$46 |
| **Total spent** | | **~$2,080** |

### Remaining Budget: ~HK$25,400

### Planned Spending

| Category | Purpose | Est. Cost |
|---|---|---|
| Cloud server upgrade | Real-time CCTV processing, RTSP stream | TBD |
| Database (cloud) | Store detections, vehicle registry, billing | TBD |
| AI API credits | Plate Recognizer / GPT / Claude API | TBD |
| GPT Plus/Pro | AI-assisted development + analysis | TBD |

### Budget Strategy
- Prioritize cloud credits / subscriptions / API topups (value persists after competition)
- Avoid hardware purchases (must be returned to HKUST)
- All expenses need receipts + relevance justification for reimbursement

---

## 7. Open Questions (For Sino)

| # | Question | Impact |
|---|---|---|
| 1 | Are the 2 guards **exclusively** for the loading bay, no other duties? | Validates HK$480K/yr savings |
| 2 | Which camera distinguishes trucks (loading bay) vs. cars (parking lot)? | Prototype scope |
| 3 | What % of vehicles are regular/repeat vs. one-time? | Registration model viability |
| 4 | Does Sino have a property management app? Can we add features? | Integration approach |
| 5 | What were previous vendor proposals? Why rejected? Pricing? | Competitive positioning |
| 6 | Frequency of fare evasion / disputes? | Pain point severity for pitch |

---

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Teammates unresponsive — video/deck may fall on Andy | High | Email paper trail, escalate to Hanna if needed |
| Out-of-pocket expenses not reimbursed | High | Email Hanna/Clara with itemized list, get written confirmation |
| ALPR accuracy in poor conditions (GF17/18) | Medium | Focus demo on GF15/16, acknowledge limitations |
| No historical baseline data for comparison | Medium | Frame as: "our system creates the data for the first time" |
| Registration model may not work if mostly one-time vehicles | Medium | Clarify with Sino; design for both scenarios |
