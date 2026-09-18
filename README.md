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