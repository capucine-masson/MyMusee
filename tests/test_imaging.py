import io

import pytest
from PIL import Image

from app import config
from app.i18n import AppError
from app.imaging import validate_upload


def _image_bytes(fmt: str = "PNG", size=(32, 24), mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, "red").save(buf, format=fmt)
    return buf.getvalue()


def _error_key(raw: bytes, content_type: str | None) -> str:
    with pytest.raises(AppError) as exc:
        validate_upload(raw, content_type, "en")
    return exc.value.key


def test_valid_png_is_returned_as_rgb():
    img = validate_upload(_image_bytes("PNG"), "image/png", "en")
    assert img.mode == "RGB" and img.size == (32, 24)


def test_transparent_png_is_flattened_on_white():
    raw = _image_bytes("PNG", mode="RGBA")
    img = validate_upload(raw, "image/png", "en")
    assert img.mode == "RGB"


def test_empty_file_is_rejected():
    assert _error_key(b"", "image/png") == "empty_file"


def test_oversized_file_is_rejected():
    assert _error_key(b"0" * (config.MAX_UPLOAD_BYTES + 1), "image/png") == "too_large"


def test_declared_type_must_be_allowed():
    assert _error_key(_image_bytes("PNG"), "application/pdf") == "bad_type"
    assert _error_key(_image_bytes("PNG"), None) == "bad_type"


def test_real_content_is_checked_not_just_the_declared_type():
    assert _error_key(b"<script>alert(1)</script>", "image/png") == "not_an_image"


def test_real_format_must_be_allowed_even_if_declared_type_is():
    assert _error_key(_image_bytes("GIF"), "image/png") == "bad_type"


def test_truncated_image_is_rejected():
    raw = _image_bytes("PNG", size=(200, 200))
    assert _error_key(raw[: len(raw) // 2], "image/png") == "not_an_image"
