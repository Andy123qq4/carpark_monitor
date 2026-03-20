# Plate Recognizer Platform Reference

> Last updated: 2026-03-20. Source: [platerecognizer.com](https://platerecognizer.com), [parkpow.com](https://parkpow.com)

## Product Overview

| Product | What it does | Relevance to CHKC |
|---|---|---|
| **Snapshot API** | Send image → get plate text + confidence | Currently using (hybrid mode) |
| **Stream** | Process live RTSP feeds in real-time | Could replace our processor.py entirely |
| **ParkPow** | Parking management dashboard + alerts | Directly solves CHKC's billing/tracking problem |
| **Snapshot SDK** | On-premise ALPR (no cloud needed) | Privacy-friendly deployment option |
| **Detection Zones** | Mask regions in camera view | Ignore parked cars, focus on entry/exit lane |
| **VMS Integrations** | Connect to Milestone, Blue Iris, Network Optix, etc. | CHKC uses iNEX — no direct integration yet |
| **Webhooks** | Push plate events to external systems | Real-time alerts to security staff |

## Pricing

### Snapshot API (what we use)

| Tier | Cost | Lookups/month |
|---|---|---|
| **Free** | $0 | 2,500 |
| Small | $50/mo | 50,000 |
| Medium | $150/mo | 250,000 |
| Large | $250/mo | 500,000 |

- Vehicle Make/Model/Color (MMC) add-on: +50% on subscription
- Annual billing saves 2 months
- No credit card required for free tier

### Stream (real-time RTSP)

| Tier | Cost | Coverage |
|---|---|---|
| **Free** | $0 | 3 cameras × 1 month |
| Stream | $35/mo/camera | Plate only |
| Stream + MMC | $45/mo/camera | + Make, Model, Color, Direction, Dwell Time |

### ParkPow (parking management)

| Tier | Cost |
|---|---|
| **Free** | 3 cameras × 1 month |
| Standard | $20/mo/camera |

## Stream — Real-Time ALPR

Processes live RTSP camera feeds without our custom pipeline.

**Deployment options:**
- Cloud (Plate Recognizer hosted)
- Your cloud (self-hosted)
- On-premise (no internet required) — Linux, Windows, Jetson, Raspberry Pi

**Detection capabilities:**
- License plate text + confidence
- Vehicle type (sedan, SUV, truck, motorcycle, bus, van)
- Make, Model, Color identification
- **Dwell time** — how long vehicle stays in frame
- **Direction of travel** — angular measurement
- **Vehicle orientation** — front vs rear (entry vs exit)

**Output:** Webhooks (JSON), CSV, JSON files

**Detection Zones:** Define areas in camera view via PNG mask. Black = ignore, white = detect. Useful to focus on entry/exit lane and ignore parked vehicles.

### Stream vs Our Current Pipeline

| Feature | Our pipeline (processor.py) | Stream |
|---|---|---|
| Input | MP4 files (batch) | Live RTSP feeds (real-time) |
| Detection | YOLO v9 local | Plate Recognizer's model |
| OCR | Hybrid (local + API) | Built-in |
| Dwell time | Calculated in db.py (SQL window) | Built-in |
| Direction | Not implemented | Built-in |
| Alerts | Not implemented | Webhooks |
| Cost | API calls only | $35-45/camera/month |
| Offline | Yes | On-premise: yes |

**For competition:** Our custom pipeline shows technical depth (innovativeness score). Stream shows a viable production deployment path (feasibility score). Present both.

## ParkPow — Parking Management Dashboard

Directly solves CHKC's business problem. Pre-integrated with Stream.

**Core features:**
- **Activity dashboard** — vehicle counts, occupancy charts, drill-down by time
- **Vehicle CRM** — track complete history per plate across all cameras
- **Occupancy monitoring** — who's in the lot now, how long they've stayed
- **Dwell time tracking** — flag vehicles over 20-minute free parking limit
- **Custom alerts** — notify when vehicle exceeds time limit, specific plates enter, vehicles still onsite after hours
- **Alert channels** — email, Slack, MS Teams, Google Chat, SMS, MQTT
- **Vehicle tags** — categorize as Employee, Visitor, Registered, Blacklisted
- **Custom metadata** — up to 6 fields per vehicle (company, department, contact)
- **Bulk import** — upload spreadsheets of registered vehicles
- **Advanced search** — partial plate, vehicle color/type, time range, location
- **Reports** — occupancy rates, frequency analytics, data export (API or spreadsheet)
- **Multi-site** — manage multiple locations from one dashboard
- **365-day history**

### ParkPow vs CHKC Requirements

| CHKC Need | ParkPow Feature | Status |
|---|---|---|
| Track truck entry/exit times | Dwell time + orientation | Built-in |
| 20-min free parking enforcement | Custom alert: "vehicle stayed > 20 min" | Built-in |
| Overtime fee collection | Alert → manual charge (or API integration) | Partial — no payment |
| Reduce security guard workload | Automated detection + alerts | Built-in |
| Registered vehicle whitelist | Vehicle tags + bulk import | Built-in |
| Reporting for management | Occupancy reports + data export | Built-in |

## Additional Products

| Product | What | Relevance |
|---|---|---|
| **Blur** | Anonymize plates/faces in images | Privacy compliance for stored footage |
| **Ship. Container** | Read container codes (BIC/ISO) | Not relevant |
| **USDOT** | Read US DOT numbers on trucks | Not relevant (HK) |
| **VIN ID** | Read Vehicle Identification Numbers | Not relevant |
| **OCR** | General text recognition | Not relevant |
| **PeopleTracker** | People counting/tracking | Could count pedestrians in loading bay |
| **VisionAlert** | Alert system for visual events | General alert capabilities |

## API Details

**Endpoint:** `POST https://api.platerecognizer.com/v1/plate-reader/`

**Key parameters:**
- `regions`: `hk` (Hong Kong)
- `upload`: image file (JPEG/PNG)
- `camera_id`: optional camera identifier
- `mmc`: `true` to get Make/Model/Color (requires paid add-on)

**Response fields:**
- `plate`: recognized text
- `score`: OCR confidence (0-1)
- `dscore`: detection confidence (0-1)
- `box`: bounding box coordinates
- `region.code`: detected region
- `vehicle.type`: vehicle classification
- `candidates`: alternative readings with scores

**Rate limits:** 429 status on rate limit exceeded. Our code retries with exponential backoff.

**Important:** API needs surrounding context to detect plates in images. Tight plate-only crops often return empty results. Use 100px padding around the plate bbox, or send wider scene crops.

## Account Info

- **Account:** nustemporary@outlook.com
- **Plan:** Free tier (2,500 lookups/month)
- **Dashboard:** https://app.platerecognizer.com/
- **Signup (self-serve, no credit card):**
  - Plate Recognizer: https://app.platerecognizer.com/accounts/signup/
  - ParkPow: https://app.parkpow.com/accounts/signup/

## How to Trial Without CHKC Camera Access

No need for live RTSP access to CHKC cameras. Options:

| Method | What | Effort |
|---|---|---|
| **Snapshot API (current)** | Upload crops via hybrid pipeline — already working | Done |
| **Dashboard upload** | Drag-and-drop images via "Upload Image" tab in web dashboard | Zero |
| **Stream with MP4** | Feed existing GF15-18 MP4 files via FFmpeg fake RTSP | 5 min |
| **Webcam/phone** | Point at any car in a parking lot | 5 min |

FFmpeg fake RTSP command (simulate live feed from video file):
```bash
ffmpeg -re -stream_loop -1 -i "video/GF15 20260212 142142-145519.mp4" -c copy -f rtsp rtsp://localhost:8554/cam1
```

**For competition:** No need to trial Stream/ParkPow. The hybrid pipeline already demonstrates the capability. Reference Stream + ParkPow in the proposal as the "production deployment path" with pricing.

## Technical Findings

### API Crop Requirement

Plate Recognizer API's internal plate detector needs surrounding context. Sending tight plate-only crops (just the plate pixels) returns empty results in ~70% of cases.

| Approach | API detection rate |
|---|---|
| Tight crop (4px padding) | 17/24 (71%) — 7 returned None |
| Tight crop + gray border padding | 5/5 (100%) — works but artificial |
| **Wide crop (100px real context)** | **20/24 (83%)** — recommended |

Wide crop = real surrounding pixels from the frame. Gray padding works too but wide crop is more natural and aids visual verification.

### Temporal Dedup Finding

Moving vehicles shift ~30-50px per frame, causing bbox IoU to drop below matching thresholds. OCR text also varies frame-to-frame. A simple **3-second temporal window** (if any detection occurs within 3s, merge into same cluster) reduced 62 → 24 detections for a 33.5-min video without losing any unique plates.

## Recommendations for CHKC Proposal

1. **Demo phase (now):** Continue with hybrid pipeline (free tier, 2,500 calls/month is plenty for demo videos)
2. **Pilot phase:** Stream free trial (3 cameras × 1 month) + ParkPow free trial — can test with MP4 files, no camera access needed
3. **Production phase:** Stream + ParkPow

### Production Cost Comparison

| Item | Monthly (4 cameras) | Annual | Annual (with 2-month discount) |
|---|---|---|---|
| Stream | $140 (HK$1,092) | $1,680 (HK$13,104) | $1,400 (HK$10,920) |
| ParkPow | $80 (HK$624) | $960 (HK$7,488) | $800 (HK$6,240) |
| **Total** | **$220 (HK$1,716)** | **$2,640 (HK$20,592)** | **$2,200 (HK$17,160)** |
| **Current (2 guards)** | **HK$40,000** | **HK$480,000** | **HK$480,000** |
| **Savings** | | | **HK$462,840/year (96%)** |
