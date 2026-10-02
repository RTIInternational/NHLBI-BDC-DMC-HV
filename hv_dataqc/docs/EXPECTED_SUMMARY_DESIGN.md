# How to handle multi-PHV / multi-input YAML transforms

A design note on three approaches to comparing harmonized output against
the source for harmonized variables whose YAML transform combines
multiple PHVs or evaluates a non-trivial expression. Written
2026-06-05 while reviewing PR #570; preserves context for follow-up
discussion.

## The problem

`hv_dataqc.compare` validates that BDC's dm-bip harmonized output
matches the source dbGaP data. It works from **aggregate-only JSON
summaries** of both sides so the comparison can run outside the Seven
Bridges enclave.

That aggregate-only constraint is fundamentally at odds with
multi-input YAML transforms. Most transforms map one source PHV to
one harmonized variable via direct copy or value_mappings — straight
single-variable comparison, no problem. But some transforms use
`case()` expressions whose branch *conditions* combine multiple PHVs.
For example:

```yaml
# From COPDGene asthma.yaml (simplified)
associated_visit:
  expr: case(
    ({phv00568798} == 'P1', uuid5('https://w3id.org/bdchm/Visit',
                                  str({phv00159568}) + ':COPDGene P1')),
    ({phv00568798} == 'P2', uuid5(...)),
    ...
  )
```

You can't derive the result distribution of this expression from the
marginal distributions of `phv00568798` and `phv00159568` alone —
you'd need either row-level data or a pre-computed joint distribution.

Aggregate distributions are sufficient for single-PHV value_mappings
and single-PHV `case()` branches. They're not sufficient for anything
where the transform's behavior depends on the joint values of two or
more inputs in the same row.

## Three approaches considered

### Option A — Aggregate marginals, give up on multi-input

What `hv_dataqc.compare` did pre-2026-05-28. Multi-PHV `case()`
branches were flagged unsupported and the relevant checks (C2 / C3 /
C7) emitted SKIP.

A meaningful chunk of harmonized variables have *at least one* exam
block or visit that uses multi-PHV `case()`. Before `ab001909` (fix
date 2026-06-01), a single unsupported entry in a match pool
collapsed the entire pool to unsupported, even when 9 of the 10
contributing YAML blocks were comparable. That fix already converted
~20 spurious SKIPs back into PASS/FAIL/WARN per cohort.

Remaining limitation: any harmonized variable whose primary
contributing block is multi-PHV is still uncomparable under Option A.

### Option B — Pre-compute pairwise PHV joint distributions

Implemented in `ef9fee71` (2026-05-28). At extract time:

1. `scan_yaml_phv_pairs.py` walks the YAMLs to find every pair of PHVs
   that co-occur in a `case()` condition.
2. `extract_source_summaries.py` reads that list and emits a
   `joint_distributions_by_pht` block in the source JSON — for each
   pair, a crosstab of `(phv_a, phv_b) → count`.
3. On the compare side, `_expected_summary_from_case_value_exprs`
   resolves 2-PHV branches by looking up the relevant joint-distribution
   cell instead of multiplying marginals.

This keeps the framework's "comparison uses live YAMLs" property: as
long as a YAML edit doesn't introduce a *new* PHV pair, the existing
joint crosstabs still work and no SB re-entry is needed.

**Limitations:**

- 3+ PHV conditions still fall through to unsupported.
- `case()` branches with non-null `else:` / default outputs require
  complement counts the crosstab doesn't supply (see line 226–231 of
  `expected_summary.py`).
- Non-`case()` expressions — `uuid5(...)`, `str(...)`, arithmetic
  inside a branch — are not modeled.
- `joins` (cross-table lookups via `linkml-map`'s `LookupIndex`) are
  not modeled.
- The compare-side YAML-semantics reimplementation in
  `expected_summary.py` is ~1300 lines and growing. `ab001909`'s
  partial-unsupported pool fix is the latest in a series of fixes to
  this surface; the bug class is "our reimplementation of YAML
  semantics drifted from dm-bip's reimplementation."

### Option C — Evaluate the YAML transform at extract time

Proposed 2026-06-05. At extract time, for each source row, run the
actual YAML transform engine and aggregate the *output* distribution. Ship the aggregated transform output alongside the raw
source aggregates.

**`linkml-map` already provides a usable runtime engine.**
`ObjectTransformer.map_object` takes a source row dict and returns
the transformed harmonized values. The "expression language" in the
YAML is Python expressions over a restricted symbol table, evaluated
via `simpleeval` (or `asteval` when `unrestricted_eval=True`).
`case()`, `uuid5()`, `str()` are functions injected into the
evaluator namespace. PHV references are `{phvNNNNNNNN}` template
substitutions, also native to the evaluator. No custom grammar to
parse, no interpreter to write.

**Confirmed working** on a real COPDGene YAML (2026-06-05 probe):

- The expression evaluator handles `{phvNNNNNNNN}` template
  substitution natively via `eval_expr_with_mapping`. Multi-PHV
  `case()` conditions, `uuid5()`, `str()`, and arithmetic all
  evaluate correctly with the same expression syntax used in the
  YAMLs.
- `ObjectTransformer.map_object` runs end-to-end on `bdy_hgt.yaml`
  after one preprocessing step: passing the YAML through
  `linkml_map.validator.normalize_spec_dict`, which flattens BDC's
  nested-dict form (class derivations keyed by name) into the
  list-of-dicts shape `TransformationSpecification` expects.
- The visit UUID `map_object` produces for a given (participant,
  visit-code) pair matches the UUID the raw expression evaluator
  produces, which is the same `uuid5(NAMESPACE_URL, ...)` algorithm
  dm-bip uses. So the outputs are byte-identical to what dm-bip
  produces for those slots.
- Top-level slots (`populated_from`, simple `expr`, `value`, and
  `case()` expressions) all evaluate without any further config.

**Required infrastructure not yet in `hv_dataqc`:**

- **Source schema.** `map_object` needs a `source_schemaview`
  describing the PHT tables and their PHV attributes. A minimal
  schema (each PHT as a class with its PHVs as attributes) suffices.
  This could be auto-generated from the existing dbGaP data-dict XMLs
  the `cache_fetcher/` already downloads.
- **Target schema (BDCHM).** Required for slots that use nested
  `object_derivations` (e.g. `value_quantity:` blocks in
  measurement YAMLs). Without the target schema, those slots raise
  `AttributeError: 'NoneType' object has no attribute 'induced_slot'`.
  dm-bip already uses BDCHM; we'd need to package it (or point
  `linkml-map` at it) at extract time.

Sketch:

1. Generate / load source schema describing PHTs and their PHVs.
2. Load target schema (BDCHM).
3. For each YAML class_derivation, normalize via
   `normalize_spec_dict` and call `create_transformer_specification`.
4. For each source row, call `transformer.map_object(row)` to produce
   the transformed harmonized values.
5. Aggregate per-harmonized-variable distributions from those outputs.
6. Ship the aggregated *transform-output* distribution in the source
   JSON.

On the compare side, C2 / C3 / C7 reduce to "did dm-bip's output
distribution match the distribution we'd get from running the same
engine over the source?" — a direct distribution-to-distribution
comparison. A meaningful chunk of `expected_summary.py` could be
deleted: the parts that reimplement YAML semantics
(`_expected_summary_from_case_value_exprs`,
`_expected_summary_from_value_map`,
`_expected_summary_from_concept_value_map`,
`_expected_summary_from_case_entry`, `_normalize_status_distribution`
and friends — roughly 500–700 of the 1300 lines). What stays:
the pooling helpers (`_aggregate_source_summaries` still useful for
combining per-PHT distributions on the compare side) and the result
metadata (`_comparison_basis`, `_comparison_confidence`,
`_comparison_limitations` fields).

**Advantages over Option B:**

- Handles 3+ PHV conditions, `else:` branches, `uuid5()` /
  arithmetic, `joins` — anything `linkml-map` already evaluates.
- Dramatically reduces the "our reimplementation of YAML semantics
  drifts from dm-bip's reimplementation" bug class. The expression
  semantics come from the same engine. Some risk remains in how we
  drive that engine vs how dm-bip drives it.
- Substantially smaller compare-side codebase. ~500–700 lines of
  `expected_summary.py` can be deleted (the YAML-semantics
  reimplementation parts); pooling and metadata plumbing stay.
- Better testability story: most of the new logic lives in the
  extractor (callable locally on synthetic fixtures) rather than in
  YAML-semantics reimplementation code.

**Disadvantages vs Option B:**

- **Loses the "comparison uses live YAMLs" property.** Every YAML
  change requires SB re-extraction. Discussed below — may matter
  less in practice than it sounds.
- **Depends on `linkml-map` as a stable library.** It's currently
  pinned to `git+...@main` (no tagged release). The 2026-06-05 probe
  showed `ObjectTransformer.map_object`, `create_transformer_specification`,
  and `normalize_spec_dict` are all callable and behave correctly,
  but none is documented with a stability guarantee. Worth asking
  the linkml-map maintainers whether the runtime engine API is
  considered stable.
- **Need a source schema describing PHTs.** Generatable from the
  dbGaP data-dict XMLs `cache_fetcher/` already downloads, but not
  free — needs a small generator script and the discipline to keep
  it in sync with cache updates.
- **Need access to the BDCHM target schema at extract time.** dm-bip
  uses it, so it exists; just needs packaging into the extract
  pipeline.
- **Migration cost from Option B is real.** The current code is
  tested and shipping.
- **DuckDB option needs scoping.** `linkml-map` also has a
  `DuckDBTransformer`. If extract performance matters (`293bb911`
  "load one PHT at a time to avoid OOM" suggests it does for large
  cohorts), row-by-row Python evaluation over hundreds of thousands
  of rows may not be viable. Worth measuring before committing.

## What Option B can't model — measured against current YAMLs

A 2026-06-05 scan of all 780 YAMLs in `priority_variables_transform/`
classified every `expr:` and `joins:` block by the pattern that takes
it outside Option B's reach. Branch
`feature/hv-dataqc-20260423`.

The classifier walked each YAML, picked out `case()` branches, and
tagged the expression by which Option-B-incompatible pattern it
contained. Up to three example links per category below; full output
in `/tmp/option_b_failures.md` (regenerable from
`/tmp/find_option_b_failures.py`).

### A. Three or more PHVs in a single `case()` branch condition (2 hits)

Option B pre-computes joint distributions for PHV **pairs**. Branches
referencing 3+ PHVs in their condition can't be resolved from
pairwise crosstabs. Both hits are demographic composite indices
built by summing per-condition `case()` flags:

- [FHS-ingest/demography.yaml#L21](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/demography.yaml#L21) — `case( ( case(({phv00021244} == 1, 1), (True, 0)) + case(({phv00021246} == 1, 1), (True, 0)) + ... )`
- [WHI-ingest/demography.yaml#L44](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/WHI-ingest/demography.yaml#L44) — `case( ( case(({phv00079317} == 1, 1), (True, 0)) + case(({phv00079318} == 1, 1), (True, 0)) + ... )`

These are also Category E (arithmetic across PHVs) — the count is
the *sum* of multiple per-PHV `case()` outputs, then bucketed.

### B. `case()` with non-null `(True, ...)` default branch (11 hits)

A `(True, X)` branch fires for "everything not matched above" — its
row count is the complement of the explicit branches. Option B has
no way to count the complement from marginals (or even from joint
crosstabs) without row-level data.

- [ARIC-ingest/cig_smok.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/cig_smok.yaml) — `case( ({phv00207119} == "N", "OMOP:45883537"), ({phv00207120} == "N", "OMOP:45883458"), (True, "OMOP:40766945") )`
- [FHS-ingest/albumin_urine.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/albumin_urine.yaml) — `case( ({phv00071895} > 3, {phv00071895}), (True, "LLOD") )`
- [FHS-ingest/alt_sgpt.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/alt_sgpt.yaml) — `case(({phv00172166} > 5.0, {phv00172166}), ({phv00172202} == 1, "LLOD"), (True, {phv00172166}) )`

The FHS examples show the limit-of-detection (LLOD) pattern:
pass-through when above threshold, sentinel otherwise. Common in
clinical chemistry.

### C. `case()` value position with computed expression (163 hits)

`uuid5(...)`, `str(...)`, or arithmetic on the *value* side of a
`case()` branch. The branch's condition may be tractable for Option
B, but the value isn't a literal categorical — it's a row-dependent
computed value. Concentrated in FHS (81), COPDGene (42), WHI (39).

- [ARIC-ingest/bdy_hgt.yaml#L49](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/bdy_hgt.yaml#L49) — `case(({phv00206817} == "I", {phv00206855} * 2.54), ({phv00206817} == "C", {phv00206855}))` — inches→cm conversion gated on a units flag
- [CARDIA-ingest/hypert_trt.yaml#L12](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/CARDIA-ingest/hypert_trt.yaml#L12) — `case(({phv00113154} == 'HBP' and {phv00113155} == 2, uuid5('https://w3id.org/bdchm/Visit', str({phv00113153}) + ':CARDIA...')))` — visit UUID built from condition+row context
- [COPDGene-ingest/afib.yaml#L7](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/COPDGene-ingest/afib.yaml#L7) — `case(({phv00568798} == 'P2', uuid5('https://w3id.org/bdchm/Visit', str({phv00159568}) + ':COPDGene P2')), ...)` — per-exam visit UUID

The `uuid5`-producing hits in C don't affect distribution-level
comparison (UUIDs are row-unique; not aggregated). The unit
conversion hits (`* 2.54`) and pass-through-or-sentinel hits *do*
affect the harmonized distribution.

### D. `joins:` blocks (1 hit)

`joins:` declares secondary-table lookups via `linkml-map`'s
`LookupIndex`. The current compare-side code doesn't model joins at
all — they're outside both Option A and Option B's framework.

- [ARIC-ingest/person.yaml#L4](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/person.yaml#L4)

Rare in current YAMLs but likely to grow if more cohorts adopt
joined-table patterns.

### E. Plain `expr:` arithmetic on PHVs — excluding `uuid5()` (1,182 hits)

Bare `expr:` blocks (no `case()` wrapper) that do arithmetic or
non-trivial function calls on PHV values. Dominant patterns:

- `{phv} * 365` — age in years → days (BDCHM stores age in days)
- `{phv} * 2.54` — inches → cm
- `{phv} * 0.01` — percent → fraction (or similar scaling)

Top concentrations: ARIC (1,425 before URI filter), FHS (1,228), CHS
(809), MESA (740). Whether these "fail" under Option B depends on
the check:

- For **continuous mean comparison** (C4/C5), the C5 unit-conversion
  check already auto-detects the conversion factor and runs the
  comparison correctly when the harmonized mean is a clean
  scale-factor of the source mean. Genuine arithmetic Option B can
  handle.
- For **distribution comparison** (C7), Option B has no path —
  the source distribution and harmonized distribution are on
  different scales, and the marginal source distribution alone
  can't be transformed without knowing the scale.

Examples:

- [ARIC-ingest/albumin_urine.yaml#L64](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/albumin_urine.yaml#L64) — `{phv00295248} * ({phv00295250} * 0.01)` — two-PHV scaled product (also fails under "two PHVs in a value computation")
- [ARIC-ingest/bdy_hgt.yaml#L10](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/bdy_hgt.yaml#L10) — `{phv00516591} * 365` — age years→days
- [ARIC-ingest/bdy_hgt.yaml#L24](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/bdy_hgt.yaml#L24) — `{phv00516590} * 2.54` — inches→cm

### F. Qualified `{pht.phv}` cross-table PHV references (950 hits, mostly FHS)

Most YAMLs reference PHVs by bare ID: `{phv00177936}`. But ~950
expressions use the **PHT-qualified form**: `{pht003099.phv00177936}`.
This form indicates the expression pulls a value from a PHT
*different from* the one named in the block's `populated_from:`.
Almost all hits are in FHS (887/950); the rest are CHS (36) and ARIC
(27). All are in age-related slots (`age_at_observation`,
`age_at_visit_start/end`).

Option B builds joint distributions **per PHT**, so a cross-PHT
expression can't be modeled by any single PHT's crosstabs. This is
structurally the same problem as Category D (`joins:`) but expressed
inline in the expression rather than declared explicitly. The
practical scale is much larger (950 vs 1).

- [FHS-ingest/bdy_hgt.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/bdy_hgt.yaml) — `{pht003099.phv00177936} * 365` — age from a related table
- [FHS-ingest/albumin_bld.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/albumin_bld.yaml) — `case(({phv00227024} == 1, {pht003099.phv00177946} * 365), ...)` — combines cross-table reference with `case()`

### G. Python `if/else` conditional syntax (12 hits, all CARDIA `bdy_wgt.yaml`)

Pythonic `X if cond else Y` rather than `case()`. Semantically a
2-branch conditional with side effects (None-mapping + numeric
coercion + unit conversion in one).

- [CARDIA-ingest/bdy_wgt.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/CARDIA-ingest/bdy_wgt.yaml) — `None if str({phv00115857}) == 'M' else float({phv00115857}) * 0.45359237` — drop "M" (missing) marker, convert pounds to kg

The current classifier in Option B never sees `case(` here, so it
falls through to category E. Compare-side handling is whatever
arithmetic Option B does for E (unit-conversion auto-detect), but
the None-mapping branch isn't modeled.

### H. Nested `case()` inside `case()` (98 hits)

`case(cond1, case(cond2, value))` — the value of one branch is
itself a `case()` expression. Option B's classifier treats the inner
`case()` as opaque content in the outer value position, so it
doesn't decompose into the inner branch's conditions or count its
PHV references. Implication: my Category A count (3+ PHVs in a
single branch) **undercounts** real 3+ PHV expressions because
nested-case PHVs aren't seen.

- [CHS-ingest/asthma.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/CHS-ingest/asthma.yaml) — `case(({phv00099087} == 1, case(({phv00099088} == 0, {phv00099091} * 365))))` — 3 distinct PHVs across nested levels
- [CHS-ingest/asthma.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/CHS-ingest/asthma.yaml) — `case(({phv00198892} == 0, "ABSENT"), ({phv00198892} == 1, case(({phv00198893} == 0, "HISTORICAL"), (True, "PRESENT"))), (True, "UNKKNOWN"))` — Y/N/UNKNOWN logic with nested override
- [FHS-ingest/albumin_bld.yaml](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/FHS-ingest/albumin_bld.yaml) — `case(({phv00227024} == 1, {pht003099.phv00177946} * 365), case({phv00227024} == 7, {pht003099.phv00177936} * 365))` — combines nesting + cross-PHT (Category F)

### I. `uuid5()` URI computation in plain `expr:` (4,009 hits) — informational

Almost every YAML has at least two `uuid5(...)` expressions: one
that computes the `associated_participant` URI and one that computes
the `associated_visit` URI. These produce row-unique identifiers,
not values that get aggregated into distributions, so Option B's
inability to "compare" them is moot — there's nothing to aggregate
on either side. Listed here only because they syntactically match
the "plain `expr:` with function call on PHV" pattern.

- [ARIC-ingest/afib.yaml#L6](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/afib.yaml#L6) — `uuid5("https://w3id.org/bdchm/Participant", str({phv00203305}) + ":ARIC")`
- [ARIC-ingest/afib.yaml#L8](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/afib.yaml#L8) — `uuid5("https://w3id.org/bdchm/Visit", str({phv00203305}) + ":ARIC EXAM 1")`
- [ARIC-ingest/afib.yaml#L29](https://github.com/RTIInternational/NHLBI-BDC-DMC-HV/blob/feature/hv-dataqc-20260423/priority_variables_transform/ARIC-ingest/afib.yaml#L29) — `uuid5("https://w3id.org/bdchm/Participant", str({phv00203308}) + ":ARIC")`

### What the numbers say

Honest summary of category sizes — the dominant Option B blocker is
**F (cross-PHT references)** at 950 hits, an order of magnitude
larger than anything else I initially measured. Together with
nested-`case()` undercounting (H), this revises my earlier
"blocking surface is small" reading downward.

- **A (3+ PHVs in one branch)** — 2 explicit hits; real count is
  larger because nested-case PHVs (Category H) weren't counted.
- **B (default `True` branch)** — 11 hits, mostly FHS LLOD pattern.
- **C (computed value in `case()`)** — 163 hits. Mix of `uuid5()`
  (not aggregable; doesn't matter) and arithmetic gated by
  condition (does matter).
- **D + F (cross-table references, declared vs. inline)** — 1 + 950
  = 951 hits. **The dominant blocker.** Concentrated in FHS (887 of
  the 950). All in age-related slots, all referencing PHTs other
  than the block's `populated_from:` PHT.
- **E (plain arithmetic on PHVs, excluding `uuid5`)** — 1,182 bare
  + ~887 of the qualified F hits also count as arithmetic = ~2,070.
  Unit conversions (`* 365`, `* 2.54`). C5's auto-detect handles
  the mean case; distribution comparison is still gapped.
- **G (Python `if/else`)** — 12 hits, all CARDIA `bdy_wgt`.
  Semantically a `case()` but in different syntax.
- **H (nested `case()` in `case()`)** — 98 hits. Each one
  potentially obscures Category-A PHV counts and Category-C
  computed-value detection.
- **I (`uuid5()` URIs)** — 4,009 boilerplate hits, doesn't affect
  comparison.

**Revised reading.** Option B's coverage gap is dominated by FHS's
pervasive cross-PHT-reference pattern (G), which I missed in the
first pass entirely. The original conclusion ("Option B + partial
fix covers most of the practical surface") was wrong for at least
one cohort (FHS, where ~887 expressions sit in this gap). For
other cohorts the original reading stands better: the gap is real
but narrower.

This makes the **value of Option C cohort-specific**: highest for
FHS, where 887 expressions need cross-PHT evaluation; lower for
cohorts where the dominant patterns are unit conversions handled by
C5. Worth verifying with FHS-specific compare output whether C2 /
C3 / C7 are emitting an unusually high SKIP rate for that cohort.

### Meta-observation

Building this classifier required walking the YAML grammar and
recognizing each Option-B-incompatible pattern — including, as the
2026-06-05 second-pass revealed, patterns I missed in the first
pass (cross-PHT refs, nested `case()`, Python conditionals). That
work is **structurally identical** to what `linkml-map`'s
`eval_expr_with_mapping` already does (and what an Option C
implementation would call into). The fact that I missed three
categories on a first careful read is itself a small piece of
evidence that the engine-reimplementation surface is larger and
trickier than it looks. Option C avoids the surface entirely by
delegating to the real engine.

## On the "live YAMLs" advantage

The framework's third design principle says:

> **Comparison uses live YAMLs.** The crosswalk (source PHV →
> harmonized concept code) is built fresh from the current HV YAML
> checkout on every compare run. Re-run `python -m hv_dataqc.compare`
> as often as needed as YAMLs evolve — no re-entry to the enclave
> required.

Under Option B this property holds as long as new YAML edits don't
introduce new PHV pairs. Under Option C, every YAML edit requires
SB re-extraction.

How important is this property in practice? Worth discussing:

- **Empirically**, local `latest_source/` artifacts show extracts on
  2026-05-07 and 2026-05-12 — roughly weekly. If the team's extract
  cadence is already weekly for other reasons (data refreshes,
  batched YAML changes), Option C's added re-extraction cost is
  marginal.
- **For fast code iteration during development**, the live-YAML
  property genuinely helps when changing the compare logic itself —
  no SB round-trip needed to test. But once the compare logic is
  stable, this benefit disappears.
- **For fast iteration on YAML changes**, the live-YAML property
  helps. Whether this is the actual bottleneck is an empirical
  question. If most YAML edits are small fixes batched into
  weekly-or-slower data refreshes, the answer may be "not really."

The most defensible answer to "does live-YAML matter?" is probably
"it matters more *during compare-code development* than *during YAML
maintenance*." If true, that argues *for* keeping Option B during
active framework development and revisiting Option C once the
compare logic is stable.

## What `ab001909` tells us about the bug class

The 2026-06-01 partial-unsupported pool fix is a clean local
improvement: collapsing the whole pool when one entry is unsupported
was wrong, and the fix correctly partitions. But the fix itself is a
symptom of the broader pattern: `expected_summary.py` is a
reimplementation of YAML transform semantics, maintained in parallel
with the real transform engine. Every edge case has to be re-handled
on this side, and the right behavior has to be re-derived. The fix
list since 2026-05-14 includes:

- `9a4f0bc5` — flat measurement categorical values
- `e6d8acae` — unresolved static case categories
- `68fb669c` — C3 denominator fallback
- `bb9c0012` — source phv roles
- `f365a234` — C9 range match details
- `ab001909` — partial-unsupported pool

These are all "the reimplementation got something slightly wrong."
Under Option C the entire class of bug goes away because there's no
reimplementation.

## Naming

"Option A / B / C" is not memorable. Suggested labels for any
follow-up discussion:

- Option A → "marginals only" or "give up on multi-input"
- Option B → "PHV-pair crosstabs" or "pairwise joint pre-computation"
- Option C → "transform-engine pre-application" or "evaluate-at-extract"

## Open questions

1. Was the "comparison uses live YAMLs" property load-bearing for a
   specific scenario, or aspirational? If load-bearing, what's the
   scenario?
2. Is the current cadence of YAML edits actually faster than the
   extract cadence, or are they roughly aligned?
3. Is `linkml-map`'s `ObjectTransformer.map_object` /
   `create_transformer_specification` / `normalize_spec_dict` API
   surface stable enough to depend on? Question for the upstream
   maintainers — they're callable today (2026-06-05 probe) but
   uncovered by stability docs.
4. Does dm-bip itself use `ObjectTransformer` or `DuckDBTransformer`?
   If DuckDB, Option C's natural shape is also DuckDB.
5. Does dm-bip generate a source LinkML schema from the dbGaP data
   dictionaries, or hand-write one? Option C needs the same input.
6. How many cohort-variables fall into each bucket today?
   - Single-PHV (handled by current marginals path)
   - 2-PHV via Option B
   - 3+ PHV or `else:` or `uuid5()` arithmetic, currently unsupported

Question 6 sets the practical ceiling on Option C's value. If only a
handful of variables fall into the still-unsupported bucket, Option B
is good enough. If many do, Option C's payoff is bigger.
