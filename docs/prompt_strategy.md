# Prompt strategy

## Compact prompt: 0–4

For a small, explicit task. It includes the goal, only necessary context, constraints, deliverables, and acceptance criteria.

## Structured prompt: 5–8

For a module or several related changes. It adds role, background, inputs, execution rules, forbidden actions, and final reporting.

## Staged prompt: 9–13

For work where analysis, design, implementation, testing, and delivery should have explicit handoffs. Each stage is a separate file with its own inputs, allowed actions, outputs, acceptance criteria, and dependency.

## Project prompt package: 14–18

For complete systems and cross-domain projects. It creates reusable project, architecture, implementation, testing, review, context, and acceptance files.

## Scoring behavior

Each dimension selects the highest matched 0–3 rule rather than adding keyword hits inside that dimension. This prevents repeated wording from inflating scores. Explicit structural signals such as a multi-domain embedded system can raise the relevant dimension when simple keywords are insufficient.

When details are inferred, ambiguity is at least level 1. A vague goal with no verifiable result is level 3 and blocks generation regardless of its total score.
