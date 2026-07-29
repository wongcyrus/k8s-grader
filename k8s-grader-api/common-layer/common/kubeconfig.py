import base64
from typing import Any, Dict, Optional

import yaml


def _encode_data(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _decode_data(value: str, field_name: str) -> str:
    try:
        return base64.b64decode(value).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive decode guard
        raise ValueError(f"Invalid {field_name} in kubeconfig") from exc


def build_kubeconfig(
    endpoint: str,
    *,
    client_certificate: Optional[str] = None,
    client_key: Optional[str] = None,
    bearer_token: Optional[str] = None,
    ca_certificate: Optional[str] = None,
    insecure_skip_tls_verify: bool = False,
    cluster_name: str = "k8s-cluster",
    user_name: str = "k8s-user",
    context_name: str = "k8s-context",
) -> str:
    if not endpoint:
        raise ValueError("Endpoint is required to build kubeconfig")
    if bearer_token and (client_certificate or client_key):
        raise ValueError("Kubeconfig cannot mix bearer token and client certificate auth")
    if not bearer_token and not (client_certificate and client_key):
        raise ValueError("Kubeconfig requires either bearer token or client certificate auth")

    cluster: Dict[str, Any] = {"server": endpoint}
    if ca_certificate:
        cluster["certificate-authority-data"] = _encode_data(ca_certificate)
    elif insecure_skip_tls_verify:
        cluster["insecure-skip-tls-verify"] = True

    user: Dict[str, Any]
    auth_type: str
    if bearer_token:
        user = {"token": bearer_token}
        auth_type = "token"
    else:
        user = {
            "client-certificate-data": _encode_data(client_certificate or ""),
            "client-key-data": _encode_data(client_key or ""),
        }
        auth_type = "client_certificate"

    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": cluster_name, "cluster": cluster}],
        "contexts": [
            {
                "name": context_name,
                "context": {
                    "cluster": cluster_name,
                    "user": user_name,
                },
            }
        ],
        "current-context": context_name,
        "users": [{"name": user_name, "user": user}],
        "preferences": {},
    }
    rendered = yaml.safe_dump(config, sort_keys=False, default_flow_style=False, width=4096)
    if auth_type == "token":
        return rendered
    return rendered


def parse_kubeconfig(kubeconfig_text: str) -> Dict[str, Any]:
    try:
        config = yaml.safe_load(kubeconfig_text)
    except yaml.YAMLError as exc:
        raise ValueError("Invalid kubeconfig YAML") from exc

    if not isinstance(config, dict):
        raise ValueError("Invalid kubeconfig structure")

    contexts = config.get("contexts") or []
    if not contexts:
        raise ValueError("Kubeconfig must define at least one context")

    current_context_name = config.get("current-context")
    if current_context_name:
        context_entry = next((entry for entry in contexts if entry.get("name") == current_context_name), None)
        if not context_entry:
            raise ValueError("Kubeconfig current-context was not found in contexts")
    elif len(contexts) == 1:
        context_entry = contexts[0]
        current_context_name = context_entry.get("name")
    else:
        raise ValueError("Kubeconfig must define current-context when multiple contexts exist")

    context = context_entry.get("context") or {}
    cluster_ref = context.get("cluster")
    user_ref = context.get("user")
    if not cluster_ref or not user_ref:
        raise ValueError("Kubeconfig context must reference both cluster and user")

    cluster_entry = next((entry for entry in config.get("clusters", []) if entry.get("name") == cluster_ref), None)
    if not cluster_entry:
        raise ValueError("Kubeconfig cluster reference was not found")
    user_entry = next((entry for entry in config.get("users", []) if entry.get("name") == user_ref), None)
    if not user_entry:
        raise ValueError("Kubeconfig user reference was not found")

    cluster = cluster_entry.get("cluster") or {}
    endpoint = str(cluster.get("server") or "").strip()
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("Kubeconfig cluster server must be a valid http or https URL")

    ca_certificate = None
    if cluster.get("certificate-authority-data"):
        ca_certificate = _decode_data(cluster["certificate-authority-data"], "certificate-authority-data")
    elif cluster.get("certificate-authority"):
        raise ValueError("Kubeconfig file path references are not supported. Embed certificate-authority-data instead.")
    insecure_skip_tls_verify = bool(cluster.get("insecure-skip-tls-verify"))

    user = user_entry.get("user") or {}
    if user.get("exec"):
        raise ValueError("AWS exec/auth-provider kubeconfig is not supported here. Use a token-based or embedded-certificate kubeconfig.")

    bearer_token = user.get("token")
    client_certificate = None
    client_key = None
    auth_type = ""
    if bearer_token:
        auth_type = "token"
    elif user.get("client-certificate-data") and user.get("client-key-data"):
        auth_type = "client_certificate"
        client_certificate = _decode_data(user["client-certificate-data"], "client-certificate-data")
        client_key = _decode_data(user["client-key-data"], "client-key-data")
    elif user.get("client-certificate") or user.get("client-key"):
        raise ValueError("Kubeconfig file path references are not supported. Embed client-certificate-data and client-key-data instead.")
    else:
        raise ValueError("Unsupported kubeconfig user authentication. Provide a token or embedded client certificate and key.")

    normalized_kubeconfig = build_kubeconfig(
        endpoint,
        client_certificate=client_certificate,
        client_key=client_key,
        bearer_token=bearer_token,
        ca_certificate=ca_certificate,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
        cluster_name=cluster_ref,
        user_name=user_ref,
        context_name=current_context_name or "k8s-context",
    )

    return {
        "endpoint": endpoint,
        "client_certificate": client_certificate,
        "client_key": client_key,
        "bearer_token": bearer_token,
        "ca_certificate": ca_certificate,
        "kubeconfig": normalized_kubeconfig,
        "auth_type": auth_type,
        "context_name": current_context_name,
        "cluster_name": cluster_ref,
        "user_name": user_ref,
        "insecure_skip_tls_verify": insecure_skip_tls_verify,
    }


def build_manual_access_config(
    endpoint: str,
    client_certificate: str,
    client_key: str,
    *,
    ca_certificate: Optional[str] = None,
) -> Dict[str, Any]:
    kubeconfig = build_kubeconfig(
        endpoint,
        client_certificate=client_certificate,
        client_key=client_key,
        ca_certificate=ca_certificate,
        insecure_skip_tls_verify=not bool(ca_certificate),
    )
    return {
        "endpoint": endpoint,
        "client_certificate": client_certificate,
        "client_key": client_key,
        "bearer_token": None,
        "ca_certificate": ca_certificate,
        "kubeconfig": kubeconfig,
        "auth_type": "client_certificate",
        "context_name": "k8s-context",
        "cluster_name": "k8s-cluster",
        "user_name": "k8s-user",
        "insecure_skip_tls_verify": not bool(ca_certificate),
    }


def session_data_from_access_config(access_config: Dict[str, Any]) -> Dict[str, Any]:
    session_data = {
        "$endpoint": access_config["endpoint"],
        "$kubeconfig": access_config["kubeconfig"],
        "$auth_type": access_config.get("auth_type", ""),
    }
    if access_config.get("client_certificate"):
        session_data["$client_certificate"] = access_config["client_certificate"]
    if access_config.get("client_key"):
        session_data["$client_key"] = access_config["client_key"]
    if access_config.get("bearer_token"):
        session_data["$bearer_token"] = access_config["bearer_token"]
    if access_config.get("ca_certificate"):
        session_data["$ca_certificate"] = access_config["ca_certificate"]
    return session_data
