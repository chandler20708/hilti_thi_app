# THI Prototype Methodology

This document is deliberately provisional. It is the placeholder for the post-meeting THI design.

## Current purpose

The current THI page is not claiming to be the final Hilti-approved index. Its purpose is to show a credible research pipeline:

1. define criteria
2. determine directionality
3. normalize scores
4. weight criteria
5. aggregate into a composite territory score
6. test sensitivity

That is enough to demonstrate how the final THI could be developed properly once the criteria are confirmed.

## Current prototype criteria

The app currently exposes five placeholder criteria:

- `MPS`: Market Potential Score
- `CAS`: Customer Accessibility Score
- `CPS`: Customer Profile Strength
- `GII`: Geographic Intensity Index
- `PIS`: Project Intensity Score

These are synthetic and are used only to make the pipeline concrete.

## Current prototype aggregation

The THI Studio page currently uses a weighted-sum MCDA style process:

1. select active factors
2. assign weights
3. normalize each factor across the current territory universe
4. calculate a weighted aggregate score
5. scale the result to `0–100`

This is a practical prototype method because it is easy to explain and easy to revise.

## Why MCDA is the right framing

The territory problem is inherently multi-criteria:

- geography alone is insufficient
- customer mix matters
- accessibility matters
- market potential matters
- the tradeoff between acquisition and retention matters

That makes a composite, criteria-based decision model more appropriate than a single-factor ranking.

## Recommended research path after the meeting

Once the final THI definition is clearer, the recommended path is:

1. confirm the criteria and whether each one is a benefit or cost criterion
2. confirm which inputs can use real data and which must stay synthetic or redacted
3. use a structured weighting method
4. compare at least two aggregation/ranking methods
5. test sensitivity to weight changes

## Candidate methods to evaluate

The prototype currently uses weighted-sum aggregation, but the research track should compare that with stronger MCDA options such as:

- AHP for structured weight elicitation
- TOPSIS for distance-to-ideal ranking
- PROMETHEE or other outranking approaches if pairwise dominance becomes important
- fuzzy variants if factor definitions remain uncertain or linguistic

## What should be updated after your meeting

This document should be revised with:

- the agreed THI name and criteria list
- exact factor formulas
- data provenance by field
- whether normalization is global or segment-specific
- the chosen weighting approach
- whether Hilti wants a single production method or a research comparison of methods
