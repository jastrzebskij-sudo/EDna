# Elite Dangerous Companion Tools — UI/UX Style Guideline

Purpose: keep every custom tool we build (starting with the Ship's Computer project) visually consistent with "the Elite Dangerous look," the way EDCoPilot and EDSY do well and most other fan tools don't bother to. Reference this before starting any new tool's GUI.

---

## 1. The reference point: the in-game HUD

Everything below should be judged against the in-game HUD, not against other fan tools — most fan tools (see §3) don't actually replicate it.

- **Typeface**: no officially confirmed match. The strongest candidate is **Eurostile / Microgramma** (Aldo Novarese) — the classic squarish geometric "sci-fi HUD" font family used across *2001*, Star Trek, *Homeworld*, *StarCraft*. The practical, free fan substitute — already bundled inside EDCoPilot's own install (`EUROCAPS.TTF`) — is **"Euro Caps"** from dafont.com. HUD text is consistently **ALL CAPS with wide letter-spacing/tracking**.
- **Color**: no official published palette (the game ships a full user-configurable HUD color editor, orange is just the default). The best-corroborated approximation of default HUD orange, converging from two independent sources (EDMC's own theme code and a widely-shared CSS recreation), is **`#FF7A00`–`#FF8000`**, on a **near-black background (`#090707`–`#0d0d0d`)**. Red is reliably used for hostile/dangerous contacts regardless of a player's HUD color choice.
- **Layout motifs**: angular panels with cut/chamfered corners, thin glowing border lines, subtle scanline/bloom — well-attested by visual convention (CSS recreations, EDSY) rather than a documented Frontier style guide. Treat as strong community consensus, not gospel.
- **The real "trick"** (per EDSY, the fan tool that nails this best): don't invent a new brand — **quote the game's own configurable-HUD system**. Dark background, one saturated accent color, all-caps tracked type, angular chrome.

Sources / implementation references worth pulling from directly when building:
- EDMC's theme code (`#ff8000` on dark): https://github.com/EDCD/EDMarketConnector/blob/main/theme.py
- Working CSS recreation (colors, glow, angular borders, blink keyframes): https://gist.github.com/CodeMyUI/0e29780646f454f3aa8f996e831837fc
- EDSY's live "HUD Color Matrix" concept: https://edsy.org/
- Open CSS attempt at the look: https://github.com/Darkmift/Project_ED_UI

---

## 2. Concrete tokens to reuse

```css
:root {
  /* Core palette */
  --ed-bg:            #0a0908;   /* near-black background */
  --ed-bg-panel:       #14100c;  /* slightly raised panel */
  --ed-orange:         #ff8000;  /* primary HUD accent (default) */
  --ed-orange-dim:      #995000; /* muted/disabled state of accent */
  --ed-red-hostile:    #ff2b2b;  /* danger / hostile / wanted */
  --ed-yellow-caution: #ffcc00;  /* caution / unknown */
  --ed-green-safe:     #35d47a;  /* friendly / clean / ok (community convention, not Frontier-confirmed) */
  --ed-blue-alt:        #3fa9ff; /* alternate/secondary accent, e.g. for a second "voice"/app in a multi-tool UI */
  --ed-border:          rgba(255,128,0,0.35);
  --ed-glow: 0 0 6px rgba(255,128,0,0.55);

  /* Type */
  --ed-font-display: "Euro Caps", "Eurostile", "Orbitron", sans-serif; /* headers, labels, buttons — ALWAYS uppercase, tracked */
  --ed-font-body: "Titillium Web", "Sintony", system-ui, sans-serif;    /* body copy / data tables — keep readable at small sizes */
  --ed-tracking-display: 0.08em;
}
```

Usage rules:
- **Display font** (Euro Caps/Eurostile-alike) is for headers, tab labels, button text, section titles — always uppercase, always tracked. Never use it for dense body text or long-form descriptions; it hurts readability at small sizes.
- **Body font** carries actual data (tables, descriptions, logs). Keep it a clean, humanist sans — this is what EDCoPilot's settings GUI actually does (see §3) and it reads fine.
- One accent color drives the whole UI. Reserve red/yellow/green strictly for status meaning (hostile/caution/safe), never for decoration.
- Panels: flat dark fill, a single 1px accent-colored border, optionally a soft outer glow (`--ed-glow`) on focus/active state. Chamfer at least the top-left and bottom-right corners of major panels (`clip-path` polygon) for the angular HUD feel — don't overdo it on small interactive elements like checkboxes.
- Toggle switches, checkboxes, and active-state highlights: bright accent color when ON, muted/gray when OFF — this pattern is already correct in EDCoPilot's own settings GUI, worth keeping.

---

## 3. Audit of tools in our ecosystem

What we've actually seen firsthand (via screen access) or found documented — useful as concrete "do this / don't do this" examples.

| Tool | What it actually looks like | Verdict |
|---|---|---|
| **EDCoPilot** (settings GUI, `EDCoPilotGUI2`) | Dark near-black background with a warm vignette, white title bar, flat dark-gray section headers, pill-shaped ON/OFF toggles (cyan-ish ON, gray OFF), plain system sans-serif body text. Bundles Euro Caps/Eurostile fonts in its install but its **settings panels don't actually use them** — the config GUI reads as a generic, clean dark-mode settings app, not a HUD. (Its in-cockpit voice/overlay experience, which we haven't inspected, is likely where the true HUD styling lives.) | **Good bones** (dark, single accent, clean toggles), **missing the display type** in its own settings screens. Don't repeat that gap — use the display font where EDCoPilot didn't. |
| **EDDI** | Warm salmon/coral-red gradient background (vignette, darker at edges), white sidebar tab list, dense data-grid tables in a small light-green-ish monospace-adjacent font, standard blue checkboxes. Reads as a **utilitarian data-grid tool with a color tint**, not a HUD skin. | **Don't imitate.** Functional but generic; the reddish tint isn't a deliberate Elite HUD choice, more an ad-hoc accent color on top of a stock desktop-app data grid. |
| **EDMC** | Not inspected directly this session, but its source confirms a deliberate `#ff8000`-on-dark theme in `theme.py` — i.e. it **intentionally** echoes HUD orange-on-black, layered onto an otherwise plain Tkinter app. | Good color discipline despite a dated toolkit. Proof that even a "boring" GUI framework (Tkinter) can carry the palette correctly. |
| **EDSY** (ship builder) | Not inspected directly, but it literally reimplements the game's own **HUD Color Matrix** as a live webpage control (independent sliders for orange/red/blue/green/yellow) and separates a distinct "caps font" for headings from body/fixed-width fonts. | **Best-in-class example** of "quote the game's own system" — closest thing we have to a model to copy. |
| **EDDiscovery, Spansh, Inara** | Conventional light-themed desktop/web-app chrome; no evidence of deliberate HUD styling. | Useful **negative examples**: these read as generic community tools, not "in-universe" — exactly what we don't want our own tools to feel like. |
| **Coriolis** | Confirmed dark-first (`#000000` theme-color) but specific HUD-accent styling unverified without direct CSS inspection. | Presumed reasonable, not fully audited. |
| **COVAS:NEXT** | Has some GUI per its docs, but no visual detail could be confirmed without a live screenshot. | Unaudited — worth a direct look later, since it's our closest architectural prior art. |

---

## 4. Checklist for any new tool's GUI

- [ ] Near-black background, one dominant accent color (default: HUD orange `#ff8000`) — not a generic light theme, not a rainbow of accent colors
- [ ] Headers/labels/buttons in an uppercase, tracked "Euro Caps"/Eurostile-style display font
- [ ] Body/data text in a clean, readable sans — don't force the display font into dense tables
- [ ] Red/yellow/green reserved strictly for hostile/caution/safe status, never decorative
- [ ] Angular/chamfered panel corners on major containers, thin accent-colored borders, optional soft glow on focus/active states
- [ ] Toggles and active states: bright accent = ON, muted gray = OFF
- [ ] If the tool has a "second voice" or secondary identity (e.g. distinguishing from EDCoPilot in a multi-app setup), use the blue alt-accent rather than a totally unrelated color, to keep it reading as "same family, different member"
- [ ] Before shipping, sanity-check against §3's negative examples (EDDiscovery/Spansh/Inara) — if it reads like a generic settings app or community website, it's missing the point

---

## 5. Open items / unconfirmed

Flagged explicitly rather than guessed, per research pass — revisit if we need higher confidence:
- No official Frontier statement on the exact in-game typeface (Eurostile is the best-supported guess, not confirmed)
- No official published hex values for HUD orange, red, yellow, green, or a "second faction blue" — the values above are corroborated approximations from fan tooling, not Frontier canon
- COVAS:NEXT's and EDDiscovery's actual rendered UI weren't visually confirmed (text-only research); worth a direct screenshot pass later
- EDCoPilot's live in-cockpit HUD/overlay (as opposed to its settings GUI, which we did inspect) hasn't been seen — likely the better HUD-styling reference within our own toolset

---

**Note on this copy**: EDna's actual implemented theme (in `frontend/styles.css`) uses `"Orbitron"` (Google Fonts) rather than "Euro Caps" as the practical display-font substitute, since Euro Caps itself lives only inside EDCoPilot's own install and shouldn't be redistributed — otherwise the tokens above match what's implemented.

*Compiled from direct inspection of EDDI and EDCoPilot's settings GUI (this session) plus web research on the official HUD, EDMC, EDDiscovery, ED Materials Helper, Coriolis, EDSY, Spansh, Inara, and COVAS:NEXT. See citations inline above.*
