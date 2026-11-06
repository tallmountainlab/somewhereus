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
    {{photo:key}}            -> photo with caption + credit (key from data/photos.json)

Optional front matter:
    image: <photo key>       -> cover photo, card photo and social image
    place: Siargao           -> short name on the home page postcards
    glance: Best time=Mar to Oct; Stay=4 to 7 days   -> "At a glance" box
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
PHOTOS_FILE = ROOT / "data" / "photos.json"
PHOTOS = json.loads(PHOTOS_FILE.read_text(encoding="utf-8")) if PHOTOS_FILE.exists() else {}
PHOTOS = {k: p for k, p in PHOTOS.items() if (ROOT / "static" / "img" / f"{k}.jpg").exists()}


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


def credit(p):
    """Short attribution line required by the CC licenses."""
    lic = html.escape(p.get("license", ""))
    if p.get("license_url"):
        lic = f'<a href="{html.escape(p["license_url"])}" rel="license noopener" target="_blank">{lic}</a>'
    return (f'Photo: <a href="{html.escape(p.get("page", ""))}" rel="noopener" target="_blank">'
            f'{html.escape(p.get("author", "Wikimedia Commons"))}</a>, {lic}, via Wikimedia Commons')


def img_tag(key, cls="", sizes="100vw", eager=False):
    p = PHOTOS.get(key)
    if not p:
        return ""
    load = ' fetchpriority="high"' if eager else ' loading="lazy"'
    return (f'<img class="{cls}" src="/img/{key}.jpg" '
            f'srcset="/img/{key}-sm.jpg 720w, /img/{key}.jpg 1600w" sizes="{sizes}" '
            f'alt="{html.escape(p["alt"])}"{load} decoding="async">')


def figure(key, cls="photo"):
    p = PHOTOS.get(key)
    if not p:
        return ""
    return (f'<figure class="{cls}">{img_tag(key, sizes="(max-width: 820px) 100vw, 800px")}'
            f'<figcaption>{html.escape(p["caption"])} <span class="credit">{credit(p)}</span></figcaption></figure>')


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", s).lower()).strip("-")


def shortcodes(body):
    body = re.sub(r"<p>\s*\{\{photo:([\w-]+)\}\}\s*</p>|\{\{photo:([\w-]+)\}\}",
                  lambda m: figure(m.group(1) or m.group(2)), body)
    body = re.sub(r"\{\{affiliate:(\w+)\}\}", lambda m: affiliate_box(m.group(1)), body)
    body = body.replace("<h2>Then and now</h2>", '<h2 class="then" id="then-and-now"><span>Memory lane</span>Then and now</h2>')
    body = re.sub(r"<h2>(.*?)</h2>", lambda m: f'<h2 id="{slugify(m.group(1))}">{m.group(1)}</h2>', body)
    body = body.replace("{{ad}}", ad_slot()).replace("{{newsletter}}", newsletter())
    return body


def toc(body):
    heads = re.findall(r'<h2[^>]*id="([^"]+)"[^>]*>(?:<span>[^<]*</span>)?(.*?)</h2>', body)
    if len(heads) < 3:
        return ""
    items = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in heads)
    return f'<nav class="toc" aria-label="In this guide"><p class="toc-h">In this guide</p><ol>{items}</ol></nav>'


def glance(g):
    if not g.get("glance"):
        return ""
    rows = []
    for part in g["glance"].split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            rows.append(f"<div><dt>{html.escape(k.strip())}</dt><dd>{html.escape(v.strip())}</dd></div>")
    return f'<aside class="glance"><p class="toc-h">At a glance</p><dl>{"".join(rows)}</dl></aside>'


def auto_photos(body, keys):
    """Place gallery photos before every other h2 that has no photo yet; leftovers go in an end gallery."""
    keys = [k for k in keys if k in PHOTOS and f"{{{{photo:{k}}}}}" not in body]
    parts = re.split(r"(?=<h2>)", body)
    out = [parts[0]]
    step = 2 if len(keys) <= (len(parts) - 1) // 2 else 1
    for n, part in enumerate(parts[1:], 1):
        prev = out[-1]
        if keys and n > 1 and n % step == 0 and "{{photo:" not in prev[-400:] and not part.startswith("<h2>Then and now"):
            out.append(f"{{{{photo:{keys.pop(0)}}}}}\n\n")
        out.append(part)
    body = "".join(out)
    if len(keys) == 1:
        body += f"\n{{{{photo:{keys[0]}}}}}"
    elif keys:
        tiles = "".join(f'<figure>{img_tag(k, "", "(max-width: 640px) 50vw, 360px")}'
                        f'<figcaption>{html.escape(PHOTOS[k]["caption"])} <span class="credit">{credit(PHOTOS[k])}</span></figcaption></figure>'
                        for k in keys)
        body += f'<h2>More pictures</h2><div class="gallery">{tiles}</div>'
    return body


def plan_box():
    affs = [a for a in SITE.get("affiliates", {}).values() if a.get("url")]
    if not affs:
        return ""
    items = "".join(f'<li><a href="{html.escape(a["url"])}" rel="sponsored nofollow noopener" target="_blank">'
                    f'{html.escape(a["label"])} &rarr;</a></li>' for a in affs)
    return ('<aside class="plan"><p class="toc-h">Plan your trip</p>'
            '<p class="small">The tools we would use to book this trip. Some are affiliate links, which '
            'support the site at no extra cost to you.</p>'
            f'<ul>{items}</ul></aside>')


def read_time(body):
    words = len(re.sub(r"<[^>]+>|\{\{[^}]+\}\}", " ", body).split())
    return max(1, round(words / 220))


def fmt_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return s


def render(title, description, content, path, extra_head="", image=None):
    head = extra_head
    image = image if image in PHOTOS else SITE.get("hero", {}).get("image")
    if image in PHOTOS:
        head += (f'<meta property="og:image" content="{SITE["url"]}/img/{image}.jpg">'
                 f'<meta name="twitter:image" content="{SITE["url"]}/img/{image}.jpg">'
                 '<meta name="twitter:card" content="summary_large_image">')
    else:
        head += '<meta name="twitter:card" content="summary">'
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
    pic = img_tag(g["image"], "card-img", "(max-width: 640px) 100vw, 360px") if g.get("image") in PHOTOS else ""
    return (
        f'<a class="card{" has-img" if pic else ""}" href="/guides/{g["slug"]}/">{pic}<div class="card-body">'
        f'<span class="kicker">{html.escape(g.get("category", "Guide"))}'
        f'{" · " + html.escape(g["country"]) if g.get("country") else ""}</span>'
        f'<h3>{html.escape(g["title"])}</h3>'
        f'<p>{html.escape(g.get("description", ""))}</p>'
        f'<span class="meta">{read_time(g["body"])} min read · Updated {fmt_date(g["updated"])}</span></div></a>'
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
    galleries = json.loads((ROOT / "data" / "galleries.json").read_text(encoding="utf-8")) \
        if (ROOT / "data" / "galleries.json").exists() else {}
    for i, g in enumerate(guides):
        same = [x for x in guides if x["slug"] != g["slug"] and x.get("category") == g.get("category")]
        other = [x for x in guides if x["slug"] != g["slug"] and x not in same]
        related = (same + other)[:3]
        ld = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": g["title"], "description": g.get("description", ""),
            "datePublished": g.get("date"), "dateModified": g["updated"],
            "publisher": {"@type": "Organization", "name": SITE["name"]},
        }
        if g.get("image") in PHOTOS:
            ld["image"] = f'{SITE["url"]}/img/{g["image"]}.jpg'
        crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE["url"] + "/"},
            {"@type": "ListItem", "position": 2, "name": "Guides", "item": SITE["url"] + "/guides/"},
            {"@type": "ListItem", "position": 3, "name": g["title"]}]}
        body = shortcodes(auto_photos(g["body"], galleries.get(g["slug"], [])))
        kicker = (f'<p class="kicker">{html.escape(g.get("category", "Guide"))}'
                  f'{" · " + html.escape(g["country"]) if g.get("country") else ""}</p>')
        title_block = (f'{kicker}<h1>{html.escape(g["title"])}</h1>'
                       f'<p class="lede">{html.escape(g.get("description", ""))}</p>')
        meta = (f'<p class="meta">{read_time(g["body"])} min read · Last reviewed {fmt_date(g["updated"])} · '
                '<a href="/disclosure/">How we make money</a></p>')
        if g.get("image") in PHOTOS:
            p = PHOTOS[g["image"]]
            top = (f'<header class="cover">{img_tag(g["image"], "cover-img", eager=True)}'
                   f'<div class="cover-text"><div class="post-w">{title_block}</div></div></header>'
                   f'<p class="cover-credit post-w">{html.escape(p["caption"])} · {credit(p)}</p>')
            title_block = ""
        else:
            top = ""
        crumb_html = (f'<p class="crumbs"><a href="/">Home</a> › <a href="/guides/">Guides</a> › '
                      f'{html.escape(g.get("place") or g.get("country") or g["title"])}</p>')
        content = (
            top + '<article class="post">' + crumb_html + title_block + meta
            + glance(g) + toc(body)
            + f'{ad_slot()}<div class="prose">{body}</div>'
            + plan_box()
            + f'<p class="note">{html.escape(SITE["article_note"])}</p>'
            f"{newsletter()}"
            '<h2 class="more">Keep exploring</h2><div class="grid">'
            + "".join(card(r) for r in related) + "</div></article>"
        )
        write(f"guides/{g['slug']}/index.html", render(
            g["title"], g.get("description", ""), content, f"/guides/{g['slug']}/",
            f'<script type="application/ld+json">{json.dumps(ld)}</script>'
            f'<script type="application/ld+json">{json.dumps(crumbs)}</script><meta property="og:type" content="article">',
            g.get("image")))

    # Guides index
    write("guides/index.html", render(
        "All guides", SITE["guides_description"],
        '<section class="wrap"><h1>All guides</h1><div class="grid">'
        + "".join(card(g) for g in guides) + "</div></section>", "/guides/"))

    # Home
    hero_cfg = SITE["hero"]
    hero = PHOTOS.get(hero_cfg.get("image", ""))
    hero_open = ('<section class="hero photo-hero">' + img_tag(hero_cfg["image"], "hero-img", eager=True)
                 + '<div class="wrap hero-inner">') if hero else '<section class="hero"><div class="wrap">'
    with_img = [g for g in guides if g.get("image") in PHOTOS]
    stack = "".join(
        f'<a class="postcard" href="/guides/{g["slug"]}/">'
        f'{img_tag(g["image"], "", "(max-width: 640px) 50vw, 260px")}'
        f'<span>{html.escape(g.get("place") or g.get("country", ""))}</span></a>'
        for g in with_img[:4])
    start_here = [g for g in guides if g.get("start") == "true"][:3]
    tn = SITE.get("then_now", {})
    then_now = ""
    if tn.get("image") in PHOTOS:
        then_now = (
            '<section class="thennow"><div class="wrap tn-grid">'
            f'{figure(tn["image"], "photo tn-map")}'
            f'<div><p class="kicker">Then and now</p><h2>{html.escape(tn["title"])}</h2>'
            + "".join(f"<p>{html.escape(t)}</p>" for t in tn["text"])
            + '<a class="btn ghost" href="/about/">Why we started ' + html.escape(SITE["name"]) + '</a></div></div></section>')
    home = (
        hero_open
        + f'<p class="kicker">{html.escape(hero_cfg["kicker"])}</p>'
        f'<h1>{html.escape(hero_cfg["title"])}</h1>'
        f'<p>{html.escape(hero_cfg["text"])}</p>'
        '<a class="btn" href="/guides/">Browse the guides</a></div>'
        + (f'<p class="hero-credit">{html.escape(hero["caption"])} · {credit(hero)}</p>' if hero else "")
        + '</section>'
        + (('<section class="wrap"><div class="section-head"><p class="kicker">Postcards from the road</p>'
            f'<h2>{html.escape(SITE.get("postcards_title", "Where do you want to wake up next?"))}</h2></div>'
            f'<div class="postcards">{stack}</div></section>') if stack else "")
        + (('<section class="wrap"><h2>Start here</h2><div class="grid">'
            + "".join(card(g) for g in start_here) + "</div></section>") if start_here else "")
        + '<section class="wrap"><h2>Latest guides</h2><div class="grid">'
        + "".join(card(g) for g in [x for x in guides if x not in start_here][:6]) + "</div>"
        f"{ad_slot()}{newsletter()}</section>"
        + then_now
    )
    write("index.html", render(SITE["name"], SITE["description"], home, "/"))

    # Static pages
    for p in (ROOT / "content" / "pages").glob("*.html"):
        pg = parse(p)
        write(f"{pg['slug']}/index.html", render(
            pg["title"], pg.get("description", ""),
            f'<article class="post"><h1>{html.escape(pg["title"])}</h1>'
            f'<div class="prose">{shortcodes(pg["body"])}</div></article>', f"/{pg['slug']}/"))

    # Photo credits
    rows = "".join(
        f'<li><a href="/img/{k}.jpg"><img src="/img/{k}-sm.jpg" alt="" loading="lazy"></a>'
        f'<div><strong>{html.escape(p["caption"])}</strong><br>{credit(p)}</div></li>'
        for k, p in PHOTOS.items() if p.get("author"))
    write("photo-credits/index.html", render(
        "Photo credits", f"The photographers behind the pictures on {SITE['name']}.",
        '<article class="post"><h1>Photo credits</h1><p>The photos on this site come from Wikimedia Commons and are '
        'shared under Creative Commons or public-domain licenses. Thank you to every photographer below. '
        'We resize the images for the web but do not otherwise change them.</p>'
        f'<ul class="credits">{rows}</ul></article>', "/photo-credits/"))

    # 404
    write("404.html", render("Page not found", "", '<section class="wrap"><h1>Page not found</h1>'
          '<p><a href="/guides/">See all guides</a></p></section>', "/404"))

    # Sitemap, robots, RSS
    urls = ["/", "/guides/", "/photo-credits/"] + [f"/guides/{g['slug']}/" for g in guides] + \
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
