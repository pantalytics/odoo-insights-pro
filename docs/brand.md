# Brand and design rules (from brand.pantalytics.com, read 10-11-2026)

The bar for every screen in this repo. Philosophy: less is more, like Apple.
If removing something loses no function, remove it.

## Principles
1. Progressive disclosure: result first, detail on demand.
2. Simplicity first: only elements that earn their place. No confirmation when undo exists.
3. Odoo-native where possible: standard widgets and views before custom code or CSS.
4. Accessible by default: WCAG AA, clear focus, readable sizes.
5. Content over chrome: data leads, controls stay quiet.

## Colour
- Status only: green works, amber needs the user, red broken, grey off or not started.
- Accent purple `#5b58d8` (dark mode `#9b99ff`, never as text on white): primary action, links, selection. Never a status.
- Everything else neutral; chrome monochrome. Depth is a 1px border, no shadows.

## Type and copy
- Font Murecho (400 text, 500 headings and labels, 700 only for emphasis). Inside the Odoo backend we keep Odoo's font for native views and use Murecho only in our own map.
- Sentence case everywhere. Buttons: verb + thing. No explainer under a title; help text at most one sentence. Errors: what happened and what to do. No em dashes, no buzzwords.

## Components (per brand)
- One primary button per screen; other actions outline; row actions ghost.
- Badge = status of one thing, one or two words.
- Empty state: one muted line, at most one action, dashed border, no illustration.
- Never unfold a panel below a list; the eye stays where it is.
- Motion 150-200 ms, transform and opacity only, none with reduced motion.
- Click feedback within 100 ms; skeleton only after 300 ms; no full-page spinner.

## Checklist before a commit that touches UI
- One primary action per screen; colour only for status; accent only for action, links and selection.
- Copy in sentence case, verb + thing, no explainers.
- Every touched action clicked and judged right after the click, at 1440 px and 390 px.
