---
---
<!-- TEMPLATE-SHARED:HEADER -->
{# readme-header.html — used as the top of every repo README.md.

   Variables:
     org:    neohiro | fpm | osi | hplus
     title:  the repo name
     blurb:  one-line description

   Heartbeat also publishes /shared/repos/{owner}_{repo}/header.md which
   can be appended after this for project-specific badges/stats. #}

{%- assign org_label = include.org -%}
{%- case include.org -%}
{%- when 'neohiro' %}{% assign org_label = 'neohiro' %}{% when 'fpm' %}{% assign org_label = 'FrenzyPenguin Media' %}{% when 'osi' %}{% assign org_label = 'Open Stage Island' %}{% when 'hplus' %}{% assign org_label = 'transhumanists' %}{% endcase -%}

---

> **DEPRECATED** - This repo is archived.
> The Open Stage Island counter and docs site have moved to
> `openstageisland/openstageisland.github.io` (GitHub org creation pending).
> Counter slot `1631175` is reserved there. All traffic, issues, and PRs are
> closed. See `neohiro/openstageisland.github.io` for the current embed.
> If you have content to preserve, open an issue in
> `openstageisland/openstageisland` before the org transfer.

# {{ include.title }}

> {{ include.blurb }}

{% include badges.html org=include.org %}
{% include heartbeat-status.html %}
{% include sponsor-buttons.html %}
{% include contact-card.html %}

---

<!-- TEMPLATE-SHARED:FOOTER -->
{# readme-footer.html — used at the bottom of every repo README.md. #}

---
{% include legal-block.html %}
{% include social-links.html %}
{% include sponsor-buttons.html %}
{% include heartbeat-status.html %}

<sub>Synced from <code>template-shared/_includes/</code> — last publish: {{ site.time | date: '%Y-%m-%d %H:%M UTC' }}</sub>

---

<div align="center">
  <a href="https://visitorbadge.io/status?path=github.com%2Fopenstageisland%2Fopenstageisland.github.io" rel="noopener noreferrer nofollow"><img src="https://api.visitorbadge.io/api/visitors?path=github.com%2Fopenstageisland%2Fopenstageisland.github.io&label=Visitors&countColor=%23263759" alt="Visitors" /></a>
</div>
## SEO layer

Search metadata has one writer, `_includes/seo-head.html`, driven by
[`_data/seo.yml`](_data/seo.yml). `jekyll-seo-tag` is no longer enabled.

```bash
python scripts/build_seo.py         # regenerate llms.txt, graph, sitemap.xml
python scripts/build_seo.py --check # CI: fail if stale
python scripts/make_og.py           # re-render the 1200x630 card
python scripts/check_seo.py         # gate, against the built site
```

This is the only site in the network whose canonical host differs from its
repository name. Four pages carried a canonical pointing at
`openstageisland.github.io` while the CNAME serves `openstageis.land`, which
tells the engine to consolidate onto the repository host — the single most
expensive mistake available to a vanity-domain site. `check_seo.py` now asserts
`origin` matches `CNAME` on every build.

`sitemap.xml` is generated and committed here rather than left to GitHub Pages,
which emits one for Jekyll sites as undocumented platform behaviour: it held on
production while failing every local build.

The reference for the whole network is
[`template-shared/docs/seo-layer.md`](../template-shared/docs/seo-layer.md).