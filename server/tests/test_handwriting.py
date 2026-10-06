"""handwriting_recognize (specs/mixar_docs/voice_handwriting.md): POST /api/v1/handwriting/recognize turns the Client's ink image into composer text. Proven code
first: a blank image is answered with empty text and NO model call; the reader model is a slot (an OpenRouter vision model on the spend ledger by default)."""

import io

import pytest
from PIL import Image, ImageDraw
from starlette.testclient import TestClient

from lampway_server import handwriting as HW
from lampway_server.app import create_app

from .fake_client import FakeMixarClient


def png(ink=True, size=(400, 160)):
    im = Image.new("RGB", size, (255, 255, 255))
    if ink:
        d = ImageDraw.Draw(im)
        d.line([(40, 80), (120, 40), (200, 120), (320, 60)], fill=(20, 20, 20), width=6)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


class Reader:
    def __init__(self, text="hello"):
        self.calls, self.text = [], text

    async def read(self, image_png, hint):
        self.calls.append({"bytes": len(image_png), "hint": hint})
        return self.text, 0.9


@pytest.fixture
def app_client(settings, provider, monkeypatch, tmp_path):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "root"))
    reader = Reader()
    app = create_app(settings, provider=provider, job_backends={}, handwriting_reader=reader)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, reader, http


def post(fake, data, hint=None):
    files = {"image": ("ink.png", data, "image/png")}
    return fake.post("/api/v1/handwriting/recognize", files=files, data={"hint": hint} if hint is not None else {})


def test_a_blank_image_is_empty_text_without_a_model_call(app_client):
    fake, reader, _ = app_client
    r = post(fake, png(ink=False))
    assert r.status_code == 200 and r.json()["data"] == {"text": "", "confidence": 0.0} and reader.calls == []


def test_ink_goes_to_the_reader_and_the_text_comes_back(app_client):
    fake, reader, _ = app_client
    r = post(fake, png(), hint="make the ramp " + "x" * 600)
    assert r.status_code == 200 and r.json()["data"]["text"] == "hello" and r.json()["data"]["confidence"] > 0, r.text
    assert len(reader.calls) == 1 and len(reader.calls[0]["hint"]) == 500 and reader.calls[0]["hint"].endswith("x"), "the hint is the composer's TAIL, 500 chars"


def test_too_large_not_an_image_and_no_bearer(app_client):
    fake, reader, http = app_client
    assert post(fake, b"\x89PNG" + b"0" * (9 * 1024 * 1024)).status_code == 413
    assert post(fake, b"not an image at all").status_code == 422
    assert http.post("/api/v1/handwriting/recognize", files={"image": ("i.png", png(), "image/png")}).status_code == 401
    assert reader.calls == []


def test_no_reader_configured_is_a_503_naming_the_fix(settings, provider, monkeypatch, tmp_path):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "root"))
    app = create_app(settings, provider=provider, job_backends={}, handwriting_reader=False)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        r = post(fake, png())
        assert r.status_code == 503 and "no vision model configured" in r.text


def test_the_ink_check_crops_to_the_strokes():
    has, crop = HW.ink(png())
    assert has is True and Image.open(io.BytesIO(crop)).size[0] < 400
    assert HW.ink(png(ink=False))[0] is False
