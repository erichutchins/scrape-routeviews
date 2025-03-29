# scrape-routeviews

[![Scrape](https://github.com/erichutchins/scrape-routeviews/actions/workflows/scrape.yml/badge.svg?branch=main)](https://github.com/erichutchins/scrape-routeviews/actions/workflows/scrape.yml)

---

Git-scraping approach to converting [routeviews.org](https://routeviews.org/) rib files into asn:prefixes json dictionaries

---

## Usage

#### ASN to prefixes

The `routeviews_asn_prefixes.json` file contains a dictionary of ASN (string) to advertised network cidr ranges. This file is pretty-printed with sorted prefixes to enable diff'ing with the regular scrapes. `routeviews_asn_prefixes.json.zstd` is the same data but zstandard compressed.

```bash
# advertised prefixes for AS1234
❯ jq -c '."1234"' routeviews_asn_prefixes.json
["132.171.0.0/16","132.171.0.0/17","132.171.128.0/17","137.96.0.0/16","193.110.32.0/21"]
```

#### Regex Patterns for Networks

For quick-and-dirty filtering of logs for all traffic for a given AS, `routeviews_asn_grex.json.zstd` takes each list of advertised prefixes and creates a regex pattern to match IPs in the prefixes using [grex](https://github.com/pemistahl/grex). (NB: it does not validate IP addresses, merely matches on the prefixes)

```bash
❯ zstdcat routeviews_asn_grex.json.zstd | jq -r '."1234"'
^1(?:3(?:2\.171\.(?:2(?:5[0-5]|[6-9])|(?:1[0-9]|2[0-4]|[3-9])[0-9]|0)|7\.96)\.|32\.171\.(?:(?:25?\.|(?:1[0-9]|2[0-4]|[3-9])\.|1\.))?|93\.110\.3[2-9]\.)
```

## Thanks

- Inspired by @simonw's [Building and deploying a custom site using GitHub Actions and GitHub Pages](https://til.simonwillison.net/github-actions/github-pages)
- And @9b's [https://github.com/9b/netinfo](https://github.com/9b/netinfo)
