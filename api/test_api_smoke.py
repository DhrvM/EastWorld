"""API smoke tests for local hackathon demo flow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.server import app


client = TestClient(app)


def _create_simulation() -> str:
    res = client.post(
        "/api/simulations",
        json={
            "environment": {
                "objective": "Discuss launch risks and priorities for the uploaded artifacts.",
            },
            "mock_mode": True,
            "bootstrap_synths": False,
            "synths": [
                {"synth_id": "Ava", "persona_prompt": "You are Ava, a practical PM."},
                {"synth_id": "Noah", "persona_prompt": "You are Noah, a detail-oriented engineer."},
            ],
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["env_id"]


def _upload_file(env_id: str, filename: str, data: bytes, artifact_type: str = "document") -> None:
    res = client.post(
        f"/api/simulations/{env_id}/artifacts/upload",
        data={"artifact_type": artifact_type, "title": filename},
        files={"file": (filename, data)},
    )
    assert res.status_code == 200, res.text


def _sample_pdf_bytes() -> bytes | None:
    try:
        from pypdf import PdfWriter
    except Exception:
        return None

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class ApiSmokeTest(unittest.TestCase):
    def test_api_end_to_end_smoke(self) -> None:
        env_id = _create_simulation()

        _upload_file(env_id, "brief.txt", b"Market size is growing 35% YoY.")
        _upload_file(env_id, "notes.md", b"# Notes\nNeed stronger onboarding and pricing clarity.")
        pdf_bytes = _sample_pdf_bytes()
        expected_artifacts = 3 if pdf_bytes is not None else 2
        if pdf_bytes is not None:
            _upload_file(env_id, "spec.pdf", pdf_bytes)
        else:
            # Ensure endpoint fails gracefully when PDF dependency is missing.
            res = client.post(
                f"/api/simulations/{env_id}/artifacts/upload",
                data={"artifact_type": "document", "title": "spec.pdf"},
                files={"file": ("spec.pdf", b"%PDF-1.7")},
            )
            self.assertEqual(res.status_code, 400, res.text)

        round_res = client.post(f"/api/simulations/{env_id}/rounds/one")
        self.assertEqual(round_res.status_code, 200, round_res.text)
        self.assertIn("stats", round_res.json())

        chat_res = client.post(
            f"/api/simulations/{env_id}/chat/Ava",
            json={"text": "What is the biggest launch risk?"},
        )
        self.assertEqual(chat_res.status_code, 200, chat_res.text)
        self.assertIn("message", chat_res.json())

        god_res = client.post(
            f"/api/simulations/{env_id}/god",
            json={"question": "Summarize top 3 action items with groundedness score."},
        )
        self.assertEqual(god_res.status_code, 200, god_res.text)
        self.assertIn("answer", god_res.json())

        stats_res = client.get(f"/api/simulations/{env_id}/stats")
        self.assertEqual(stats_res.status_code, 200, stats_res.text)
        self.assertGreaterEqual(stats_res.json()["stats"]["artifacts_ingested"], expected_artifacts)

        trace_res = client.get(f"/api/simulations/{env_id}/traces?limit=20")
        self.assertEqual(trace_res.status_code, 200, trace_res.text)
        self.assertIsInstance(trace_res.json()["traces"], list)


if __name__ == "__main__":
    unittest.main()
