---
this_file: TODO.md
---

- [ ] Union of jina and gemma links (see PLAN item 0)
- [ ] Full-book normalize run (overnight) and yield comparison against raw markdown
- [ ] Time a 4B-class model for the normalize stage
- [ ] Decide on trigram spans after inspecting the full-book TMX
- [ ] Language-split for multilingual single volumes (`de-en` folders)
- [ ] Batch run over all 40 books; OCR language packs for scanned PDFs
- [ ] docling segfaults (exit -11) on some scans (Ogilvy on Advertising en): try ocrmac or page-batched OCR as a fallback engine

## Release tooling — completed 2026-09-12

- [x] Provide verified Git-tag releases, a real dry run, same-tag retries, and private-data exclusions.
