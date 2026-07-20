import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add common layer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common-layer"))

from common.pytest import download_source_archive, get_tests


class TestPrivateGameSource:
    def test_download_source_archive_uses_s3_client(self):
        mock_client = Mock()

        with patch("common.pytest.boto3.client", return_value=mock_client):
            download_source_archive(
                "s3://private-bucket/game-sources/k8s-game-rule.zip",
                "/tmp/k8s-game-rule.zip",
            )

        mock_client.download_file.assert_called_once_with(
            "private-bucket",
            "game-sources/k8s-game-rule.zip",
            "/tmp/k8s-game-rule.zip",
        )

    def test_get_tests_extracts_private_s3_archive(self, tmp_path):
        game = f"game-{uuid.uuid4().hex}"
        archive_root = f"source-{uuid.uuid4().hex}"
        source = "s3://private-bucket/game-sources/k8s-game-rule.zip"
        archive_path = tmp_path / "source.zip"
        target_root = tmp_path / game

        payload_dir = tmp_path / archive_root / "tests" / "game01"
        payload_dir.mkdir(parents=True)
        (payload_dir / "marker.txt").write_text("private source", encoding="utf-8")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in (tmp_path / archive_root).rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(tmp_path)))

        def fake_download_file(bucket, key, destination):
            shutil.copyfile(archive_path, destination)

        mock_client = Mock()
        mock_client.download_file.side_effect = fake_download_file

        cache_file = Path(f"/tmp/{game}_source.txt")
        zip_file = Path(f"/tmp/{game}.zip")

        try:
            with patch("common.pytest.get_game_source", return_value=source), \
                 patch("common.pytest.boto3.client", return_value=mock_client), \
                 patch("common.pytest.get_root_path", return_value=str(target_root)):
                get_tests(game)

            assert (target_root / "tests" / "game01" / "marker.txt").read_text(
                encoding="utf-8"
            ) == "private source"
        finally:
            if cache_file.exists():
                cache_file.unlink()
            if zip_file.exists():
                zip_file.unlink()
