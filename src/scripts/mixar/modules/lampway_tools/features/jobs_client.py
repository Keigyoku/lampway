# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The client's door to the server's image slot (job queue ``image_gen``): POST the prompt and the reference image, poll the job,
download the result. No bpy here, so the pure part is testable; the server URL and the bearer come from the stored login, the
same as the MatGen client."""

import base64
import json
import time
import urllib.error
import urllib.request
import uuid


class ImageSlotError(RuntimeError):
    pass


def _server_url() -> str:
    from mixar.config.config import get_server_url
    return get_server_url().rstrip("/")


def _access_token() -> str:
    from mixar.modules.auth.core.auth import get_access_token
    return get_access_token()


def _request(method, path, body=None, timeout=120):
    token = _access_token()
    if not token:
        raise ImageSlotError("not signed in: log in to the Lampway server first")
    req = urllib.request.Request(_server_url() + path, method=method, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail") or ""
        except Exception:  # noqa: BLE001
            detail = ""
        raise ImageSlotError(detail or f"the server answered HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ImageSlotError(f"the server could not be reached: {exc}") from None


def _download(url, timeout=120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def record_ledger(row: dict) -> dict:
    """One experiment row into the server's ledger (POST /app/ledger: the server checks and appends it); returns the stored row."""
    return _request("POST", "/app/ledger", row)


def generate_image(prompt, reference_png, count=1, timeout=300, poll=1.0, extra_references=None):
    """``count`` images (PNG/JPEG bytes) from the image slot, conditioned on ``reference_png`` (bytes) when given; ``extra_references`` (bytes, in order)
    follow it, e.g. a material reference as the second image."""
    payload = {"prompt": prompt, "params": {"number_of_images": int(count)}}
    refs = [r for r in [reference_png, *(extra_references or [])] if r]
    if refs:
        payload["reference_images_b64"] = [base64.b64encode(r).decode("ascii") for r in refs]
    sub = _request("POST", "/api/v1/job-queue/jobs", {"service": "image_gen", "model": "default", "payload": payload,
                                                      "idempotency_key": str(uuid.uuid4())})
    data = sub.get("data") or {}
    job_id = data.get("job_id")
    deadline = time.time() + timeout
    while True:
        status = str(data.get("status") or "")
        if status == "DONE":
            break
        if status in ("FAILED", "CANCELLED", "DLQ"):
            raise ImageSlotError(f"the image job {status.lower()}: {data.get('error') or data.get('user_message') or 'no reason given'}")
        if time.time() > deadline:
            raise ImageSlotError(f"the image job did not finish in {timeout} s")
        time.sleep(poll)
        data = (_request("GET", f"/api/v1/job-queue/jobs/{job_id}").get("data")) or {}
    urls = [i["url"] if isinstance(i, dict) else i for i in ((data.get("result") or {}).get("images") or [])]
    if not urls:
        raise ImageSlotError("the image job finished with no image")
    return [_download(u) for u in urls]
