<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Security Policy

## Reporting A Vulnerability

Report security issues privately, in this order of preference:

1. GitHub private vulnerability reporting: <https://github.com/Keigyoku/lampway/security/advisories/new>
2. By email to `security@lampway.dev` once the project announces that mailbox is live. **Placeholder: the owner has not named a contact yet; until this line is replaced, use the first route.**

Do not open a public issue for vulnerabilities, secrets, credential leaks, exploit details, or private user data.

Include a concise description, the affected version or commit, safe reproduction steps, and the impact.

Do not include real account passwords, API keys, tokens, private scene data, or third-party secrets in reports.

## Scope

In scope: the Lampway client and server code in this repository, its build and packaging scripts, and how it handles tokens, local credentials, user files and network requests.

Out of scope: third-party services Lampway can be pointed at (their own vulnerabilities are theirs to fix) and the upstream projects it is built on, unless the flaw is in code this repository changed.

## Supported Versions

The most recent tagged release, and `main`, are the supported security review targets.
