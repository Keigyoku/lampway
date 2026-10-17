<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Enterprise network configuration

Lampway's client talks to its own backend at `http://127.0.0.1:8787` by default.
`LAMPWAY_BACKEND_URL` overrides that address. The configured backend also supplies
the browser SSO frontend; its callback listens on loopback port `51731`.
The public project site is `lampway.dev`. These identities come from
[`brand.py`](../src/scripts/mixar/config/brand.py) and
[`auth/utils/constants.py`](../src/scripts/mixar/modules/auth/utils/constants.py).
The fork does not use the upstream project's hosted services.

Network configuration does not authorize external traffic. Provider egress is
off until the user enables it and remains subject to the server's egress gate.
Sandbox asset downloads accept HTTP/HTTPS and the configured asset hosts;
the default hosts are `127.0.0.1` and `localhost`. An external asset URL is refused
before transfer. See [the egress gate](../server/lampway_server/egress.py) and the
[root contract](../AGENTS.md).

## Proxy and loopback

The shared [network layer](../src/scripts/mixar/modules/common/network/__init__.py)
runs before bootstrap modules. Proxy resolution uses the first available value:

1. `LAMPWAY_PROXY_URL`.
2. `network.proxy_url` in the per-user `mixar.json` configuration overlay.
3. Existing `HTTPS_PROXY` or `HTTP_PROXY` variables, including lowercase forms.
4. The operating system's static proxy reported by `urllib.request.getproxies()`.

Explicit configuration is exported to the standard proxy variables so requests,
httpx, urllib and websocket-client agree. HTTP and HTTPS proxies are supported;
SOCKS is rejected because its client dependencies are not bundled. PAC/WPAD
automatic proxy discovery is unsupported; supply a static proxy URL.

`LAMPWAY_NO_PROXY`, `network.no_proxy`, and existing `NO_PROXY` entries are merged.
`localhost`, `127.0.0.1`, and `::1` are always added, including for SSO callbacks
and local model relays. Proxy configuration cannot route these through a proxy.
The implementation is [core/proxy.py](../src/scripts/mixar/modules/common/network/core/proxy.py).
The deprecated `MIXAR_*` spellings remain a one-release compatibility fallback;
use the `LAMPWAY_*` names for new configurations.

## Certificate trust

The root set is resolved in this order:

1. `LAMPWAY_CA_BUNDLE`, then `network.ca_bundle`, then existing
   `REQUESTS_CA_BUNDLE` or `SSL_CERT_FILE` overrides. A custom bundle replaces
   the default roots and is exported to `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`,
   and `WEBSOCKET_CLIENT_CA_BUNDLE`. The launcher's bundled interpreter CA path
   is treated as a default rather than an operator override.
2. The operating system trust store through `truststore`.
3. The bundled certifi roots when truststore is unavailable or Linux has no
   system CA bundle.

`LAMPWAY_EXTRA_CA_CERTS` supplies files or folders separated by `os.pathsep`;
`network.extra_ca_certs` accepts a string or list. Additional certificates are
additive in every trust mode. PEM and DER certificates with `.pem`, `.crt`,
`.cer`, or `.der` extensions are also read from `<user config>/lampway/certs`
and the platform's Lampway machine certificate folder. Missing bundles and
invalid certificates produce visible errors; they do not disable verification.
See [core/trust.py](../src/scripts/mixar/modules/common/network/core/trust.py).

## Diagnosing a failure

`network_diagnostics()` reports the effective trust mode, certificate errors,
proxy source, and proxy errors. Transport exceptions retain their original
cause and are classified for authentication, SSO and BYOK settings.
Support codes include `NET-TLS`, `NET-TLS2`, `NET-PROXY`, `NET-DNS`,
`NET-TIMEOUT`, `NET-REFUSED`, `NET-RESET`, `NET-UNREACH`, and `NET-UNKNOWN`.
Keep certificate verification enabled and correct the reported trust or proxy
configuration. The code map is in
[constants.py](../src/scripts/mixar/modules/common/network/constants.py).

These contracts are covered offline by `tests/network/` and
`tests/test_terrain_asset_prefetch.py`; those tests use fake transports and
do not establish connectivity to an enterprise deployment.
