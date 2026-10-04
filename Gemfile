source "https://rubygems.org"

gem "jekyll", "~> 4.3"
gem "kramdown-parser-gfm"
gem "webrick", "~> 1.8"
# Required by {% seo %} in _layouts/default.html. Liquid raises on unknown tags
# in every error mode, so without this gem `jekyll build` fails outright. The
# GitHub Pages build tolerates the missing gem because its own whitelist loads
# jekyll-seo-tag, which is why only CI was red.
gem "jekyll-seo-tag", "~> 2.8"
