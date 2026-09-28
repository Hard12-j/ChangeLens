# ChangeLens -- Spring Boot Change-Impact Analyzer

> Explains what changed between two git commits of a Spring Boot project, in plain English for non-technical managers, with a risk level and a "what could break" assessment.

---

## Problem

Engineering managers and non-technical stakeholders need to understand code changes before approving releases, but reading raw git diffs requires deep technical expertise. Existing tools produce raw diffs, changelogs, or CI reports that are opaque to business audiences.

ChangeLens bridges that gap by combining deterministic rule-based analysis with an LLM to produce a plain-English report -- no code reading required.

---

## Approach

```
Git diff
   |
   +---> rules/spring.py   (deterministic: endpoints, DTOs, entities, security)
   |
   +---> rag.py            (optional: embed repo Java files -> Chroma -> retrieve context)
   |
   +---> llm.py            (prompt = diff + findings + context -> structured JSON)
              |
              +---> app.py (Streamlit: summary, risk badge, change table, tech details)
```

Three analysis modes trade speed for depth:

| Mode | What the LLM sees | Best for |
|------|-------------------|----------|
| A | Diff only | Quick scan, minimal cost |
| B | Diff + Spring rule findings | Reliable endpoint / DB / security detection |
| C | Diff + rules + RAG context | Deepest understanding; requires one-time indexing |

---

## Screenshots

<img width="1920" height="883" alt="image" src="https://github.com/user-attachments/assets/c40af4b1-0ad6-4ad2-8f77-da7ada1fb657" />
<br>
<br>
<img width="1918" height="882" alt="image" src="https://github.com/user-attachments/assets/6b99ab42-e9d1-4641-8616-57cdbd56b6d4" />


---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/your-org/changelens.git
cd changelens
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### 2. Configure API keys

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
# Edit .env and set OPENAI_API_KEY
```

### 3. Run

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

### 4. (Optional) Index for Mode C (RAG)

In the sidebar, enter the repo path, select Mode C, and click **Index repo for RAG**.
This is a one-time step; chunks are stored in `.chroma_db/`.

---

## Benchmark Results

Benchmark executed against [`SmartFitnessTracker`](https://github.com/Hard12-j/SmartFitnessTracker) across 5 sample commits:

```bash
python benchmark.py --repo https://github.com/Hard12-j/SmartFitnessTracker --n 5
```

### Comparative Results Table

| Mode | Commit | Risk Level | Time (s) | Key Assessment / Identified Breakage |
|------|--------|------------|----------|--------------------------------------|
| **A** | `60ecb6e` | Medium | 2.79 | Datasource URL changed & HikariCP pool added; possible connectivity issues if env var unset. |
| **B** | `60ecb6e` | Low | 2.68 | Minor configuration & logging adjustment with low blast radius. |
| **C** | `60ecb6e` | Medium | 4.25 | Database connectivity configuration changes; pool sizing verified. |
| **A** | `657ed62` | Low | 2.33 | Minor UI / dependency touch-ups. |
| **B** | `657ed62` | Low | 1.28 | No sensitive Spring annotations affected. |
| **C** | `657ed62` | Low | 1.27 | Consistent low risk across all code contexts. |
| **A** | `0d6283b` | Medium | 1.98 | Modified user handling logic. |
| **B** | `0d6283b` | Medium | 2.90 | Entity / controller interaction inspected. |
| **C** | `0d6283b` | Medium | 2.45 | Verified cross-layer impact. |
| **A** | `01d3674` | **Low** ⚠️ | 28.65 | *Missed schema risk* — raw diff interpreted as straightforward code additions. |
| **B** | `01d3674` | **High** ✅ | 38.31 | **Caught schema & API changes**: Detected `@Entity` (`ChatMessage`), new table, and new `@PostMapping`/`@GetMapping` endpoints requiring DB migration. |
| **C** | `01d3674` | **High** ✅ | 40.41 | Confirmed full blast radius with WebSocket configuration & STOMP controller routes. |
| **A** | `e03055d` | Medium | 26.25 | Controller updates detected. |
| **B** | `e03055d` | **High** ✅ | 38.66 | **High risk**: Spring rule analysis flagged breaking endpoint signatures and security filter changes. |
| **C** | `e03055d` | **High** ✅ | 36.41 | Deep structural impact verified across service and repository dependencies. |

### Key Benchmark Takeaways
- **Deterministic Rules Prevent Blind Spots (Mode B vs A):** On commit `01d3674`, Mode A evaluated the commit as **Low** risk. Mode B caught the `@Entity` JPA annotation and new REST endpoints via `rules/spring.py`, correctly escalating the risk to **High** due to mandatory database schema migrations.
- **RAG Context Depth (Mode C):** Provides deep contextual grounding for complex multi-file architectural changes (such as WebSocket brokers and cross-controller mappings).

---

## Project Structure

```
changelens/
|-- app.py              # Streamlit UI
|-- git_utils.py        # Git diff and commit metadata extraction
|-- llm.py              # LLM prompt builder and API caller
|-- rag.py              # Java chunking, embedding, Chroma retrieval
|-- benchmark.py        # Multi-mode benchmark runner
|-- rules/
|   |-- __init__.py
|   +-- spring.py       # Deterministic Spring Boot pattern detection
|-- requirements.txt
|-- .env.example
+-- README.md
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | OpenAI or compatible API key |
| `OPENAI_BASE_URL` | *(unset)* | Override endpoint (Groq, Together, Ollama, etc.) |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `EMBED_MODEL` | `text-embedding-3-small` | Embeddings model (Mode C) |
| `CHROMA_PATH` | `.chroma_db` | Local Chroma vector DB path |

---

## Detected Spring Boot Patterns (Modes B and C)

`rules/spring.py` detects these **deterministically** -- no LLM involved:

- **Endpoints**: @GetMapping, @PostMapping, @PutMapping, @DeleteMapping, @PatchMapping, @RequestMapping added/removed
- **DTOs**: Field changes in *Request, *Response, *Dto, *Payload, *Body classes
- **Entities**: JPA annotations (@Entity, @Table, @Column, @Id, etc.) -- flags potential DB migrations
- **Security**: @PreAuthorize, @Secured, @EnableWebSecurity, SecurityFilterChain, CORS config
- **Configuration**: @Configuration, @Bean, @ConfigurationProperties, @Value, @Profile

---

## Future Work

- **User login / auth** -- multi-user SaaS mode with saved history
- **Private repos** -- GitHub/GitLab OAuth token support
- **Other languages** -- Kotlin, Groovy, Python (FastAPI), Node (Express). Adding a framework = adding `rules/framework.py` with the same `analyse(diff_text) -> list[Finding]` interface.
- **GitHub Actions integration** -- post report as PR comment automatically
- **VS Code extension** -- inline change-impact hover tooltips
- **More LLM providers** -- Anthropic Claude, Google Gemini presets
- **Historical trend view** -- track risk levels across many releases
