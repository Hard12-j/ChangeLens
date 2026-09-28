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

> Run `streamlit run app.py`, analyze a commit, and add a screenshot here.

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

## Benchmark

Run with:

```bash
python benchmark.py --repo /path/to/spring-repo --n 5
```

Then manually review summaries and fill Notes columns.

| Mode | Commit | Risk Level | Time (s) | Correct Breakage Found | Missed | False Alarm | Hallucination |
|------|--------|------------|----------|------------------------|--------|-------------|---------------|
| A | (run benchmark to fill) | -- | -- | -- | -- | -- | -- |
| B | (run benchmark to fill) | -- | -- | -- | -- | -- | -- |
| C | (run benchmark to fill) | -- | -- | -- | -- | -- | -- |

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

## Limitations

- **LLM "why" is always a guess.** The Why column is inferred by the LLM and labelled "(inferred)". It may be wrong.
- **Cross-file breakage may be missed.** Analysis focuses on changed files. Mode C (RAG) partially mitigates this.
- **Large diffs are truncated.** Diffs over ~12,000 characters are truncated. Very large refactors may produce incomplete summaries.
- **Java only.** Rule detection only parses `.java` files. Kotlin, Groovy not yet supported.
- **No correctness guarantee.** This tool assists; it does not replace human code review.
- **Private GitHub repos not supported.** Clone locally first -- URL mode requires public repos.

---

## Future Work

- **User login / auth** -- multi-user SaaS mode with saved history
- **Private repos** -- GitHub/GitLab OAuth token support
- **Other languages** -- Kotlin, Groovy, Python (FastAPI), Node (Express). Adding a framework = adding `rules/framework.py` with the same `analyse(diff_text) -> list[Finding]` interface.
- **GitHub Actions integration** -- post report as PR comment automatically
- **VS Code extension** -- inline change-impact hover tooltips
- **More LLM providers** -- Anthropic Claude, Google Gemini presets
- **Historical trend view** -- track risk levels across many releases

---

## License

MIT
