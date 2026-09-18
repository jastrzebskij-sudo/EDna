# EDCoPilot EULA — Reverse-Engineering / Companion-Tool Risk Review

Source: https://www.razzafrag.com/eula (developer: Razzafrag Technology Inc., cmdr_razzafrag@outlook.com). Full verbatim text not reproduced here — fetch tooling paraphrased it; for exact clause wording, view the page directly or the text shown at install.

## What the EULA actually says

1. **Reverse engineering**: Explicitly prohibited — "decompile, disassemble or reverse engineer the Application or attempt to do any such things." Standard blanket clause, targets the *software binary*, not files it produces.
2. **Third-party tools reading/writing its data files**: Not addressed. A modification/combination clause bars the Application itself being "combined with or become incorporated in any other software" (aimed at bundling/embedding, not a separate tool reading a plain-text save file). Silent on programmatic use of the data files specifically.
3. **Redistribution / publishing a companion tool**: Only *commercial* distribution/resale of the Application itself is barred. Publishing an independent, free, open-source GUI tool isn't redistribution of EDCoPilot — not addressed either way.
4. **Binary inspection short of decompiling** (e.g. `strings`/PE header analysis): Not distinguished from decompiling in the text found; "or attempt to do any such things" could be stretched to cover it. Grayer and lower-risk than actual decompilation, but not cleanly excluded.
5. **License scope**: Revocable, personal, non-transferable, non-exclusive, non-commercial-use license. Governed by Canadian law.

## Risk assessment

- **Editing the `SaveData...LIVE.txt` file (this project's v1 scope): Low risk.** It's a config/data file, not the Application binary — no clause covers third-party editing of it. The developer's own external-TTS hook (`shipai_log.json`) shows they already expect external programs to interoperate via files.
- **Building and open-sourcing the companion GUI tool: Low-to-moderate, mostly EULA-silent risk**, not a clear violation. Avoid: decompiling/reverse-engineering the `.exe` (skip or treat binary inspection as gray-zone, don't publish findings from it), don't bundle/redistribute EDCoPilot's own binaries, don't claim official/affiliated status. Several ecosystem tools already exist on GitHub (`EDCoPilot-Installer`, `EDCoPTER`, `EDCoLauncher`), suggesting practical/social tolerance is high — but EULA silence isn't permission. Cleanest path: ask Razzafrag directly (Discord/email) before public release, especially before any exe inspection.

## Bottom line for this project

Proceed with the SaveData-file editor (EDCV Manager) — low risk as scoped. Hold off on any further binary/exe inspection of EDCoPilot until either (a) Razzafrag is asked directly, or (b) it's judged not worth the marginal legal ambiguity for the value it adds.
