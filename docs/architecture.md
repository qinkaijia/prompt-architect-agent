# Architecture

Prompt Architect Agent separates task understanding, routing, rendering, publishing, and local application surfaces so future analyzers can change without breaking the CLI or HTTP contracts.

## Data flow

1. `RequirementAnalyzer` redacts secrets, classifies the task, infers safe defaults, and records field provenance.
2. `ComplexityScorer` assigns six independent scores and explains every result.
3. `StrategyRouter` maps the total to one strategy. Disabling staging can downgrade a complex task, but cannot force a project-level task into one prompt.
4. `ContextManager` classifies supplied paths as required, optional, reference-only, or ignored. It checks path existence but does not read file contents.
5. `AdapterRegistry` selects target-specific operating guidance from YAML profiles.
6. `PromptCompiler` renders packaged Jinja templates and creates the appropriate artifact set.
7. `PromptReviewer` applies safety and completeness rules. One deterministic repair pass is allowed.
8. `PromptArchitect.build()` returns a reviewed in-memory result; `generate()` preserves the CLI publishing contract.
9. `ArtifactPublisher` writes to a temporary directory and atomically renames it only after review passes.
10. `RunService` indexes successful runs in SQLite while keeping Markdown and JSON as ordinary files.
11. FastAPI exposes the same core to the React workbench and pywebview desktop shell.

## Public models

- `TaskSpec`: normalized request, target, deliverables, context, constraints, risk, score, strategy, provenance, and blockers.
- `ComplexityAssessment`: six `DimensionScore` values, total, strategy, and explanation.
- `ContextManifest`: categorized file references and read conditions.
- `PromptArtifact`: filename and rendered Markdown.
- `ReviewResult`: pass state, score, issues, suggestions, and repair state.
- `GenerationResult`: complete in-memory result plus the published output path.

The Web API adds `GenerationRequest`, `AnalysisResponse`, `RunSummary`, `RunDetail`, `ArtifactMetadata`, and `ApiError`. API models reuse the core enums and never serialize `raw_request`.

The original request is excluded from Pydantic serialization. Only the redacted request is persisted. SQLite stores searchable metadata and file indexes; artifact contents remain in the managed run directory.

## Local application boundary

- FastAPI binds to loopback and serves the built React application on the same origin.
- The desktop bridge exposes only file selection, directory selection, and opening a managed run folder.
- Artifact lookup requires both a database entry and path containment within the managed runs root.
- A failed database insert rolls back the just-published directory; if the process is interrupted between publishing and indexing, startup reconciliation restores the missing index.
- CLI output remains relative to the current directory, while desktop and Web output uses the platform application-data directory.

## Extension points

`RuleTaskClassifier`, `ModelAdapter`, `ContextManager`, `PromptCompiler`, `PromptReviewer`, `HistoryStore`, and `RunService` have narrow interfaces. Later releases can add LLM classification, opt-in repository scanning, PDF indexing, and feedback without changing strategy semantics.
