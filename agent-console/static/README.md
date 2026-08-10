# Console static assets

Flask serves this folder at `/static/`.

## `sensedia-logo.svg`

The header of `templates/index.html` loads the official Sensedia logo from
`/static/sensedia-logo.svg`. It is the official horizontal color SVG supplied
for this project:

https://cdn.prod.website-files.com/6474ba281ebb6ae9242441af/647524df5e03a0547c4b5401_Sensedia_horizontal_color-01.svg

The stylesheet constrains it by height with `width: auto`, so the original
proportions are preserved. A neutral fallback slot remains in the header for
an unavailable asset; the console never draws an approximation of the mark.
