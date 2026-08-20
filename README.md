# kantan-setup-filters

Safari content blocker rules converted from EasyList, published for the
"かんたん設定" iOS app.

## Attribution and license

The rule sets in `docs/` are derived from **EasyList** and **EasyPrivacy**,
both maintained by the EasyList authors.

- Source: **The EasyList authors** — https://easylist.to/
- License: **Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)**
- https://creativecommons.org/licenses/by-sa/3.0/

EasyList is dual licensed under GPLv3 and CC BY-SA 3.0. This project uses it
under the CC BY-SA 3.0 option. The converted rule sets are therefore also
distributed under CC BY-SA 3.0.

The conversion script (`tools/convert.py`) is original work, released under
the MIT License. See `LICENSE`.

## What this does

A GitHub Actions workflow runs every Monday:

1. Fetches the latest EasyList and EasyPrivacy
2. Converts Adblock Plus syntax to Safari content-blocking JSON
3. Drops rules Safari cannot express (scriptlets, `$removeparam`, `$csp`,
   procedural cosmetic filters, and so on)
4. Trims the result to at most **120,000 rules**
5. Validates the output (JSON shape, regex validity, rule ordering)
6. Publishes to GitHub Pages

The current output is about **115,000 rules**: roughly 108,000 `block`,
5,300 `css-display-none`, and 1,400 `ignore-previous-rules`.

## Why 120,000 rules?

Apple documents a limit of 150,000 rules per content blocker. This project
started at 30,000 because loading was reported to fail well below Apple's limit
on older devices, but that turned out to be far too conservative: measured on an
iPad (A16, iPadOS 27), 115,000 rules load and run smoothly, and blocking went
from roughly 7% to 64% on the same test pages. The headroom below Apple's limit
is kept deliberately, because the failure mode is the whole list silently not
loading.

If a device is found where loading fails, lower `--limit` rather than dropping
whole source lists — the trim keeps the highest-value rules first.

## Cosmetic filters

Cosmetic filters (`##selector`) are converted to `css-display-none` actions and
are **included**, capped so they cannot crowd out network rules. They are what
removes the leftover empty boxes after a network request is blocked.

Procedural cosmetic filters (`:has-text()`, `:xpath()` and friends) are still
dropped — Safari cannot express them.

## Published URLs

Rules and app config:

- https://yamawebjpspike-del.github.io/kantan-setup-filters/blocklist.json
- https://yamawebjpspike-del.github.io/kantan-setup-filters/config.json

The app's legal documents are published from the same GitHub Pages site. They
are **generated from the app repository** by `Tools/publish_legal.py`; do not
edit the HTML here by hand.

- https://yamawebjpspike-del.github.io/kantan-setup-filters/privacy.html
- https://yamawebjpspike-del.github.io/kantan-setup-filters/terms.html
- https://yamawebjpspike-del.github.io/kantan-setup-filters/licenses.html

## Running locally

```sh
python3 tools/convert.py --output docs/blocklist.json
```

Options:

| Option | Meaning |
| --- | --- |
| `--url` | Source filter list URL |
| `--input` | Read a local file instead of downloading (for testing) |
| `--output` | Output path |
| `--limit` | Maximum number of rules (default 120000) |
| `--min-rules` | Fail if fewer rules than this are produced |
