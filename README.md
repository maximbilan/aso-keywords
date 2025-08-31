# aso-keywords

Fetch Apple App Store keywords for one or more apps and locales using the App Store Connect API.

This script prints the app name and the comma‑separated keywords for each requested locale. It supports the following identifiers for apps:

- App Store ID: `id123456789` or `123456789`
- Bundle ID: `com.example.myapp`
- App Store Connect App ID (resource id)

Example output:

```
Name: My Great App id123456789 [en-US]
========================================
garageband,ringtone maker,garage,ringtones,garage rigtones,garage band,ringtone,zedge
```

## Requirements

- Python 3.9+
- App Store Connect API key (ES256 `.p8` private key), Key ID, and Issuer ID

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## App Store Connect credentials

You need an API key that has access to the apps whose keywords you want to read.

1. Sign in to App Store Connect.
2. Go to Users and Access → Keys → App Store Connect API.
3. Note the Issuer ID, create a new key, and download the `.p8` file. Note the Key ID.
4. Keep the `.p8` secure and never commit it to source control.

You can provide credentials via flags or environment variables:

- `ASC_KEY_ID` → App Store Connect Key ID
- `ASC_ISSUER_ID` → App Store Connect Issuer ID
- One of:
  - `ASC_PRIVATE_KEY_PATH` → path to the `.p8` file, or
  - `ASC_PRIVATE_KEY` → the PEM contents (supports Base64‑encoded value as well)

Optional environment variables:

- `ASC_COUNTRY` → iTunes lookup country when resolving App Store IDs (default: `us`)
- `ASC_TOKEN_TTL` → JWT lifetime in seconds (max 1200; default: 1200)
- `ASC_HTTP_TIMEOUT` → HTTP timeout in seconds (default: 30)

## Usage

Show help:

```bash
python3 fetch_keywords.py -h
```

Basic (using environment variables for credentials):

```bash
export ASC_KEY_ID=ABC123XYZ
export ASC_ISSUER_ID=00000000-1111-2222-3333-444444444444
export ASC_PRIVATE_KEY_PATH="$HOME/Keys/AuthKey_ABC123XYZ.p8"

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

Connect App ID input:

```bash
python3 fetch_keywords.py 12345678-90ab-cdef-1234-567890abcdef -l en-US
```

Specify platform and prefer the live version:

```bash
python3 fetch_keywords.py id123456789 -l en-US --platform IOS --prefer-live
```

Resolve App Store IDs with a specific iTunes country (for name/bundle lookup):

```bash
python3 fetch_keywords.py id123456789 -l en-US --country de
```

### Output format

For each requested locale, the script prints:

```
Name: <App Name> <identifier> [<locale>]
========================================
<comma-separated keywords or (no keywords)>
```

The `<identifier>` is `id<itunesId>` if provided, otherwise the Bundle ID or the App Store Connect App ID.

## Notes and limitations

- Keywords are only available for apps you can access with the provided API key (your App Store Connect team).
- If multiple App Store versions exist, `--prefer-live` selects a READY_FOR_SALE version when available, otherwise the most recent version is used.
- Locales must be valid App Store locales (e.g., `en-US`, `de-DE`, `fr-FR`, `ja-JP`).
- Network errors and permission issues are reported to stderr; the script exits non‑zero if any app fails.

## Exit codes

- `0` → success
- `1` → ran but one or more lookups failed
- `2` → invalid/missing credentials or arguments

## Security

- Do not commit your `.p8` file or secret contents.
- Prefer environment variables or a secret manager to pass credentials.

## License

MIT — see `LICENSE`.
