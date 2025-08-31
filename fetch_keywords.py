#!/usr/bin/env python3
"""
Fetch App Store keywords for one or more apps and locales using the
App Store Connect API.

- Accepts App Store IDs (e.g., id123456789 or 123456789), bundle IDs (e.g., com.example.app),
  or App Store Connect App IDs (resource IDs).
- For each requested locale (e.g., en-US), prints the app name and keywords.

Note: App Store keywords are only accessible for apps you have access to in
your App Store Connect account tied to the API key.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple, Union

import jwt  # PyJWT
import requests
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_der_private_key,
)
from cryptography.hazmat.backends import default_backend

ASC_API_BASE = "https://api.appstoreconnect.apple.com/v1"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"


class AppStoreConnectClient:
    """Lightweight ASC API client with JWT auth (ES256)."""

    def __init__(
        self,
        key_id: str,
        issuer_id: str,
        private_key_pem: Union[str, bytes],
        token_ttl_seconds: int = 1200,
        http_timeout_seconds: int = 30,
    ) -> None:
        if not key_id or not issuer_id or not private_key_pem:
            raise ValueError("Missing App Store Connect credentials")
        self.key_id = key_id.strip()
        self.issuer_id = issuer_id.strip()
        self.private_key_pem = private_key_pem
        self.token_ttl_seconds = min(max(token_ttl_seconds, 60), 1200)  # Apple max 20 min
        self.http_timeout_seconds = http_timeout_seconds
        self._cached_token: Optional[str] = None
        self._cached_token_exp: Optional[int] = None
        self._signing_key = self._load_signing_key(private_key_pem)

    @staticmethod
    def _load_signing_key(key_data: Union[str, bytes]):
        """Load an EC private key object suitable for ES256 signing.

        Accepts PEM text, PEM bytes, or DER bytes. If given a str that looks base64-encoded,
        attempts to base64-decode first.
        """
        if isinstance(key_data, str):
            text = key_data.strip()
            # Normalize escaped newlines
            if "\\n" in text and "-----BEGIN" in text:
                text = text.replace("\\n", "\n")
            # Load PEM if it looks like PEM
            if "-----BEGIN" in text and "-----END" in text:
                try:
                    return load_pem_private_key(text.encode("utf-8"), password=None, backend=default_backend())
                except Exception:
                    pass
            # Try base64 → DER
            try:
                raw = base64.b64decode(text)
            except Exception:
                raw = text.encode("utf-8", errors="ignore")
        else:
            raw = key_data

        # Try PEM then DER with raw bytes
        try:
            return load_pem_private_key(raw, password=None, backend=default_backend())
        except Exception:
            try:
                return load_der_private_key(raw, password=None, backend=default_backend())
            except Exception as e:
                raise SystemExit(f"Failed to parse private key: {e}")

    def _generate_token(self) -> str:
        now = int(dt.datetime.utcnow().timestamp())
        if self._cached_token and self._cached_token_exp and now + 30 < self._cached_token_exp:
            return self._cached_token
        headers = {"kid": self.key_id, "alg": "ES256", "typ": "JWT"}
        payload = {
            "iss": self.issuer_id,
            "iat": now,
            "exp": now + self.token_ttl_seconds,
            "aud": "appstoreconnect-v1",
        }
        token = jwt.encode(payload, self._signing_key, algorithm="ES256", headers=headers)
        # PyJWT may return str or bytes depending on version
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self._cached_token = token
        self._cached_token_exp = payload["exp"]
        return token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._generate_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "aso-keywords-fetcher/1.0",
        }

    def get(self, path: str, params: Optional[Dict[str, str]] = None) -> Dict:
        url = f"{ASC_API_BASE}{path}"
        # Some proxies strip Authorization on GET with params, so avoid mixing if debug suggests issues
        resp = requests.get(url, headers=self._headers(), params=params or {}, timeout=self.http_timeout_seconds)
        self._raise_for_status_with_detail(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status_with_detail(resp: requests.Response) -> None:
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            detail = ""
            try:
                data = resp.json()
                if isinstance(data, dict) and data.get("errors"):
                    detail = json.dumps(data.get("errors"), indent=2)
                else:
                    detail = json.dumps(data, indent=2)
            except Exception:
                detail = resp.text
            raise requests.HTTPError(f"HTTP {resp.status_code} error: {detail}") from e

    # --- App resolution ---
    def get_app_by_bundle_id(self, bundle_id: str) -> Optional[Dict]:
        data = self.get("/apps", params={"filter[bundleId]": bundle_id, "limit": "2"})
        items = data.get("data", [])
        return items[0] if items else None

    def get_app_by_connect_id(self, connect_app_id: str) -> Optional[Dict]:
        try:
            data = self.get(f"/apps/{connect_app_id}")
            return data.get("data")
        except requests.HTTPError as e:
            if "404" in str(e):
                return None
            raise

    def list_app_store_versions(self, app_id: str, platform: str = "IOS", state: Optional[str] = None) -> List[Dict]:
        params: Dict[str, str] = {"filter[platform]": platform, "limit": "200"}
        if state:
            params["filter[appStoreState]"] = state
        data = self.get(f"/apps/{app_id}/appStoreVersions", params=params)
        return data.get("data", [])

    def get_app_info_id(self, app_id: str) -> Optional[str]:
        data = self.get(f"/apps/{app_id}/appInfos", params={"limit": "1"})
        items = data.get("data", [])
        return items[0]["id"] if items else None

    def get_app_name_for_locale(self, app_id: str, locale: str) -> Optional[str]:
        app_info_id = self.get_app_info_id(app_id)
        if not app_info_id:
            return None
        data = self.get(
            f"/appInfos/{app_info_id}/appInfoLocalizations",
            params={"filter[locale]": locale, "limit": "1"},
        )
        items = data.get("data", [])
        if not items:
            return None
        return items[0].get("attributes", {}).get("name")

    def get_keywords_for_version_locale(self, app_store_version_id: str, locale: str) -> Optional[str]:
        data = self.get(
            f"/appStoreVersions/{app_store_version_id}/appStoreVersionLocalizations",
            params={"filter[locale]": locale, "limit": "1"},
        )
        items = data.get("data", [])
        if not items:
            return None
        return items[0].get("attributes", {}).get("keywords")


def is_bundle_id(value: str) -> bool:
    return "." in value and not value.lower().startswith("id") and not value.isdigit()


def normalize_itunes_id(value: str) -> Optional[str]:
    m = re.fullmatch(r"id?(\d+)", value.strip())
    return m.group(1) if m else None


def itunes_lookup_by_id(itunes_id: str, country: str = "us", timeout_seconds: int = 15) -> Optional[Dict]:
    try:
        resp = requests.get(
            ITUNES_LOOKUP_URL,
            params={"id": itunes_id, "country": country},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount", 0) > 0:
            return data["results"][0]
        return None
    except Exception:
        return None


def resolve_app(
    client: AppStoreConnectClient,
    app_identifier: str,
    country: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve an input identifier to (connect_app_id, bundle_id, itunes_id, display_name).
    - Accepts: App Store numeric ID (with or without id prefix), bundle ID, or connect app id.
    """
    # If it's an iTunes App Store ID, look up bundle id and name via iTunes API
    itunes_id = normalize_itunes_id(app_identifier)
    if itunes_id:
        itunes = itunes_lookup_by_id(itunes_id, country=country)
        display_name = (itunes or {}).get("trackName")
        bundle_id = (itunes or {}).get("bundleId")
        connect_app_id = None
        if bundle_id:
            app = client.get_app_by_bundle_id(bundle_id)
            connect_app_id = app["id"] if app else None
        return connect_app_id, bundle_id, itunes_id, display_name

    # If it looks like a bundle id, resolve to connect app id
    if is_bundle_id(app_identifier):
        app = client.get_app_by_bundle_id(app_identifier)
        if app:
            return app["id"], app.get("attributes", {}).get("bundleId"), None, None
        return None, app_identifier, None, None

    # Otherwise, assume it's a Connect app id
    app = client.get_app_by_connect_id(app_identifier)
    if app:
        return app["id"], app.get("attributes", {}).get("bundleId"), None, None

    return None, None, None, None


def choose_app_store_version(
    client: AppStoreConnectClient,
    app_id: str,
    platform: str,
    prefer_live: bool = True,
) -> Optional[Dict]:
    """Pick an App Store Version. Prefer READY_FOR_SALE if available."""
    versions: List[Dict] = []
    if prefer_live:
        versions = client.list_app_store_versions(app_id, platform=platform, state="READY_FOR_SALE")
    if not versions:
        versions = client.list_app_store_versions(app_id, platform=platform)
    if not versions:
        return None
    # If multiple, pick most recent by createdDate if present; otherwise first.
    def created_key(v: Dict) -> str:
        return v.get("attributes", {}).get("createdDate", "")

    versions_sorted = sorted(versions, key=created_key, reverse=True)
    return versions_sorted[0]


def _coerce_pem(value: Union[str, bytes]) -> Union[str, bytes]:
    """Attempt to coerce various input encodings to a usable PEM/DER key.

    Handles:
    - Raw PEM string
    - PEM string with literal \n sequences
    - Base64-encoded PEM (text)
    - Base64-encoded DER (binary)
    """
    if isinstance(value, bytes):
        # Could already be DER or PEM bytes
        return value

    text = value.strip()

    # Replace literal \n with real newlines if present
    if "\\n" in text and "-----BEGIN" in text:
        text = text.replace("\\n", "\n")

    # If it already looks like PEM, return as-is
    if "-----BEGIN" in text and "-----END" in text:
        return text

    # Try Base64 decode → UTF-8 text PEM
    try:
        decoded_bytes = base64.b64decode(text)
        try:
            decoded_text = decoded_bytes.decode("utf-8")
            if "-----BEGIN" in decoded_text:
                return decoded_text
        except UnicodeDecodeError:
            # Not UTF-8 text; could be DER bytes
            if decoded_bytes:
                return decoded_bytes
    except Exception:
        pass

    # As a last resort, return the original text
    return text


def load_private_key_from_args(args: argparse.Namespace) -> Union[str, bytes]:
    # Priority: --key-file > ASC_PRIVATE_KEY_PATH env; then --key > ASC_PRIVATE_KEY env
    if args.key_file:
        with open(args.key_file, "r", encoding="utf-8") as f:
            return _coerce_pem(f.read())
    env_path = os.getenv("ASC_PRIVATE_KEY_PATH")
    if env_path and os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            return _coerce_pem(f.read())
    if args.key:
        return _coerce_pem(args.key)
    env_key = os.getenv("ASC_PRIVATE_KEY")
    if env_key:
        return _coerce_pem(env_key)
    raise SystemExit("Missing private key: provide --key-file or --key, or set ASC_PRIVATE_KEY_PATH/ASC_PRIVATE_KEY")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch App Store keywords for apps and locales using App Store Connect API.",
    )
    parser.add_argument(
        "apps",
        nargs="*",
        help="App identifiers: App Store IDs (id12345 or 12345), bundle IDs (com.example.app), or Connect App IDs",
    )
    parser.add_argument(
        "-l",
        "--locales",
        nargs="+",
        default=["en-US"],
        help="Locales to fetch (e.g., en-US de-DE fr-FR). Default: en-US",
    )
    parser.add_argument(
        "--platform",
        choices=["IOS", "MAC_OS", "TV_OS"],
        default="IOS",
        help="Target platform for the App Store version. Default: IOS",
    )
    parser.add_argument(
        "--country",
        default=os.getenv("ASC_COUNTRY", "us"),
        help="Country code for iTunes lookup when given App Store IDs. Default: us",
    )
    parser.add_argument(
        "--prefer-live",
        action="store_true",
        help="Prefer the live (READY_FOR_SALE) App Store version when selecting keywords",
    )
    # Credentials
    parser.add_argument("--key-id", default=os.getenv("ASC_KEY_ID"), help="App Store Connect API Key ID")
    parser.add_argument("--issuer-id", default=os.getenv("ASC_ISSUER_ID"), help="App Store Connect API Issuer ID")
    parser.add_argument("--key-file", help="Path to the App Store Connect API .p8 private key file")
    parser.add_argument("--key", help="Private key contents (PEM). Alternatively set ASC_PRIVATE_KEY env var")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (also set ASC_DEBUG=1)",
    )
    parser.add_argument(
        "--print-token",
        action="store_true",
        help="Print a freshly generated JWT and exit (for troubleshooting)",
    )
    parser.add_argument(
        "--auth-check",
        action="store_true",
        help="Perform a simple authenticated request and report status, then exit",
    )
    parser.add_argument(
        "--token-ttl",
        type=int,
        default=int(os.getenv("ASC_TOKEN_TTL", "1200")),
        help="JWT token lifetime in seconds (max 1200). Default: 1200",
    )
    parser.add_argument(
        "--http-timeout",
        type=int,
        default=int(os.getenv("ASC_HTTP_TIMEOUT", "30")),
        help="HTTP timeout in seconds. Default: 30",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Allow ASC_DEBUG env to enable debug mode
    if not getattr(args, "debug", False):
        env_debug = os.getenv("ASC_DEBUG", "").lower()
        args.debug = env_debug in {"1", "true", "yes", "on"}

    # Trim credentials to avoid whitespace issues
    args.key_id = (args.key_id or "").strip()
    args.issuer_id = (args.issuer_id or "").strip()

    if not args.key_id or not args.issuer_id:
        print("Error: Missing credentials. Provide --key-id and --issuer-id or set ASC_KEY_ID/ASC_ISSUER_ID.", file=sys.stderr)
        return 2

    private_key_pem = load_private_key_from_args(args)

    client = AppStoreConnectClient(
        key_id=args.key_id,
        issuer_id=args.issuer_id,
        private_key_pem=private_key_pem,
        token_ttl_seconds=args.token_ttl,
        http_timeout_seconds=args.http_timeout,
    )

    # If debug, print token meta (without private key) and clock details
    if args.debug:
        try:
            token = client._generate_token()
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})
            now = int(dt.datetime.utcnow().timestamp())
            skew = payload.get("exp", 0) - now
            print(
                json.dumps(
                    {
                        "tokenHeader": header,
                        "tokenPayload": payload,
                        "nowUtc": now,
                        "secondsUntilExp": skew,
                    },
                    indent=2,
                )
            )
        except Exception as e:
            print(f"Debug: failed to inspect token: {e}", file=sys.stderr)

    # Utility modes
    if args.print_token:
        print(client._generate_token())
        return 0

    if args.auth_check:
        try:
            # Minimal authenticated request; doesn't require admin privileges
            _ = client.get("/apps", params={"limit": "1"})
            print("Auth OK: able to call App Store Connect API")
            return 0
        except requests.HTTPError as e:
            print(f"Auth FAILED: {e}", file=sys.stderr)
            return 1

    if not args.apps:
        print("Error: no apps provided. Pass one or more identifiers, or use --auth-check/--print-token.", file=sys.stderr)
        return 2

    any_errors = False

    for app_input in args.apps:
        try:
            connect_app_id, bundle_id, itunes_id, display_name = resolve_app(client, app_input, country=args.country)
        except requests.HTTPError as e:
            print(f"Failed to resolve app '{app_input}': {e}", file=sys.stderr)
            any_errors = True
            continue

        if not connect_app_id and not bundle_id and not itunes_id:
            print(f"Could not find app for '{app_input}'. Ensure you own the app or provided a valid identifier.", file=sys.stderr)
            any_errors = True
            continue

        # Select version
        version = None
        if connect_app_id:
            try:
                version = choose_app_store_version(client, connect_app_id, platform=args.platform, prefer_live=args.prefer_live)
            except requests.HTTPError as e:
                print(f"Failed to list versions for app '{app_input}': {e}", file=sys.stderr)
                any_errors = True
                continue
        if not version:
            print(f"No App Store versions found for '{app_input}'.", file=sys.stderr)
            any_errors = True
            continue
        version_id = version["id"]

        for locale in args.locales:
            # Name resolution priority: ASC appInfo name (locale) -> iTunes trackName -> bundleId
            name = None
            if connect_app_id:
                try:
                    name = client.get_app_name_for_locale(connect_app_id, locale)
                except requests.HTTPError:
                    name = None
            if not name:
                name = display_name or bundle_id or "Unknown App"

            # Keywords
            keywords = None
            try:
                keywords = client.get_keywords_for_version_locale(version_id, locale)
            except requests.HTTPError as e:
                print(f"Failed to fetch keywords for '{app_input}' [{locale}]: {e}", file=sys.stderr)

            # Output
            printed_id = f"id{itunes_id}" if itunes_id else (bundle_id or connect_app_id or "?")
            print(f"Name: {name} {printed_id} [{locale}]")
            print("=" * 40)
            if keywords and keywords.strip():
                print(keywords.strip())
            else:
                print("(no keywords)")
            # Separator between locales for readability
            # print()

    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
