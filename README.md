# kantan-setup-filters

Safari content blocker rules converted from EasyList, published for the
"かんたん設定" iOS app.

## Attribution and license

The rule sets in `docs/` are derived from **EasyList**.

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

1. Fetches the latest EasyList
2. Converts Adblock Plus syntax to Safari content-blocking JSON
3. Drops rules Safari cannot express (scriptlets, `$removeparam`, `$csp`,
   procedural cosmetic filters, and so on)
4. Trims the result to at most **30,000 rules**
5. Validates the output (JSON shape, regex validity, rule ordering)
6. Publishes to GitHub Pages

## Why only 30,000 rules?

Apple documents a limit of 150,000 rules per content blocker, but in practice
loading fails well below that on older devices — there are reports of failures
from around 45,000 rules on an iPhone 12 running iOS 18, and AdGuard had to
shrink its rule sets after iOS 17. The target users of the app are often on
older iPhones, so this project stays conservative.

## Why no cosmetic filters?

Cosmetic filters (`##selector`) consume a large share of the rule budget and
are the main source of visual breakage. The app's users generally cannot
diagnose why a page looks wrong, so this project blocks network requests only.

## Published URLs

- https://yamawebjpspike-del.github.io/kantan-setup-filters/blocklist.json
- https://yamawebjpspike-del.github.io/kantan-setup-filters/config.json

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
| `--limit` | Maximum number of rules (default 30000) |
| `--min-rules` | Fail if fewer rules than this are produced |
