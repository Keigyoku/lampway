"""Uploads are identified by their bytes, never by a name or the kind the caller claims (specs/mrmak/BUILD_ORDER_ADDENDUM section 2, attachment handling)."""
import pytest

from lampway_server.videojobs import UploadStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16


@pytest.fixture
def store(tmp_path):
    return UploadStore(tmp_path / "up", probe=lambda p: {"duration": 1.0, "width": 8, "height": 8})


@pytest.mark.parametrize("data,mime", [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"), (GIF, "image/gif")])
def test_an_image_is_recognised_by_its_magic_bytes(store, data, mime):
    out = store.put("image", data, "whatever.txt")                      # the file name is irrelevant
    assert out["media_type"] == mime


@pytest.mark.parametrize("data,mime", [(MP4, "video/mp4"), (WEBM, "video/webm")])
def test_a_video_is_recognised_by_its_container(store, data, mime):
    assert store.put("video", data, "clip.png")["media_type"] == mime


def test_the_claimed_kind_must_match_the_bytes(store):
    with pytest.raises(ValueError, match="not an image"):
        store.put("image", b"<html>not an image</html>", "x.png")
    with pytest.raises(ValueError, match="not an image"):
        store.put("image", MP4, "x.png")                                 # a video named .png is not an image
    with pytest.raises(ValueError, match="not a video"):
        store.put("video", PNG, "x.mp4")
    with pytest.raises(ValueError, match="not a video"):
        store.put("video", b"plain text", "x.mp4")
