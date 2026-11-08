# Claude Book Knowledge System

Turn books into a knowledge library that Claude Code skills use to discover, design, build and test software.

## Pipeline

```text
books.txt ──► ./books (pdf2md) ──► knowledge/<book>/chapters/   (script: raw text + page markers)
                                            │
                       /extract-book <book> ▼
                                    knowledge/<book>/notes.md      (Claude: deep notes)
                                            │
                                            ▼
                               role-skills/<role>/SKILL.md         (reads notes, greps chapters)
```

## Layout

```text
knowledge/
├── books.txt                 # "<slug> <path to pdf, relative to BOOKS_DIR>"
└── <slug>/
    ├── chapters/NN-title.md  # generated, gitignored (copyrighted text)
    └── notes.md              # written by Claude, committed
```

## notes.md

1. **Overview** – thesis, mental model, chapter → topic map, missing pages.
2. **Concepts** – one section each:
   - **Claim** (with page), **Why**, **When / when not**, **How to apply**, **Anti-pattern**, **Review question + evidence**, **Related**
   - Mark anything that is your own interpretation or example with *(interpretation)*.
3. **Checklist** – review questions the skills ask.

Split it into `notes/<topic>.md` only if it grows past ~500 lines.

Example concept:

> **Deep modules** (p. NN)
> - **Claim:** a good module hides a lot of complexity behind a simple interface.
> - **Why:** many tiny classes add interfaces that callers have to learn.
> - **When not:** a small module with a clear, stable job is fine.
> - **Anti-pattern:** layers that only pass calls through.
> - **Review:** does the API hide real detail, or just forward calls? Evidence: interface size, number of calls a use case needs, implementation details that leak out.

## Rules

1. **Only cite what's in `chapters/`.** Never invent pages or quotes, and say which pages are missing. `p.N` means PDF page N (from the `<!-- p.N -->` markers), not the number printed in the book.
2. **Keep the reasoning, not just the rule.** Include the why, the trade-offs and the exceptions; paraphrase instead of copying long passages.
3. **Skills use judgment, not dogma.** When books conflict, explain the context, then record the decision and any open questions.
4. **Skills keep `SKILL.md` short.** Read `notes.md` first, then grep `chapters/` for exact detail.

## Skills

| Skill | Books | Writes to |
|---|---|---|
| product-manager | The Mom Test, Inspired | `docs/product/` – vision, discovery, roadmap, PRD |
| ux-designer | About Face, Don't Make Me Think | `docs/ux/` – personas, journeys, flows, UI spec |
| software-architect | Learning DDD, DDD (Evans), Clean Architecture, Fundamentals of SA, Philosophy of SD, PoEAA | `docs/architecture/` – domain model, contexts, APIs, ADRs, Mermaid diagrams |
| software-engineer | Philosophy of SD, Pragmatic Programmer, Refactoring, Clean Code | `docs/engineering/` – plan, tasks, notes |
| qa-engineer | *later: needs books (see plan.md)* | `docs/qa/` – strategy, plan, cases, report |

Every skill should:
- read the existing project docs first
- separate evidence, assumptions and recommendations
- trace customer problems through requirements, design, code and tests
- ask before making consequential decisions
- send findings back upstream when they disprove an earlier assumption

## Done when

Given a real proposal, a skill finds the relevant concepts, cites pages, explains why they apply, challenges weak assumptions and writes a useful Markdown document.
