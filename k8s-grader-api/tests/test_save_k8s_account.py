"""Tests for the save-k8s-account Lambda."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _load_module():
    root = Path(__file__).resolve().parent.parent
    module_path = root / "save-k8s-account" / "app.py"
    spec = importlib.util.spec_from_file_location("save_k8s_account_app", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _multipart_event():
    return {
        "httpMethod": "POST",
        "headers": {"content-type": "multipart/form-data; boundary=abc"},
        "body": "ignored",
        "isBase64Encoded": False,
    }


class TestSaveK8sAccount:
    def test_options_returns_cors_ready_response(self):
        app = _load_module()

        response = app.lambda_handler({"httpMethod": "OPTIONS", "headers": {}}, None)

        assert response["statusCode"] == 200
        assert response["body"] == '{"status": "OK", "message": "OK"}'

    def test_save_account_probes_endpoint_before_persisting(self):
        app = _load_module()
        event = _multipart_event()

        fs = {
            "endpoint": type("Part", (), {"text": "https://cluster.example.com:6443"})(),
            "client-certificate": type("Part", (), {"text": "a" * 120})(),
            "client-key": type("Part", (), {"text": "b" * 120})(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "is_endpoint_exist", return_value=False), \
             patch.object(app, "probe_endpoint", return_value=None) as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        probed_config = mock_probe.call_args.args[0]
        assert probed_config["endpoint"] == "https://cluster.example.com:6443"
        assert probed_config["client_certificate"] == "a" * 120
        assert probed_config["client_key"] == "b" * 120
        save_args = mock_save.call_args.args
        save_kwargs = mock_save.call_args.kwargs
        assert save_args[:4] == (
            "student@example.com",
            "https://cluster.example.com:6443",
            "a" * 120,
            "b" * 120,
        )
        assert save_kwargs["auth_type"] == "client_certificate"
        assert response["statusCode"] == 200

    def test_save_account_stops_when_probe_fails(self):
        app = _load_module()
        event = _multipart_event()

        fs = {
            "endpoint": type("Part", (), {"text": "https://cluster.example.com:6443"})(),
            "client-certificate": type("Part", (), {"text": "a" * 120})(),
            "client-key": type("Part", (), {"text": "b" * 120})(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "is_endpoint_exist", return_value=False), \
             patch.object(app, "probe_endpoint", return_value="dial tcp timeout") as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        mock_probe.assert_called_once()
        mock_save.assert_not_called()
        assert response["statusCode"] == 200
        assert "Endpoint probe failed" in response["body"]

    def test_save_account_returns_error_for_invalid_api_key(self):
        app = _load_module()
        event = _multipart_event()

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value={
                 "endpoint": type("Part", (), {"text": "https://cluster.example.com:6443"})(),
             }), \
             patch.object(app, "get_email_from_event", side_effect=ValueError("Invalid or expired API key: InvalidToken")), \
             patch.object(app, "is_endpoint_exist") as mock_exists, \
             patch.object(app, "probe_endpoint") as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        mock_exists.assert_not_called()
        mock_probe.assert_not_called()
        mock_save.assert_not_called()
        assert response["statusCode"] == 200
        assert "Invalid or expired API key" in response["body"]

    def test_save_account_allows_minikube_without_cert_or_key(self):
        app = _load_module()
        event = _multipart_event()

        fs = {
            "endpoint": type("Part", (), {"text": "https://minikube.example.com:8443"})(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "is_endpoint_exist", return_value=False), \
             patch.object(app, "probe_endpoint", return_value=None) as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        probed_config = mock_probe.call_args.args[0]
        assert probed_config["endpoint"] == "https://minikube.example.com:8443"
        assert probed_config["client_certificate"] == app.FAKE_CLIENT_CERTIFICATE
        assert probed_config["client_key"] == app.FAKE_CLIENT_KEY
        save_args = mock_save.call_args.args
        assert save_args[:4] == (
            "student@example.com",
            "https://minikube.example.com:8443",
            app.FAKE_CLIENT_CERTIFICATE,
            app.FAKE_CLIENT_KEY,
        )
        assert response["statusCode"] == 200

    def test_validate_input_rejects_half_filled_credentials(self):
        app = _load_module()

        assert (
            app.validate_manual_input(
                "student@example.com",
                "https://minikube.example.com:8443",
                "cert",
                None,
            )
            == "Client certificate and client key must be provided together"
        )

    def test_save_account_normalizes_endpoint_before_duplicate_check(self):
        app = _load_module()
        event = _multipart_event()

        fs = {
            "endpoint": type("Part", (), {"text": "https://cluster.example.com:6443/"})(),
            "client-certificate": type("Part", (), {"text": "a" * 120})(),
            "client-key": type("Part", (), {"text": "b" * 120})(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "is_endpoint_exist", return_value=False) as mock_exists, \
             patch.object(app, "probe_endpoint", return_value=None) as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        mock_exists.assert_called_once_with("student@example.com", "https://cluster.example.com:6443")
        probed_config = mock_probe.call_args.args[0]
        assert probed_config["endpoint"] == "https://cluster.example.com:6443"
        assert probed_config["client_certificate"] == "a" * 120
        assert probed_config["client_key"] == "b" * 120
        save_args = mock_save.call_args.args
        assert save_args[:4] == (
            "student@example.com",
            "https://cluster.example.com:6443",
            "a" * 120,
            "b" * 120,
        )
        assert response["statusCode"] == 200

    def test_probe_endpoint_falls_back_until_version_succeeds(self):
        app = _load_module()

        def fake_run(cmd, **kwargs):
            raw_arg = next(value for value in cmd if value.startswith("--raw="))
            if raw_arg == "--raw=/version":
                return SimpleNamespace(returncode=0, stderr="", stdout='{"gitVersion":"v1.31.0"}')
            return SimpleNamespace(returncode=1, stderr="Error from server (NotFound): not found", stdout="")

        with patch.object(app.subprocess, "run", side_effect=fake_run) as mock_run:
            result = app.probe_endpoint("https://cluster.example.com:6443", None, None)

        assert result is None
        assert mock_run.call_count == 4
        assert any("--raw=/version" in call.args[0] for call in mock_run.call_args_list)

    def test_probe_endpoint_reports_all_paths_when_every_probe_fails(self):
        app = _load_module()

        with patch.object(
            app.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stderr="Error from server (NotFound): not found", stdout=""),
        ):
            result = app.probe_endpoint("https://cluster.example.com:6443", None, None)

        assert "/readyz: Error from server (NotFound): not found" in result
        assert "/version: Error from server (NotFound): not found" in result

    def test_save_account_accepts_kubeconfig_text(self):
        app = _load_module()
        event = _multipart_event()
        kubeconfig = """
apiVersion: v1
kind: Config
clusters:
- name: hilarious-dance-sparrow
  cluster:
    server: https://cluster.example.com
    certificate-authority-data: Y2E=
contexts:
- name: local-pc-context
  context:
    cluster: hilarious-dance-sparrow
    user: local-pc-user
current-context: local-pc-context
users:
- name: local-pc-user
  user:
    token: token-value
"""
        fs = {
            "kubeconfig": type("Part", (), {"text": kubeconfig})(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "is_endpoint_exist", return_value=False), \
             patch.object(app, "probe_endpoint", return_value=None) as mock_probe, \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        mock_probe.assert_called_once()
        save_kwargs = mock_save.call_args.kwargs
        assert save_kwargs["bearer_token"] == "token-value"
        assert save_kwargs["auth_type"] == "token"
        body = json.loads(response["body"])
        assert body["authType"] == "token"
        assert body["context"] == "local-pc-context"

    def test_save_account_rejects_exec_kubeconfig(self):
        app = _load_module()
        event = _multipart_event()
        fs = {
            "kubeconfig": type(
                "Part",
                (),
                {
                    "text": """
apiVersion: v1
kind: Config
clusters:
- name: cluster
  cluster:
    server: https://cluster.example.com
contexts:
- name: ctx
  context:
    cluster: cluster
    user: aws-user
current-context: ctx
users:
- name: aws-user
  user:
    exec:
      command: aws
"""
                },
            )(),
        }

        with patch.object(app, "decode_post_data"), \
             patch.object(app, "parse_multipart_data", return_value=fs), \
             patch.object(app, "get_email_from_event", return_value="student@example.com"), \
             patch.object(app, "save_account") as mock_save:
            response = app.lambda_handler(event, None)

        mock_save.assert_not_called()
        assert "AWS exec/auth-provider kubeconfig is not supported" in response["body"]
