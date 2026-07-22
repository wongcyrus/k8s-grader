import json
import os
import shutil
import re


MANAGED_TMP_FILES = {
    "client_certificate.crt",
    "client_key.key",
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


def create_json_input(endpoint, extra_data=None):
    if extra_data is None:
        extra_data = {}
    json_input = {
        "cert_file": "/tmp/client_certificate.crt",
        "key_file": "/tmp/client_key.key",
        "host": endpoint,
    }
    json_input.update(extra_data)
    # Remove all metadata keys (keys starting with $) - not needed for test execution
    keys_to_remove = [key for key in json_input.keys() if key.startswith('$')]
    for key in keys_to_remove:
        del json_input[key]
    with open("/tmp/json_input.json", "w", encoding="utf-8") as json_file:
        json.dump(json_input, json_file)
