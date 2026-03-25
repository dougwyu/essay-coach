# Essay Coach — Quantitative Scoring Design

## Goal

Add per-paragraph quantitative scoring to the feedback loop. Instructors embed point values in square brackets at the end of each paragraph of the model answer. After streaming qualitative feedback, a second LLM call scores the student's answer paragraph-by-paragraph and sends the result as a final SSE event. Scores are stored in the database and rendered in both the live workspace and revision history. Questions without point values continue to work exactly as before, receiving qualitative-only feedback.

## Stack Additions

None — no new libraries. Scoring is built on existing FastAPI + SQLite + Anthropic SDK patterns.

---

## Model Answer Format

Instructors write model answers as paragraphs separated by blank lines. A paragraph that should be scored ends with a point value in square brackets, separated from the text by a single space:

```
Photosynthesis converts light energy into chemical energy stored as glucose.
It occurs in chloroplasts via two coupled stages. [3]

In the light-dependent reactions, water is split and oxygen released.
ATP and NADPH are produced and passed to the next stage. [4]

The Calvin cycle uses CO2, ATP, and NADPH to build glucose via carbon
fixation catalysed by RuBisCO. [3]
```

### Rules

- Paragraphs are separated by one or more blank lines.
- A paragraph is **scored** if its last non-whitespace token matches the regex `\[(\d+)\]` where the integer is ≥ 1.
- The `[N]` token is stripped from the paragraph text before it is sent to the LLM; the LLM never sees the raw point values.
- A paragraph without a `[N]` token is passed to the LLM as contextual text but is not assigned a score and does not contribute to the total.
- **Total points** for a question = sum of all `[N]` values across scored paragraphs.
- If zero paragraphs carry a point value, scoring is skipped entirely for that question.

### Specimen Model Answers

The following examples illustrate the format at final-year (3rd year, UK) university level.

---

**Molecular Biology**
*Describe the mechanism of homologous recombination as a pathway for DNA double-strand break repair in eukaryotes. Explain the roles of BRCA1 and BRCA2, the restriction of this pathway to S and G2 phases, and the clinical consequences of pathway deficiency.*

Double-strand breaks (DSBs) are sensed by the MRN complex (MRE11–RAD50–NBS1), which recruits and activates the kinase ATM via autophosphorylation at Ser1981. ATM phosphorylates histone H2AX (γH2AX) over megabase chromatin domains flanking the break, creating a scaffold for MDC1, RNF8/RNF168, and the downstream effectors BRCA1 and 53BP1. Homologous recombination (HR) is initiated by 5'→3' resection: MRN and CtIP generate short 3' ssDNA overhangs extended by EXO1 and the BLM–DNA2–RPA complex. The resulting kilobase-scale ssDNA tails are stabilised by RPA, which simultaneously activates the ATR–ATRIP checkpoint kinase and stalls the cell cycle through Chk1. [3]

RAD51 must displace RPA from ssDNA and form a right-handed helical nucleofilament competent for homology search. BRCA2 mediates this step, binding RAD51 via eight BRC repeats in its central domain and loading it cooperatively onto ssDNA; the C-terminal domain further stabilises the filament. BRCA1 acts upstream as an adaptor, counteracting the anti-resection activity of 53BP1 and recruiting BRCA2 to DSB sites via PALB2. The mature RAD51 nucleofilament performs strand invasion into the intact sister chromatid, driven by ATP hydrolysis, inserting the 3' ssDNA end into the homologous duplex to form a displacement loop (D-loop). This synaptic step is the central catalytic event of HR. [4]

The 3' invading end within the D-loop is extended by DNA polymerase δ using the sister chromatid as template. Resolution proceeds via two sub-pathways. In synthesis-dependent strand annealing (SDSA), the newly synthesised strand is unwound and anneals to the other resected end, producing non-crossover products — the predominant outcome in mitotic cells, which avoids loss of heterozygosity. Alternatively, capture of the second DSB end produces a double Holliday junction (dHJ), which can be dissolved by the BTR complex (BLM–Topoisomerase IIIα–RMI1/2) to give non-crossovers, or cleaved by structure-specific endonucleases (GEN1; SLX1–SLX4; MUS81–EME1) to yield crossovers or non-crossovers depending on cleavage orientation. [3]

HR is restricted to late S and G2 phases when a replicated sister chromatid is available as template and held in proximity by cohesin. This restriction is enforced by CDK activity: CDK2/cyclin A and CDK1/cyclin B phosphorylate CtIP (activating resection) and BRCA1 (releasing it from 53BP1 competition at DSBs) specifically in S and G2. In G1, low CDK activity leaves 53BP1 and its effectors RIF1 and the Shieldin complex dominant at DSB ends, suppressing resection and committing repair to non-homologous end joining (NHEJ). The mutually antagonistic relationship between BRCA1 (HR-promoting) and 53BP1 (NHEJ-promoting) constitutes the molecular switch governing pathway choice. [3]

Germline loss-of-function mutations in BRCA1 or BRCA2 cause HR deficiency, producing genomic instability and elevated lifetime risks of breast (~70%), ovarian (~40%), and pancreatic cancers. HR-deficient tumours display a characteristic mutational signature — deletions at microhomologies and high-level copy number changes — detectable by genomic sequencing. Critically, HR deficiency creates a therapeutic vulnerability: PARP1 mediates repair of single-strand breaks and stalled replication forks; in BRCA-deficient cells, PARP inhibition (olaparib, niraparib) prevents SSB repair, causing fork collapse into DSBs that cannot be resolved by HR, selectively killing tumour cells — a paradigm of synthetic lethality now exploited in FDA-approved targeted therapy. HR proficiency in normal heterozygous cells provides the therapeutic window. [4]

**Total: 17 points**

---

**Ecology**
*Critically evaluate the evidence for trophic cascades in aquatic and terrestrial ecosystems, and discuss the factors that modulate cascade strength. What are the implications for conservation management?*

The trophic cascade hypothesis holds that apex predators exert strong top-down control that propagates indirectly through the food web to affect primary producers, creating alternating positive and negative effects across trophic levels. The intellectual foundation is the Hairston–Smith–Slobodkin (1960) "green world" hypothesis, which inferred predator control of herbivores from the observation that terrestrial vegetation is rarely consumed to bare ground. Paine's (1966) keystone species concept, derived from removal experiments with the sea star *Pisaster ochraceus* in intertidal communities, provided the first controlled experimental demonstration: removing the apex predator led to mussel dominance and collapse of species diversity, establishing that single species can have disproportionate top-down structuring effects on communities. [3]

Aquatic systems provide the strongest and most consistent evidence for trophic cascades. Estes and Palmisano (1974) documented a natural experiment across the Aleutian Islands: where sea otters (*Enhydra lutris*) persisted, sea urchin densities were low and kelp forests extensive; islands from which otters had been extirpated by the fur trade supported urchin population explosions and urchin barrens devoid of macroalgae. Carpenter et al.'s whole-lake manipulation experiments in Wisconsin demonstrated that altering piscivore abundance cascaded through planktivorous fish and zooplankton to affect phytoplankton biomass and water clarity — a tri-trophic cascade confirmed by replicated experimental design. Shurin et al.'s (2002) cross-system meta-analysis confirmed that cascade effect sizes are consistently large in marine benthic, freshwater pelagic, and stream ecosystems, though variable among systems. [4]

Evidence for strong trophic cascades in terrestrial ecosystems is more equivocal. The reintroduction of grey wolves (*Canis lupus*) to Yellowstone in 1995 attracted attention as a cascade exemplar: wolf predation on elk was proposed to reduce browsing pressure on riparian vegetation and, through a "landscape of fear," alter elk spatial distribution, enabling vegetation recovery and geomorphological changes to river channels (Ripple & Beschta 2012). This narrative has been substantially challenged: Kauffman et al. (2010) demonstrated that elk population size, drought, and human hunting explained vegetation recovery better than wolf-induced fear alone, and the geomorphological claims remain contested. Shurin et al. (2002) confirmed that terrestrial cascades are consistently weaker than aquatic ones, reflecting greater omnivory, reticulate food web structure, and spatial refugia that allow prey to evade predators without cascading effects on plant communities. [4]

Several ecological properties predict cascade strength. System complexity is the primary moderator: cascades are strongest in spatially enclosed, low-diversity systems where predators exert pervasive control and prey lack dispersal refugia. Omnivory disrupts linear cascade logic — a predator feeding across multiple trophic levels simultaneously suppresses prey (cascade-promoting) and competes with them (cascade-opposing), damping net effects. The exploitation ecosystem hypothesis (Oksanen et al. 1981) predicts that cascade length and strength increase with primary productivity, as high-energy systems can support more trophic levels under top-down control. Species identity matters independently of trophic position: functionally dominant and keystone species generate stronger cascades than functionally redundant ones, and cascade effects may collapse if a numerically comparable but functionally distinct species replaces the original predator. [3]

Trophic cascade theory underpins contemporary rewilding initiatives proposing apex predator reintroduction as a cost-effective mechanism for restoring ecosystem structure without continuous management intervention. Marine protected areas permitting recovery of sharks and large-bodied piscivores are predicted to generate cascading benefits for reef herbivore communities and coral cover. Terrestrial rewilding proposals for Eurasian lynx, wolf, and white-tailed eagle invoke similar logic. However, the heterogeneity of evidence — particularly the weakness of documented terrestrial cascades — cautions against overconfident predictions. Successful cascade management requires prior characterisation of the target food web, realistic assessment of predator functional roles, and monitoring frameworks capable of attributing community change to trophic mechanisms rather than confounding climatic or land-use drivers. Cascades are better treated as ecologically plausible hypotheses requiring post-reintroduction evaluation than as guaranteed outcomes of predator restoration. [3]

**Total: 17 points**

---

## Parsing

A new pure function `parse_scored_paragraphs(model_answer: str) -> list[dict]` lives in `feedback.py`:

```python
import re

def parse_scored_paragraphs(model_answer: str) -> list[dict]:
    """
    Split model_answer into paragraphs. For each paragraph, extract the
    trailing [N] point value if present. Return a list of dicts:
        {"text": str, "points": int | None}
    Paragraphs with points=None are contextual only and not scored.
    """
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', model_answer.strip()) if p.strip()]
    result = []
    pattern = re.compile(r'^(.*?)\s*\[(\d+)\]\s*$', re.DOTALL)
    for p in paragraphs:
        m = pattern.match(p)
        if m:
            result.append({"text": m.group(1).strip(), "points": int(m.group(2))})
        else:
            result.append({"text": p, "points": None})
    return result
```

`total_points(paragraphs) -> int` returns the sum of all non-None point values. If the result is 0, scoring is skipped.

---

## LLM Calls

### Call 1 — Streaming qualitative feedback

`generate_feedback_stream` is unchanged in signature. One addition to the system prompt:

> "If the model answer contains point values per section, acknowledge at the end of your feedback that a score will follow. If it does not, add a single sentence: 'No point values were set for this question — feedback is qualitative only.'"

The qualitative feedback text never contains numeric scores. The acknowledgement line is a brief, subordinate closing sentence.

### Call 2 — Non-streaming scoring

A new function `generate_score(paragraphs, student_answer, attempt_number) -> dict | None` in `feedback.py`. Only called when `total_points(paragraphs) > 0`.

**System prompt:**

```
You are a strict but fair examiner scoring a student's essay answer.
You will be given the model answer split into numbered sections, each with a maximum point value.
The student's answer will not follow the same order as the model answer sections.
For each section, judge how many points the student has earned based on the conceptual
coverage and accuracy of their answer as a whole.

Rules:
1. awarded must be an integer between 0 and max (inclusive).
2. Generate a label (3–7 words) summarising the core concept of each section.
   - attempt_number 1: use broad topic labels (e.g. "Light-dependent reactions").
   - attempt_number 2+: use progressively more specific labels that give the student
     clearer signal about what is missing (e.g. "Role of ATP and NADPH in light reactions").
   Labels should orient the student to the relevant part of their answer without
   quoting or closely paraphrasing the model answer text.
3. Return ONLY valid JSON matching the schema below. No prose, no markdown.

Schema:
{
  "breakdown": [
    {"label": "<string>", "awarded": <int>, "max": <int>},
    ...
  ],
  "total_awarded": <int>,
  "total_max": <int>
}
```

**User message:**

```
<sections>
  <section index="1" max="3">DSB detection and end resection text...</section>
  <section index="2" max="4">RAD51 loading and strand invasion text...</section>
  ...
</sections>
<student_answer attempt="2">Student text here...</student_answer>
```

Only scored paragraphs (`points != None`) appear as `<section>` elements. Unscored paragraphs are omitted from the scoring call (they were already available to Call 1).

**Validation before storing:**

```python
def validate_score(data: dict, paragraphs: list[dict]) -> bool:
    scored = [p for p in paragraphs if p["points"] is not None]
    if len(data["breakdown"]) != len(scored):
        return False
    for item, para in zip(data["breakdown"], scored):
        if not (0 <= item["awarded"] <= item["max"]):
            return False
        if item["max"] != para["points"]:
            return False
    expected_total_max = sum(p["points"] for p in scored)
    expected_total_awarded = sum(item["awarded"] for item in data["breakdown"])
    if data["total_max"] != expected_total_max:
        return False
    if data["total_awarded"] != expected_total_awarded:
        return False
    return True
```

If validation fails, or if the Anthropic call raises an exception, `generate_score` returns `None` and no score event is emitted. The attempt is already saved without a score; the qualitative feedback has already been delivered.

---

## Database Changes

### Modified table: `attempts`

Add column: `score_data TEXT` (nullable JSON string).

```sql
ALTER TABLE attempts ADD COLUMN score_data TEXT;
```

Added in `init_db()` via a guard:

```python
existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(attempts)").fetchall()]
if "score_data" not in existing_cols:
    conn.execute("ALTER TABLE attempts ADD COLUMN score_data TEXT")
```

`score_data` is `NULL` when:
- The question has no point values.
- The scoring call failed or returned invalid JSON.
- The attempt predates this feature.

### Modified function: `create_attempt`

```python
def create_attempt(question_id, session_id, student_answer, feedback, attempt_number, score_data=None):
```

`score_data` is stored as a JSON string (or `None`).

`get_attempts` already returns `SELECT *`, so `score_data` is included automatically.

---

## API — SSE Protocol Changes

The existing SSE event sequence gains one new optional event type, emitted after `done`:

```
data: {"text": "chunk"}          ← repeated during streaming (unchanged)
data: {"done": true, "attempt_number": 3}   ← attempt saved (unchanged)
data: {"score": {                ← new; only emitted when scoring succeeds
  "breakdown": [
    {"label": "DSB detection and resection", "awarded": 2, "max": 3},
    {"label": "RAD51 loading and strand invasion", "awarded": 4, "max": 4},
    {"label": "dHJ resolution and SDSA", "awarded": 2, "max": 3},
    {"label": "Cell cycle restriction of HR", "awarded": 1, "max": 3},
    {"label": "BRCA mutations and PARP inhibitor therapy", "awarded": 3, "max": 4}
  ],
  "total_awarded": 12,
  "total_max": 17
}}
```

The scoring call is made after `done` is emitted. `create_attempt` is called before scoring (the attempt is saved whether or not scoring succeeds). The SSE connection remains open until the scoring call completes or fails.

### `GET /api/attempts/{question_id}`

Returns `score_data` as a parsed object (not a string) when present, `null` when absent. The route deserialises the JSON string from the DB before returning.

---

## Frontend Changes

### `static/app.js`

**`submitForFeedback`** gains handling for the `score` event type:

```javascript
if (data.score) {
    renderScore(data.score);
}
```

**New `renderScore(scoreData)` function:**

```javascript
function renderScore(scoreData) {
    const section = document.getElementById('score-section');
    const content = document.getElementById('score-content');
    const rows = scoreData.breakdown.map(item =>
        `<tr>
           <td class="score-label">${item.label}</td>
           <td class="score-fraction">${item.awarded} / ${item.max}</td>
         </tr>`
    ).join('');
    content.innerHTML = `
        <div class="score-total">Score: ${scoreData.total_awarded} / ${scoreData.total_max}</div>
        <table class="score-breakdown">${rows}</table>`;
    section.style.display = 'block';
}
```

**`loadAttemptHistory`** calls `renderScore` for each history card that has `score_data`:

```javascript
if (a.score_data) {
    renderScore(a.score_data);  // renders into the card's score-section
}
```

History cards each get their own `score-section` div, so `renderScore` must accept an optional target element parameter. The live workspace has one global `score-section`; history cards each have an inline one.

### `templates/student.html` — workspace mode

Add inside the right pane, below `feedback-section`:

```html
<div id="score-section" class="score-section" style="display:none">
    <div id="score-content"></div>
</div>
```

Reset `score-section` to hidden (and clear `score-content`) at the start of each new submission, alongside resetting `feedback-section`.

### `static/style.css`

```css
.score-section {
    margin-top: 1.5rem;
    padding: 1rem 1.25rem;
    background: var(--bg-subtle);
    border-radius: var(--radius);
    border: 1px solid var(--border);
}

.score-total {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
}

.score-breakdown {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}

.score-breakdown tr + tr {
    border-top: 1px solid var(--border);
}

.score-label {
    padding: 0.35rem 0;
    color: var(--text-muted);
}

.score-fraction {
    padding: 0.35rem 0;
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
```

---

## Backwards Compatibility

- Questions created before this feature (no `[N]` tokens) behave identically to today. No score event is emitted; the feedback note "qualitative only" appears in the LLM text.
- Existing `attempts` rows have `score_data = NULL`; revision history renders no score block for them.
- The `create_attempt` signature change is backwards-compatible (new parameter defaults to `None`).

---

## Flexibility Note

The per-paragraph breakdown display is the initial design. Switching to total-score-only display in future requires changing only `renderScore` on the client — the DB schema, SSE event shape, and server logic are identical for both display modes. The `breakdown` array remains in the stored JSON and SSE payload regardless of how it is presented.

---

## Testing

### `tests/test_feedback.py` — new unit tests for parsing and validation

- `parse_scored_paragraphs` correctly extracts `[N]` tokens and strips them from text
- `parse_scored_paragraphs` returns `points=None` for unscored paragraphs
- `total_points` returns correct sum; returns 0 when no paragraphs are scored
- `validate_score` passes on a correct scoring response
- `validate_score` fails when `awarded > max`
- `validate_score` fails when `total_awarded` does not match sum of `breakdown`
- `validate_score` fails when `breakdown` length does not match scored paragraph count
- `validate_score` fails when any `max` does not match the expected paragraph points

### `tests/test_scoring_integration.py` — new FastAPI TestClient integration tests

- `POST /api/feedback` on a scored question emits a `score` event after `done`
- `POST /api/feedback` on an unscored question emits no `score` event
- `score` event `total_max` matches the sum of `[N]` values in the model answer
- `GET /api/attempts/{id}` returns `score_data` as a parsed object (not string) when present
- `GET /api/attempts/{id}` returns `score_data: null` for pre-feature attempts
- `create_attempt` with `score_data=None` stores NULL; retrieved attempt has `score_data=None`
- `create_attempt` with valid score dict stores and retrieves correctly
- Scoring call failure (mocked) results in no `score` event and no `score_data` on the attempt; `done` event is still emitted

### Existing tests

`test_db.py`, `test_auth.py`, `test_auth_utils.py`, `test_auth_integration.py`, `test_classes.py`, and `test_classes_integration.py` are unaffected.
