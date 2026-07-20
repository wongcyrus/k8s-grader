"""Tests for post-deployment custom resource Lambda."""
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch


def _load_post_deployment_module():
    root = Path(__file__).resolve().parent.parent
    module_path = root / "post_deployment" / "app.py"
    spec = importlib.util.spec_from_file_location("post_deployment_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _event(request_type: str, wait_seconds: int = 0):
    return {
        "RequestType": request_type,
        "ResponseURL": "https://example.com/response",
        "StackId": "stack-id",
        "RequestId": "request-id",
        "LogicalResourceId": "logical-resource-id",
        "PhysicalResourceId": "physical-resource-id",
        "ResourceProperties": {"WaitSeconds": str(wait_seconds)},
    }


class TestPostDeploymentHandler:
    def test_create_success_saves_backgrounds_and_returns_success(self, monkeypatch):
        app = _load_post_deployment_module()
        monkeypatch.setenv("NCPBackgroundSheetId", "sheet-id")
        event = _event("Create", wait_seconds=1)

        backgrounds = [
            {"name": "npc1", "age": "18", "gender": "M", "background": "bg1"},
            {"name": "npc2", "age": "20", "gender": "F", "background": "bg2"},
        ]

        with patch.object(app, "sleep") as mock_sleep, \
             patch.object(app, "get_npc_background_google_spreadsheet", return_value=backgrounds), \
             patch.object(app, "save_npc_background") as mock_save, \
             patch.object(app.cfnresponse, "send") as mock_send:
            app.lambda_handler(event, None)

        mock_sleep.assert_called_once_with(1)
        assert mock_save.call_count == 2
        assert mock_send.call_count == 1
        args = mock_send.call_args[0]
        assert args[2] == app.cfnresponse.SUCCESS
        assert args[3]["TimeWaited"] == 1

    def test_create_fails_when_background_sheet_empty(self, monkeypatch):
        app = _load_post_deployment_module()
        monkeypatch.setenv("NCPBackgroundSheetId", "sheet-id")
        event = _event("Create")

        with patch.object(app, "sleep"), \
             patch.object(app, "get_npc_background_google_spreadsheet", return_value=[]), \
             patch.object(app, "save_npc_background") as mock_save, \
             patch.object(app.cfnresponse, "send") as mock_send:
            app.lambda_handler(event, None)

        mock_save.assert_not_called()
        assert mock_send.call_count == 1
        args = mock_send.call_args[0]
        assert args[2] == app.cfnresponse.FAILED
        assert "Failed to retrieve NPC backgrounds" in args[3]["Reason"]

    def test_update_fails_fast_on_unexpected_exception(self, monkeypatch):
        app = _load_post_deployment_module()
        monkeypatch.setenv("NCPBackgroundSheetId", "sheet-id")
        event = _event("Update")

        with patch.object(app, "sleep"), \
             patch.object(app, "get_npc_background_google_spreadsheet", side_effect=RuntimeError("boom")), \
             patch.object(app.cfnresponse, "send") as mock_send:
            app.lambda_handler(event, None)

        assert mock_send.call_count == 1
        args = mock_send.call_args[0]
        assert args[2] == app.cfnresponse.FAILED
        assert "Failed: boom" in args[3]["Reason"]

    def test_delete_returns_success_without_sheet_fetch(self):
        app = _load_post_deployment_module()
        event = _event("Delete")

        with patch.object(app, "sleep"), \
             patch.object(app, "get_npc_background_google_spreadsheet") as mock_fetch, \
             patch.object(app.cfnresponse, "send") as mock_send:
            app.lambda_handler(event, None)

        mock_fetch.assert_not_called()
        assert mock_send.call_count == 1
        args = mock_send.call_args[0]
        assert args[2] == app.cfnresponse.SUCCESS
