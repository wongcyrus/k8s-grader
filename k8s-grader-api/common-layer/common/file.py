import json
import os
import shutil
import re

from common.kubeconfig import build_kubeconfig


MANAGED_TMP_FILES = {
    "client_certificate.crt",
    "client_key.key",
    "ca.crt",
    "kubeconfig.yaml",
    "json_input.json",
    "report.html",
    "easter_egg.csv",
}
MANAGED_TMP_PATTERNS = (
    re.compile(r"^game\d+$"),
    re.compile(r"^game\d+\.zip$"),
    re.compile(r"^game\d+_source\.txt$"),
)


def _is_managed_tmp_entry(filename):
    if filename in MANAGED_TMP_FILES:
        return True
    return any(pattern.match(filename) for pattern in MANAGED_TMP_PATTERNS)


def clear_tmp_directory():
    for filename in os.listdir("/tmp/"):
        if not _is_managed_tmp_entry(filename):
            continue
        file_path = os.path.join("/tmp/", filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to delete {file_path}. Reason: {e}") from e


def write_user_files(client_certificate, client_key):
    with open("/tmp/client_certificate.crt", "w", encoding="utf-8") as cert_file:
        cert_file.write(client_certificate)
    with open("/tmp/client_key.key", "w", encoding="utf-8") as key_file:
        key_file.write(client_key)


def write_k8s_access_files(access_config):
    endpoint = access_config.get("endpoint")
    kubeconfig = access_config.get("kubeconfig")
    client_certificate = access_config.get("client_certificate")
    client_key = access_config.get("client_key")
    bearer_token = access_config.get("bearer_token")
    ca_certificate = access_config.get("ca_certificate")
    insecure_skip_tls_verify = bool(access_config.get("insecure_skip_tls_verify", False))

    if client_certificate and client_key:
        write_user_files(client_certificate, client_key)

    if ca_certificate:
        with open("/tmp/ca.crt", "w", encoding="utf-8") as ca_file:
            ca_file.write(ca_certificate)

    if not kubeconfig and endpoint and (bearer_token or (client_certificate and client_key)):
        kubeconfig = build_kubeconfig(
            endpoint,
            client_certificate=client_certificate,
            client_key=client_key,
            bearer_token=bearer_token,
            ca_certificate=ca_certificate,
            insecure_skip_tls_verify=insecure_skip_tls_verify or not bool(ca_certificate),
        )

    if kubeconfig:
        with open("/tmp/kubeconfig.yaml", "w", encoding="utf-8") as kubeconfig_file:
            kubeconfig_file.write(kubeconfig)


def create_json_input(endpoint, extra_data=None):
    if extra_data is None:
        extra_data = {}
    if extra_data.get("$client_certificate") and extra_data.get("$client_key"):
        write_user_files(extra_data["$client_certificate"], extra_data["$client_key"])
    if extra_data.get("$ca_certificate"):
        with open("/tmp/ca.crt", "w", encoding="utf-8") as ca_file:
            ca_file.write(extra_data["$ca_certificate"])
    if extra_data.get("$kubeconfig"):
        with open("/tmp/kubeconfig.yaml", "w", encoding="utf-8") as kubeconfig_file:
            kubeconfig_file.write(extra_data["$kubeconfig"])

    json_input = {
        "host": endpoint,
    }
    if os.path.exists("/tmp/client_certificate.crt"):
        json_input["cert_file"] = "/tmp/client_certificate.crt"
    if os.path.exists("/tmp/client_key.key"):
        json_input["key_file"] = "/tmp/client_key.key"
    if os.path.exists("/tmp/ca.crt"):
        json_input["ca_file"] = "/tmp/ca.crt"
    if os.path.exists("/tmp/kubeconfig.yaml"):
        json_input["kubeconfig_file"] = "/tmp/kubeconfig.yaml"
    json_input.update(extra_data)
    # Remove all metadata keys (keys starting with $) - not needed for test execution
    keys_to_remove = [key for key in json_input.keys() if key.startswith('$')]
    for key in keys_to_remove:
        del json_input[key]
    with open("/tmp/json_input.json", "w", encoding="utf-8") as json_file:
        json.dump(json_input, json_file)
