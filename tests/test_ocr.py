"""Tests for POST /materials/ocr (mocked — no real vision calls)."""

import agents.material_ocr as ocr
import main


def _post(client, b64="aGVsbG8=", media="image/jpeg"):
    return client.post("/materials/ocr", json={"image_base64": b64, "media_type": media})


def test_ocr_unavailable_without_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = _post(client)
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_ocr_happy_path_mocked(client, monkeypatch):
    captured = {}

    def fake_extract(image_base64, media_type):
        captured["b64"] = image_base64
        captured["media"] = media_type
        return "Photosynthesis converts light energy into chemical energy."

    monkeypatch.setattr(ocr, "extract_text_from_image", fake_extract)
    r = _post(client, b64="Zm9v", media="image/png")
    assert r.status_code == 200
    assert r.json()["text"].startswith("Photosynthesis")
    assert captured == {"b64": "Zm9v", "media": "image/png"}


def test_ocr_rejects_bad_media_type(client):
    r = _post(client, media="application/pdf")
    assert r.status_code == 400
    assert "media_type" in r.json()["detail"]


def test_ocr_rejects_oversized_image(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_OCR_B64_CHARS", 10)
    r = _post(client, b64="A" * 20)
    assert r.status_code == 413


def test_ocr_is_available_reflects_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ocr.is_available() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert ocr.is_available() is True
