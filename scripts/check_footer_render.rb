# Renders the footer partials with Liquid and runs the site's own rendered-HTML
# gate over the result, for every combination of `current`. Stand-in for the
# `jekyll build` that cannot run locally on this machine (http_parser.rb, a
# native gem, will not install on Windows).
#
#   ruby scripts/check_footer_render.rb
#
# Renders each partial inside a minimal page shell and wraps the result in
# index.md's <main> so the gate sees the heading sequence a real page has.
require "liquid"
require "open3"
require "tmpdir"
require "fileutils"
require "rbconfig"

ROOT = File.expand_path("..", __dir__)

# Liquid::Template.parse is strict: unbalanced tags raise here rather than
# shipping a page with a literal "{%" in it.
def render(path, assigns)
  Liquid::Template.parse(File.read(path), error_mode: :strict).render!(assigns)
end

partials = {
  "ecosystem" => "_includes/ecosystem-network.html",
  "bottom-bar" => "_includes/bottom-bar.html"
}

# `current` values the four layouts pass, plus nil for a caller that omits it.
currents = %w[neohiro fpm transhumanists openstageisland] + [nil]

failures = []

currents.each do |current|
  # Jekyll exposes an include's parameters under `include`, not as bare
  # variables. Rendering with a bare `current` would be silently ignored by the
  # partial and every case would collapse to the same all-links output, which
  # is exactly the kind of false green this script exists to catch.
  assigns = { "include" => { "current" => current } }
  partials.each do |name, rel|
    body = render(File.join(ROOT, rel), assigns)

    # bottom-bar.html links to the guide sections by fragment, and the gate
    # requires every same-document anchor to resolve. Stand up a stub section
    # per id it emits so that check is exercised rather than trivially failing.
    stubs = body.scan(/href="#([\w-]+)"/).flatten.uniq.map do |id|
      %(<section id="#{id}"><h2>#{id}</h2></section>)
    end.join("\n")

    page = <<~HTML
      <!DOCTYPE html>
      <html lang="en">
      <head><meta charset="UTF-8"><title>#{name}</title>
      <meta name="description" content="rendered footer partial">
      <meta http-equiv="Content-Security-Policy" content="default-src 'self'"></head>
      <body>
      <main>
      <h1>Fixture</h1>
      #{stubs}
      #{body}
      </main>
      </body>
      </html>
    HTML

    # One site dir per page: the gate scans everything under --site, so a shared
    # dir would report a failure on an earlier page against a later page.
    Dir.mktmpdir("footer-render") do |dir|
      site = File.join(dir, "_site", "index.html")
      FileUtils.mkdir_p(File.dirname(site))
      File.write(site, page)

      log, status = Open3.capture2e(
        ENV.fetch("PYTHON", "python"),
        File.join(ROOT, ".github/scripts/check_rendered_html.py"),
        "--site", File.dirname(site), "--baseurl", ""
      )
      unless status.success?
        failures << "#{rel} (current=#{current || 'none'}):\n#{log}"
      end

      # Behaviour, not just well-formedness. Exactly one card may claim to be
      # the current site, and it must be the one that was asked for.
      next unless name == "ecosystem"

      marked = body.scan(/ecosystem-card is-current/).size
      unless marked == (current ? 1 : 0)
        failures << "#{rel} (current=#{current || 'none'}): expected " \
                    "#{current ? 1 : 0} is-current card(s), found #{marked}"
      end
    end
  end
end

puts "checked #{currents.size * partials.size} rendered page(s)"

if failures.empty?
  puts "OK: all partials render and pass check_rendered_html.py"
else
  failures.each { |f| warn f }
  exit 1
end
