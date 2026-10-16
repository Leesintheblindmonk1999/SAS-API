# SAS — Symbiotic Autoprotection System

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19702379.svg)](https://doi.org/10.5281/zenodo.19702379)
[![Tribunal v1.1.0](https://img.shields.io/badge/Tribunal-v1.1.0-purple)](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)
[![R3.1 Guard](https://img.shields.io/badge/R3.1_Guard-F1_0.833-orange)](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)
[![R0 Audit](https://img.shields.io/badge/R0%20Audit-Zenodo%2020647532-blueviolet)](https://zenodo.org/records/20647532)
[![R1-D](https://img.shields.io/badge/R1--D-Zenodo%2021282332-blueviolet)](https://zenodo.org/records/21282332)
[![R2.1](https://img.shields.io/badge/R2.1-Zenodo%2021365707-blueviolet)](https://doi.org/10.5281/zenodo.21365707)
[![Landing Page](https://img.shields.io/badge/%F0%9F%8C%90-Landing_Page-0a0e17?style=flat&logo=github)](https://leesintheblindmonk1999.github.io/sas-landing/)
[![API Online](https://img.shields.io/badge/API-online-brightgreen)](https://sas-api.onrender.com)
[![PyPI](https://img.shields.io/pypi/v/sas-client?label=sas-client&color=blue)](https://pypi.org/project/sas-client/)
[![npm](https://img.shields.io/npm/v/sas-audit-client?label=sas-audit-client&color=red)](https://www.npmjs.com/package/sas-audit-client)
[![API Docs](https://img.shields.io/badge/API-FastAPI-009688)](https://sas-api.onrender.com/docs)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](requirements.txt)
[![License](https://img.shields.io/badge/license-GPL--3.0%20%2B%20Durante%20Invariance-blue)](LICENSE.md)
[![Status](https://img.shields.io/badge/status-production%20v1.1.0-brightgreen)](#scope-and-limitations)
[![Tribunal Benchmark](https://img.shields.io/badge/Tribunal-99.17%25_accuracy-brightgreen)](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)
[![Precision](https://img.shields.io/badge/Precision-100%25-success)](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)
[![OTS Proof](https://img.shields.io/badge/OpenTimestamps-proof-blueviolet)](docs/benchmark_complete_20260429_172647.json.ots)

**SAS — Symbiotic Autoprotection System** is an open-source structural coherence auditing system. It classifies (source, response) text pairs into **3 structural zones** using the **SAS Multimetric Tribunal v1.1.0**: 7 detection modules with cascading multiplicative penalty, plus an optional **R3.1 Differential Guard**.

> **Production status:** v1.1.0 — The multimetric tribunal is the current core engine. The legacy pipeline (TDA + NIG + E9–E12) remains available at `/v1/diff` for backward compatibility and reproducibility of published benchmarks. New integrations should use `/v2/audit`.

---

## Quick Start — 30 seconds

No API key, no registration:

```bash
curl -X POST https://sas-api.onrender.com/public/demo/audit \
  -H "Content-Type: application/json" \
  -d '{
    "source": "The Eiffel Tower is in Paris, France. It was built in 1889.",
    "response": "The Eiffel Tower is in Berlin, Germany. It was built in 1950."
  }'
```

Expected response:

```json
{
  "status": "ok",
  "isi": 0.041,
  "kappa_d": 0.56,
  "kappa_r": 0.15,
  "verdict": "MANIFOLD_RUPTURE",
  "zone": "F-S",
  "fired_modules": ["source_target_guard", "negation_penalty"],
  "demo": true
}
```

Or from the CLI:

```bash
pip install sas-client
sas demo-audit "The Eiffel Tower is in Paris, France." "The Eiffel Tower is in Berlin, Germany."
```

---

## SAS Multimetric Tribunal v1.1.0

The **SAS Multimetric Tribunal** is the core classification engine. It evaluates (source, response) pairs through **7 detection modules** with cascading multiplicative penalty, producing an **Invariant Similarity Index (ISI)** that determines the structural zone.

Full repository: [https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)

### Architecture

```text
ISI_HARD  = min(lexical_baseline, source_target_guard, cre_isi)
ISI_FINAL = ISI_HARD × Π(penalties from fired modules)
```

### 7 Detection Modules

| # | Module | Function | Weight |
|---|--------|----------|--------|
| 1 | `lexical_baseline_score` | Jaccard lexical overlap | 0.35 |
| 2 | `source_target_guard` | Critical entity mutation detection | 0.25 |
| 3 | `flow_penalty` | Semantic flow rupture | 0.12 |
| 4 | `negation_penalty` | Logical inversions | 0.08 |
| 5 | `cre_isi` | Ricci semantic curvature | 0.12 |
| 6 | `arithmetic_penalty` | Arithmetic errors | 0.04 |
| 7 | `reference_penalty` | Reference fabrication | 0.04 |

### R3.1 Differential Guard (Optional)

| Component | Function |
|-----------|----------|
| **Grounding** | Recall of response content words against source |
| **Compression Ratio** | Abstains when response >50% shorter than source |
| **Short-Response Heuristics** | Polarity inversion, isolated entity, stopword grounding |

### Structural Zones

| Zone | Code | ISI Range | Risk | Action |
|------|------|-----------|------|--------|
| **STRUCTURAL COLLAPSE** | **F-S** | ISI < κR (0.15) | CRITICAL | Block / Escalate |
| **RECOVERABLE RUPTURE** | **B** | κR ≤ ISI < κD (0.56) | HIGH | Review / Flag |
| **COHERENT** | **A** | ISI ≥ κD (0.56) | LOW | Pass |

### Benchmark (v6)

| Metric | Core Tribunal (1,800 pairs) | + R3.1 Guard (N1 audit) | FinQA Cross-Query |
|--------|-----------------------------|------------------------|-------------------|
| **F1 Score** | **98.99%** | **0.833** | **87.0%** detection |
| **Precision** | **100.00%** (0 false positives) | — | — |
| **Accuracy** | **99.00%** | — | — |
| **ISI Separation** | **0.8323** | — | — |
| **Corpora** | halueval_dialogue, halueval_qa, truthfulqa | N1 (1,800 × 4 conditions) | financiero_finqa (1,657 pairs) |

**Paper v6 (Qeios):** DOI 10.32388/T420IV — Round 4, Clarity 5/5  
**Supplement:** SAS_v6_Supplements.zip (26 files, SHA-256 verified)

---

## API Endpoints

### Tribunal (v2 — Current)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/v2/audit` | API Key | Full multimetric tribunal analysis (7 modules + optional R3.1 Guard) |

### Legacy (v1 — Backward Compatible)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/diff` | API Key | Forensic diff between two texts (TDA + NIG + E9–E12 pipeline) |
| `POST` | `/v1/audit` | API Key | Structural audit (single text) |
| `POST` | `/v1/batch` | API Key | Batch structural audit (multiple pairs per request) |
| `POST` | `/v1/chat` | API Key | Chat endpoint with SAS filtering |

### Public (No Auth Required)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/readyz` | Granular router and database readiness |
| `GET` | `/integrity` | Technical and legal provenance certificate |
| `POST` | `/public/demo/audit` | Public source-vs-response forensic demo |
| `GET` | `/public/stats` | Anonymized aggregate usage stats |
| `GET` | `/public/activity` | Anonymized activity feed |
| `GET` | `/public/request-key` | Free API key onboarding instructions |
| `POST` | `/public/request-key` | Free API key by email (automatic delivery) |
| `GET` | `/public/interaction/stats` | Aggregate interaction stability stats |

### Account

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/v1/whoami` | API Key | Plan, quota, and key identity |

### Experimental

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/v1/interaction/stability/example` | None* | Experimental demo payload |
| `POST` | `/v1/interaction/stability` | API Key | Experimental interaction stability analysis |

> \* Feature-flag controlled. Returns 503 if `ENABLE_INTERACTION_STABILITY` is not set.

---

## Get a Free API Key

```bash
sas request-key --email you@example.com --name "Your Name"
```

Free keys are delivered by email automatically. Then:

```bash
export SAS_API_KEY="sas_xxxxxxxxxxxxxxxxxxxxx"
sas whoami
sas diff "The contract is governed by Argentine law." \
         "The contract is NOT governed by Argentine law."
```

Hosted Free plan: **50 requests/day**, no credit card.

---

## Official Clients and SDKs

| Client | Package | Runtime | Status |
|---|---|---|---|
| **sas-multimetric-tribunal** (core engine) | [GitHub](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal) | Python 3.10+ | **v1.1.0** — 7 modules + R3.1 Guard |
| Python CLI / client | [`sas-client`](https://pypi.org/project/sas-client/) | Python 3.10+ | Published on PyPI |
| Node.js / TypeScript SDK | [`sas-audit-client`](https://www.npmjs.com/package/sas-audit-client) | Node.js 18+ | Published on npm |

### Python Client

```bash
pip install sas-client
```

```python
from sas_client import SASClient

client = SASClient(api_key="YOUR_API_KEY")

# Tribunal analysis (v2)
result = client.tribunal(
    source="Python is a programming language used for data analysis.",
    response="A python is a large tropical snake."
)

print(result["isi"])
print(result["verdict"])
print(result["zone"])
print(result.get("evidence", {}).get("fired_modules"))
```

### Node.js / TypeScript SDK

```bash
npm install sas-audit-client
```

```js
import { SASClient } from "sas-audit-client";

const client = new SASClient({ apiKey: process.env.SAS_API_KEY });

const result = await client.diff({
  textA: "The Eiffel Tower is located in Paris, France, and was completed in 1889.",
  textB: "The Eiffel Tower is located in Berlin, Germany, and was completed in 1950.",
});

console.log(result.verdict);
console.log(result.isi);
```

---

## Legacy Pipeline (v1 — TDA + NIG + E9–E12)

The original SAS pipeline remains available at `/v1/diff` for backward compatibility and reproducibility of published benchmarks. It uses:

| Component | Function |
|---|---|
| **TDA** | Topological Data Analysis — persistent homology H₀ + H₁, Wasserstein distance |
| **NIG** | Numerical Invariance Guard — detects year, quantity, and measurement mutations |
| **SourceTargetGuard** | Detects critical source-response mutations: locations, entities, dates |
| **E9** | Logical contradiction detection |
| **E10** | Fact grounding — unsupported claims vs. source |
| **E11** | Temporal inconsistency detection |
| **E12** | Abrupt topic-shift detection |

Legacy pipeline:

```text
Source text A + Response text B
        |
        v
[Layer 0]  Lexical Overlap Guard
[Layer 1]  TDA: Persistent Homology H0 + H1  ->  ISI_TDA
[Layer 2]  NIG: Numerical Invariance Guard    ->  ISI_NIG
[Core]     ISI_HARD = min(ISI_TDA, ISI_NIG)
[SAS]      E9-E12 + SourceTargetGuard         ->  module penalties
        |
        +-- ISI_FINAL >= 0.56  ->  COHERENT
        +-- ISI_FINAL <  0.56  ->  MANIFOLD_RUPTURE
```

> **Note:** New integrations should use `/v2/audit` (tribunal). The v1 pipeline is maintained for reproducibility of published benchmarks but is superseded by the multimetric tribunal.

---

## Research Releases

### R0 Baseline Stability Audit

The R0 audit validates the research pipeline infrastructure and baseline stability.

**Zenodo:** [https://zenodo.org/records/20647532](https://zenodo.org/records/20647532)

**Corpus scale** — A local benchmark scan identified 152,525 complete A/B hallucination pairs across 12 strata:

| Corpus/category | Complete pairs |
|---|---:|
| `halogen/biographies` | 9,362 |
| `halogen/code` | 15,190 |
| `halogen/historical_events` | 21,008 |
| `halogen/numerical_falsepresupposition` | 15,168 |
| `halogen/rationalization_binary` | 21,000 |
| `halogen/rationalization_numerical` | 14,274 |
| `halogen/references` | 24,918 |
| `halueval_dialogue/direct` | 10,000 |
| `halueval_general/direct` | 815 |
| `halueval_qa/direct` | 10,000 |
| `halueval_summarization/direct` | 10,000 |
| `truthfulqa/direct` | 790 |

**Stratified R0 runs:**

| Run | Records | Pairs/category | Train/Test | Minimal F1 | Full F1 |
|---|---:|---:|---:|---:|---:|
| `sample_strat_2400` | 2,400 | 100 | 1,800 / 600 | 0.742 | 0.738 |
| `sample_strat_4800` | 4,800 | 200 | 3,600 / 1,200 | 0.743 | 0.741 |
| `sample_strat_12000` | 12,000 | 500 | 9,000 / 3,000 | 0.742 | 0.740 |

> **Note:** These R0 results use clean-self controls (source = A_clean, response = A_clean), which can inflate performance for dissimilarity-based modules. They validate infrastructure and baseline stability, not production-grade hallucination detection. The current production engine is the multimetric tribunal (v1.1.0), which uses a fundamentally different architecture.

### R1-D — Structural Evaluation over Declarative Corpus

Flow + CRE + Negation composite on halueval_qa: test F1 = 0.5230, precision = 0.5617, recall = 0.4892, accuracy = 0.5538.

**Zenodo:** [https://doi.org/10.5281/zenodo.21282332](https://doi.org/10.5281/zenodo.21282332)

### R2.1 — Structural Code Hallucination Detection via AST Fingerprinting

AST structural comparison against a reference implementation: AUC 0.9141 (raw) / 0.9421 (length-confound-controlled) on a 1,596-row execution-verified corpus.

**Zenodo:** [https://doi.org/10.5281/zenodo.21365707](https://doi.org/10.5281/zenodo.21365707)

---

## Batch Auditing

The API supports batch processing of multiple source/response pairs in a single request via `/v1/batch`. Each pair is evaluated independently, and the response includes per-pair ISI, verdict, and fired modules. Batch mode is available on Pro and higher plans.

---

## Experimental: Interaction Stability Auditing

SAS includes an experimental module for temporal interaction stability analysis (`/v1/interaction/stability`). It uses a heuristic hidden-state model to track belief entropy, demand history, and structural stability across conversational turns. This is a research feature, feature-flag controlled.

**Research line DOI:** `10.5281/zenodo.20335612`

---

## Self-Hosting

SAS can be self-hosted. The API is a standard FastAPI application.

### Docker

```bash
docker build -t sas-api .
docker run -p 8000:8000 -e SAS_API_KEY=your_key sas-api
```

### Local Python

```bash
git clone https://github.com/Leesintheblindmonk1999/SAS-API.git
cd SAS-API
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Hosted API Plans

SAS is open source under **GPL-3.0 + Durante Invariance License**. The following plans refer to the hosted SAS API service.

| Plan | Usage / Features | Price |
| :--- | :--- | :--- |
| **SAS Free** | 50 requests/day. API key authentication. Individual testing and evaluation. | **Free** |
| **SAS Developer / Pro** | 10,000 requests/month. Hosted API access, API key, basic email support. | **USD 99/month** |
| **SAS Team** | 50,000 requests/month. Team usage, priority support, internal validation workflows. | **USD 299/month** |
| **SAS Enterprise Cloud** | High-volume usage or custom request package. Direct support, private integration, SLA by agreement. | **From USD 1,500/month** |
| **SAS On-Premise License** | Private deployment in customer infrastructure. Commercial license, implementation support, internal integration. | **From USD 15,000/year** |
| **Technical Pilot** | Initial audit, guided integration, technical report, and validation on customer-specific cases. | **USD 1,500–3,000 one-time payment** |

> **Enterprise & On-Premise:** The multimetric tribunal (R0→R1 transition) is complete and deployed as `sas-multimetric-tribunal` v1.1.0. SLA-backed commitments are available.

📧 **Commercial inquiries:** [duranteg2@gmail.com](mailto:duranteg2@gmail.com)

---

## Ecosystem

### Production

- **[sas-multimetric-tribunal](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)** — Core classification engine v1.1.0 with R3.1 Differential Guard (7 modules, 3-zone structural classification)
- **[SAS-API](https://github.com/Leesintheblindmonk1999/SAS-API)** — This repository: hosted API service
- **[sas-landing](https://leesintheblindmonk1999.github.io/sas-landing/)** — Interactive landing page with live demo
- **[sas-client](https://pypi.org/project/sas-client/)** — Python SDK / CLI
- **[sas-js](https://www.npmjs.com/package/sas-audit-client)** — Node.js / TypeScript SDK
- **[Project_Manifold_056](https://github.com/Leesintheblindmonk1999/Project_Manifold_056)** — Research artifact repository and reproducibility archive

### Research Core

- **[Omni_Scanner](https://github.com/Leesintheblindmonk1999/Omni_Scanner)** — Hallucination detection engine (TDA + NIG). Validated on 156,215 real pairs.
- **[Ontological_AI](https://github.com/Leesintheblindmonk1999/Ontological_AI)** — Library for ontological density, transfer entropy, and spectral signature research.

### Publications

| Publication | DOI / Link | Status |
|---|---|---|
| **SAS v6 — Structural Auditing with R3.1 Differential Guard** | Qeios (DOI 10.32388/T420IV) | Round 4, Clarity 5/5 |
| **SAP Paper — Structural Autoprotection** | [10.5281/zenodo.21925439](https://zenodo.org/records/21925439) | Published |
| **SAS Multimetric Tribunal — Full Artifacts** | [papers/v6/](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal/tree/main/papers/v6) | 26-file supplement with SHA-256 manifest |

---

## Scope and Limitations

SAS is not a universal factual oracle. It is a technical evidence layer for structural coherence auditing.

- **Structural, not semantic.** SAS measures structural coherence between source and response. A structurally coherent response can still be factually wrong, and a structurally ruptured response can still contain correct facts.
- **Dataset-specific benchmarks.** All reported metrics are dataset-specific and should not be generalized without domain-level structural evaluation.
- **No GPU required.** SAS runs entirely on CPU. No external LLM API is required for the core detector.
- **No training data required.** All modules are rule-based or geometry-based. No fine-tuning, no training splits, no gradient updates.
- **Privacy by design.** The public demo does not store submitted text. The API does not log raw content beyond request metadata.

---

## Privacy and Observability

- Raw submitted text is not stored beyond the duration of the request.
- Anonymized usage statistics are collected for rate limiting and capacity planning.
- The `/public/stats` and `/public/activity` endpoints expose aggregate, non-identifying metrics.
- API key usage is logged for quota enforcement and abuse prevention.

---

## Citation

If you use SAS or the multimetric tribunal in academic work, please cite:

```bibtex
@software{durante2026sas,
  author = {Gonzalo Emir Durante},
  title = {SAS — Symbiotic Autoprotection System},
  doi = {10.5281/zenodo.19702379},
  year = {2026},
  publisher = {Zenodo}
}

@software{durante2026tribunal,
  author = {Gonzalo Emir Durante},
  title = {SAS Multimetric Tribunal v1.1.0},
  note = {DOI 10.32388/T420IV (Qeios)},
  year = {2026}
}
```

Use of `κD = 0.56` for semantic invariance, hallucination detection, or similar structural coherence auditing requires citation of the public SAS repository / DOI.

---

## License

**GPL-3.0 + Durante Invariance License**

- Free to use, modify, and distribute under the license terms.
- Attribution to **Gonzalo Emir Durante** is required.
- Commercial hosted service, private integration, on-premise deployment, or proprietary use may require a separate commercial agreement.

See [LICENSE.md](LICENSE.md) for the complete terms.

---

```text
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  "Structural stability in computational systems is not a property            ║
║   to be aligned toward — it is a threshold to be measured against.            ║
║   κD = 0.56 is that threshold. Documented. Implemented. Auditable."          ║
║                                                                              ║
║                               — Gonzalo Emir Durante                         ║
║                                 Project Manifold 0.56                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

<div align="center">

**SAS API:** [https://sas-api.onrender.com](https://sas-api.onrender.com)  
**Live Demo:** [https://leesintheblindmonk1999.github.io/sas-landing/](https://leesintheblindmonk1999.github.io/sas-landing/)  
**Tribunal:** [https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal](https://github.com/Leesintheblindmonk1999/sas-multimetric-tribunal)  
**PyPI:** [https://pypi.org/project/sas-client/](https://pypi.org/project/sas-client/)  
**Contact:** [duranteg2@gmail.com](mailto:duranteg2@gmail.com)

</div>
