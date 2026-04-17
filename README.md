# makancrawler

`makancrawler` is an on-demand web crawler that takes an array of crawl settings and generates a local, markdown-based snapshot of the content it discovers.

## What it does

- **Run on demand**: you trigger a run when you want (not a continuously running service).
- **Crawl from configured URLs**: each crawl setting includes:
  - **`url`**: the starting URL to crawl
  - **`checkOtherSites`** (boolean): whether the crawler is allowed to follow links to other domains/sites found from that starting URL
- **Store results as markdown files**: all crawl output is written to your local folder as `.md` files.

## Output structure

- **Pages are saved as markdown files**: a crawled page becomes an `.md` file.
- **Deeper links become folders**: if a page contains additional links that are crawled “under” it, the crawler may create a folder for that page and place the linked pages’ `.md` files inside it (creating a nested structure that mirrors the link tree).

## Usage

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

1) Copy the example settings file:

```bash
cp crawl-settings.example.json crawl-settings.json
```

2) Edit `crawl-settings.json` and set your `settings` array:

- **`url`**: starting URL
- **`checkOtherSites`**: if `true`, the crawler may follow links to other domains found from the URL
- **Optional limits**: `maxDepth`, `maxPages`, `maxLinksPerPage`, `timeoutSeconds`

3) Run the crawler:

```bash
python -m crawler crawl --settings crawl-settings.json --out crawl-output
```

## Notes

- This repository stores crawl results **as files in your local folder**, so you can browse, diff, and version them like normal markdown content.
