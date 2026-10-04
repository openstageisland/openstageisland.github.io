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

Dir.mktmpdir("footer-render") do |dir|
  site = File.join(dir, "_site")
  FileUtils.mkdir_p(site)

  currents.each do |current|
    assigns = { "current" => current }
    partials.each do |name, rel|
      body = render(File.join(ROOT, rel), assigns)

      page = <<~HTML
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"><title>#{name}</title>
        <meta name="description" content="rendered footer partial">
        <meta http-equiv="Content-Security-Policy" content="default-src 'self'"></head>
        <body>
        <main>
        <h1>Fixture</h1>
        <h2>Section</h2>
        #{body}
        </main>
        </body>
        </html>
      HTML

      out = File.join(site, "#{name}-#{current || 'none'}", "index.html")
      FileUtils.mkdir_p(File.dirname(out))
      File.write(out, page)

      log, status = Open3.capture2e(
        RbConfig.ruby, File.join(ROOT, ".github/scripts/check_rendered_html.py"),
        "--site", site, "--baseurl", ""
      )
      # The gate scans every page under the site dir each run, so only look at
      # the lines naming the page this iteration just wrote.
      mine = log.lines.grep(/#{Regexp.escape("#{name}-#{current || 'none'}")}/)
      next if mine.empty? && status.success?

      failures << "#{rel} (current=#{current || 'none'}):\n#{mine.join}"
    end
  end

  puts "rendered #{currents.size * partials.size} page(s) into #{site}"
end

if failures.empty?
  puts "OK: all partials render and pass check_rendered_html.py"
else
  failures.each { |f| warn f }
  exit 1
end
