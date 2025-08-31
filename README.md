# aso-keywords

Fetch Apple App Store keywords for one or more apps and locales using ONLY public iTunes APIs (no App Store Connect required).

This script prints the app name and a heuristically constructed comma‑separated keywords string (≤100 chars) for each requested locale. It supports the following identifiers for apps:

- App Store ID: `id123456789` or `123456789`
- Bundle ID: `com.example.myapp`
  
Note: Since this uses public metadata (title, genres, description), the resulting keywords are a best‑effort heuristic, not the private App Store Connect keywords field.

Example output:

```
Name: My Great App id123456789 [en-US]
========================================
garageband,ringtone maker,garage,ringtones,garage rigtones,garage band,ringtone,zedge
```

## Requirements

- Python 3.9+

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

- `DEFAULT_COUNTRY` (optional): Default storefront country for lookups when a locale is unknown (default: `us`).
- `ASO_CHAR_LIMIT` (optional): Max characters for the output keywords string (default: `100`).

## Usage

Show help:

```bash
python3 fetch_keywords.py -h
```

Basic:

```bash
python3 fetch_keywords.py id123456789 -l en-US
```

Multiple locales:

```bash
python3 fetch_keywords.py id123456789 -l en-US de-DE fr-FR ja-JP
```

Bundle ID input:

```bash
python3 fetch_keywords.py com.example.myapp -l en-US
```

Connect App ID is not supported (public APIs only). Use App Store ID or Bundle ID.

 

Resolve with a specific default country (for storefront mapping):

```bash
python3 fetch_keywords.py id123456789 -l en-US --country de
```

### Output format

For each requested locale, the script prints a colored panel (when supported) or plain text:

```
Name: <App Name> <identifier> [<locale>]
========================================
<comma-separated keywords or (no keywords)>
```

The `<identifier>` is `id<itunesId>` if provided, otherwise the Bundle ID or the App Store Connect App ID.

## Notes and limitations

- This tool does not use App Store Connect and cannot access private keywords fields.
- Keywords are derived heuristically from public metadata (title, genres, description) and packed to ≤100 chars.
- Locales must be valid (e.g., `en-US`, `de-DE`, `fr-FR`, `ja-JP`). The tool maps locale→storefront country when possible.
- Network errors are reported to stderr; the script exits non‑zero if any app lookup fails.

## Exit codes

- `0` → success
- `1` → ran but one or more lookups failed
- `2` → invalid/missing credentials or arguments

## Security

- No private credentials are required. This tool uses only public endpoints.

## License

MIT — see `LICENSE`.
