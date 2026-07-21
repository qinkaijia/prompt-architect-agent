# Architecture

Prompt Architect Agent separates task understanding, routing, rendering, and publishing so that future LLM-assisted analyzers can replace rule implementations without changing the CLI contract.

## Data flow

1. `RequirementAnalyzer` redacts secrets, classifies the task, infers safe defaults, and records field provenance.
2. `ComplexityScorer` assigns six independent scores and explains every result.
3. `StrategyRouter` maps the total to one strategy. Disabling staging can downgrade a complex task, but cannot force a project-level task into one prompt.
4. `ContextManager` classifies supplied paths as required, optional, reference-only, or ignored. It checks path existence but does not read file contents.
5. `AdapterRegistry` selects target-specific operating guidance from YAML profiles.
6. `PromptCompiler` renders packaged Jinja templates and creates the appropriate artifact set.
7. `PromptReviewer` applies safety and completeness rules. One deterministic repair pass is allowed.
8. `ArtifactPublisher` writes to a temporary directory and atomically renames it only after review passes.

## Public models

- `TaskSpec`: normalized request, target, deliverables, context, constraints, risk, score, strategy, provenance, and blockers.
- `ComplexityAssessment`: six `DimensionScore` values, total, strategy, and explanation.
- `ContextManifest`: categorized file references and read conditions.
- `PromptArtifact`: filename and rendered Markdown.
- `ReviewResult`: pass state, score, issues, suggestions, and repair state.
- `GenerationResult`: complete in-memory result plus the published output path.

The original request is excluded from Pydantic serialization. Only the redacted request is persisted.

## Extension points

`RuleTaskClassifier`, `ModelAdapter`, `ContextManager`, `PromptCompiler`, and `PromptReviewer` have narrow interfaces. Later releases can add LLM classification, repository scanning, PDF indexing, feedback storage, and web APIs without changing strategy semantics.
