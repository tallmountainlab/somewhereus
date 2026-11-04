# somewhereus.com

Static travel site: road trips, national parks and weekends away in the usa.

- `content/guides/*.html` – articles (front matter + HTML body)
- `content/pages/*.html` – about, disclosure, privacy
- `site.json` – site settings, hero text, AdSense ID, newsletter form, affiliate links (empty = hidden)
- `templates/base.html`, `static/` – layout, CSS, favicon
- `build.py` – zero-dependency builder, writes `public/`

Build: `python3 build.py`. Host: Cloudflare Workers static assets via `wrangler.jsonc` (serves the prebuilt, committed `public/`; deploy command `npx wrangler deploy`, no build command).

Shortcodes in article bodies: `{{affiliate:stays|car|rv|tours|gear|insurance}}`, `{{ad}}`, `{{newsletter}}`.
Mark a guide `draft: true` to hide it, `featured: true` to pin it first.
