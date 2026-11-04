#!/usr/bin/env python3
"""Build this travel site into ./public. No dependencies, just Python 3.

Content lives in content/guides/*.html and content/pages/*.html.
Each file starts with a front-matter block:

    ---
    title: Mexico City for remote workers
    description: One-line summary for Google and social cards.
    date: 2026-10-31
    updated: 2026-10-31
    category: City guide
    country: Mexico
    ---
    <p>Body HTML...</p>

Shortcodes inside the body:
    {{affiliate:insurance}}  -> affiliate box (hidden until the URL is set in site.json)
    {{ad}}                   -> ad slot (hidden until adsense_client_id is set)
    {{newsletter}}           -> newsletter sign-up box
"""
import html
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "public"
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")


def parse(path):
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    meta["slug"] = path.stem
    meta["body"] = body.strip()
    meta.setdefault("updated", meta.get("date", ""))
    return meta


def affiliate_box(key):
    aff = SITE.get("affiliates", {}).get(key)
    if not aff or not aff.get("url"):
        return ""
    return (
        '<aside class="aff"><span class="aff-tag">Recommended</span>'
        f'<a href="{html.escape(aff["url"])}" rel="sponsored nofollow noopener" target="_blank">'
        f'{html.escape(aff["label"])} &rarr;</a></aside>'
    )


def ad_slot():
    cid = SITE.get("adsense_client_id")
    if not cid:
        return ""
    return (
        '<div class="ad"><ins class="adsbygoogle" style="display:block" '
        f'data-ad-client="{html.escape(cid)}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        "<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>"
    )


def newsletter():
    action = SITE.get("newsletter_form_action")
    if not action:
        return ""
    return (
        f'<section class="news"><h3>{html.escape(SITE["newsletter"]["title"])}</h3>'
        f'<p>{html.escape(SITE["newsletter"]["text"])}</p>'
        f'<form action="{html.escape(action)}" method="post" target="_blank">'
        '<input type="email" name="email" placeholder="you@example.com" required aria-label="Email">'
        "<button>Subscribe</button></form></section>"
    )


def shortcodes(body):
    body = re.sub(r"\{\{affiliate:(\w+)\}\}", lambda m: affiliate_box(m.group(1)), body)
    body = body.replace("<h2>Then and now</h2>", '<h2 class="then"><span>Memory lane</span>Then and now</h2>')
    body = body.replace("{{ad}}", ad_slot()).replace("{{newsletter}}", newsletter())
    return body


def fmt_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return s


def render(title, description, content, path, extra_head=""):
    head = extra_head
    if SITE.get("adsense_client_id"):
        head += (
            '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
            f'?client={html.escape(SITE["adsense_client_id"])}" crossorigin="anonymous"></script>'
        )
    if SITE.get("travelpayouts_drive_src"):
        # Travelpayouts Drive: turns plain partner links into affiliate links (no pop-ups)
        head += (
            '<script nowprocket data-noptimize="1" data-cfasync="false" data-wpfc-render="false" '
            'seraph-accel-crit="1" data-no-defer="1" data-cmp-ab="2">\n'
            '  (function () {\n'
            '      var script = document.createElement("script");\n'
            '      script.async = 1;\n'
            '      script.setAttribute("data-cmp-ab","2");\n'
            f"      script.src = '{SITE['travelpayouts_drive_src']}';\n"
            '      document.head.appendChild(script);\n'
            '  })();\n'
            '</script>'
        )
    full_title = title if title == SITE["name"] else f"{title} | {SITE['name']}"
    out = TEMPLATE
    for k, v in {
        "{{title}}": html.escape(full_title),
        "{{description}}": html.escape(description),
        "{{canonical}}": SITE["url"] + path,
        "{{site_name}}": SITE["name"],
        "{{tagline}}": html.escape(SITE["tagline"]),
        "{{extra_head}}": head,
        "{{content}}": content,
        "{{year}}": str(date.today().year),
        "{{contact_email}}": SITE["contact_email"],
        "{{fonts_href}}": SITE["fonts_href"],
        "{{logo_a}}": SITE["logo"][0],
        "{{logo_b}}": SITE["logo"][1],
    }.items():
        out = out.replace(k, v)
    return out


def write(rel, text):
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def card(g):
    return (
        f'<a class="card" href="/guides/{g["slug"]}/">'
        f'<span class="kicker">{html.escape(g.get("category", "Guide"))}'
        f'{" · " + html.escape(g["country"]) if g.get("country") else ""}</span>'
        f'<h3>{html.escape(g["title"])}</h3>'
        f'<p>{html.escape(g.get("description", ""))}</p>'
        f'<span class="meta">Updated {fmt_date(g["updated"])}</span></a>'
    )


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT, dirs_exist_ok=True)

    guides = [parse(p) for p in (ROOT / "content" / "guides").glob("*.html")]
    guides = [g for g in guides if g.get("draft", "").lower() != "true"]
    guides.sort(key=lambda g: (g.get("featured") == "true", g["updated"]), reverse=True)

    # Guide pages
    for g in guides:
        related = [x for x in guides if x["slug"] != g["slug"]][:3]
        ld = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": g["title"], "description": g.get("description", ""),
            "datePublished": g.get("date"), "dateModified": g["updated"],
            "publisher": {"@type": "Organization", "name": SITE["name"]},
        }
        content = (
            '<article class="post">'
            f'<p class="kicker">{html.escape(g.get("category", "Guide"))}'
            f'{" · " + html.escape(g["country"]) if g.get("country") else ""}</p>'
            f'<h1>{html.escape(g["title"])}</h1>'
            f'<p class="lede">{html.escape(g.get("description", ""))}</p>'
            f'<p class="meta">Last reviewed {fmt_date(g["updated"])} · '
            '<a href="/disclosure/">How we make money</a></p>'
            f'{ad_slot()}<div class="prose">{shortcodes(g["body"])}</div>'
            f'<p class="note">{html.escape(SITE["article_note"])}</p>'
            f"{newsletter()}"
            '<h2 class="more">Keep reading</h2><div class="grid">'
            + "".join(card(r) for r in related) + "</div></article>"
        )
        write(f"guides/{g['slug']}/index.html", render(
            g["title"], g.get("description", ""), content, f"/guides/{g['slug']}/",
            f'<script type="application/ld+json">{json.dumps(ld)}</script><meta property="og:type" content="article">'))

    # Guides index
    write("guides/index.html", render(
        "All guides", SITE["guides_description"],
        '<section class="wrap"><h1>All guides</h1><div class="grid">'
        + "".join(card(g) for g in guides) + "</div></section>", "/guides/"))

    # Home
    home = (
        '<section class="hero"><div class="wrap">'
        f'<p class="kicker">{html.escape(SITE["hero"]["kicker"])}</p>'
        f'<h1>{html.escape(SITE["hero"]["title"])}</h1>'
        f'<p>{html.escape(SITE["hero"]["text"])}</p>'
        '<a class="btn" href="/guides/">Browse the guides</a></div></section>'
        '<section class="wrap"><h2>Postcards from the road</h2><div class="grid">'
        + "".join(card(g) for g in guides[:6]) + "</div>"
        f"{ad_slot()}{newsletter()}</section>"
    )
    write("index.html", render(SITE["name"], SITE["description"], home, "/"))

    # Static pages
    for p in (ROOT / "content" / "pages").glob("*.html"):
        pg = parse(p)
        write(f"{pg['slug']}/index.html", render(
            pg["title"], pg.get("description", ""),
            f'<article class="post"><h1>{html.escape(pg["title"])}</h1>'
            f'<div class="prose">{shortcodes(pg["body"])}</div></article>', f"/{pg['slug']}/"))

    # 404
    write("404.html", render("Page not found", "", '<section class="wrap"><h1>Page not found</h1>'
          '<p><a href="/guides/">See all guides</a></p></section>', "/404"))

    # Sitemap, robots, RSS
    urls = ["/", "/guides/"] + [f"/guides/{g['slug']}/" for g in guides] + \
           [f"/{p.stem}/" for p in (ROOT / "content" / "pages").glob("*.html")]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"  <url><loc>{SITE['url']}{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    ai_training = ["GPTBot", "Google-Extended", "CCBot", "ClaudeBot", "anthropic-ai", "Bytespider",
                   "Applebot-Extended", "meta-externalagent", "Amazonbot", "cohere-training-data-crawler"]
    robots = "".join(f"User-agent: {b}\nDisallow: /\n\n" for b in ai_training)
    write("robots.txt", robots + f"User-agent: *\nAllow: /\nSitemap: {SITE['url']}/sitemap.xml\n")
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(
        f"<item><title>{html.escape(g['title'])}</title><link>{SITE['url']}/guides/{g['slug']}/</link>"
        f"<guid>{SITE['url']}/guides/{g['slug']}/</guid><description>{html.escape(g.get('description', ''))}</description></item>"
        for g in guides[:20])
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
          f"<title>{SITE['name']}</title><link>{SITE['url']}</link>"
          f"<description>{html.escape(SITE['description'])}</description><lastBuildDate>{now}</lastBuildDate>"
          f"{items}</channel></rss>")
    if SITE.get("adsense_client_id"):
        pub = SITE["adsense_client_id"].replace("ca-", "")
        write("ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")

    print(f"Built {len(guides)} guides into {OUT}")


if __name__ == "__main__":
    main()
