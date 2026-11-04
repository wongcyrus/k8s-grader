"""Storage and private-origin rollout invariants."""
from pathlib import Path

import pytest
import yaml


class CloudFormationLoader(yaml.SafeLoader):
    pass


def construct_intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    if tag == "GetAtt" and isinstance(value, str):
        value = value.split(".", 1)
    return {tag if tag in ("Ref", "Condition") else f"Fn::{tag}": value}


CloudFormationLoader.add_multi_constructor("!", construct_intrinsic)
TEMPLATE = yaml.load(
    (Path(__file__).parent.parent / "template.yaml").read_text(),
    Loader=CloudFormationLoader,
)
RESOURCES = TEMPLATE["Resources"]


@pytest.mark.parametrize(
    "bucket", ["TestResultBucket", "ExamWebsiteBucket", "GameSourceBucket"]
)
def test_data_buckets_are_private_versioned_logged_and_tls_only(bucket):
    resource = RESOURCES[bucket]
    properties = resource["Properties"]
    assert all(properties["PublicAccessBlockConfiguration"].values())
    assert properties["OwnershipControls"]["Rules"] == [
        {"ObjectOwnership": "BucketOwnerEnforced"}
    ]
    assert properties["VersioningConfiguration"]["Status"] == "Enabled"
    assert properties["LoggingConfiguration"]["DestinationBucketName"] == {
        "Ref": "S3AccessLogBucket"
    }
    assert resource["DeletionPolicy"] == resource["UpdateReplacePolicy"] == "Retain"
    statements = RESOURCES[f"{bucket}Policy"]["Properties"]["PolicyDocument"][
        "Statement"
    ]
    deny = next(item for item in statements if item["Sid"] == "DenyInsecureTransport")
    assert deny["Effect"] == "Deny" and deny["Principal"] == "*"
    assert deny["Action"] == "s3:*"
    assert deny["Condition"]["Bool"]["aws:SecureTransport"] is False
    assert {"Fn::GetAtt": [bucket, "Arn"]} in deny["Resource"]
    assert {"Fn::Sub": f"${{{bucket}.Arn}}/*"} in deny["Resource"]
    assert not any(
        item["Effect"] == "Allow" and item["Principal"] == "*" for item in statements
    )


def test_storage_uses_only_s3_managed_encryption():
    assert not any(
        resource["Type"].startswith("AWS::KMS::") for resource in RESOURCES.values()
    )
    for resource in RESOURCES.values():
        if resource["Type"] == "AWS::S3::Bucket":
            rules = resource["Properties"]["BucketEncryption"][
                "ServerSideEncryptionConfiguration"
            ]
            assert rules == [
                {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]


def test_cloudfront_uses_scoped_signed_rest_access_without_changing_viewer_https():
    origin = RESOURCES["ExamWebsiteCloudFrontDistribution"]["Properties"][
        "DistributionConfig"
    ]
    assert "CustomOriginConfig" not in origin["Origins"][0]
    assert origin["Origins"][0]["DomainName"] == {
        "Fn::GetAtt": ["ExamWebsiteBucket", "RegionalDomainName"]
    }
    assert origin["Origins"][0]["OriginAccessControlId"] == {
        "Ref": "ExamWebsiteOriginAccessControl"
    }
    oac = RESOURCES["ExamWebsiteOriginAccessControl"]["Properties"][
        "OriginAccessControlConfig"
    ]
    assert oac["SigningBehavior"] == "always" and oac["SigningProtocol"] == "sigv4"
    for behavior in [origin["DefaultCacheBehavior"], *origin["CacheBehaviors"]]:
        assert behavior["ViewerProtocolPolicy"] == "redirect-to-https"
        assert behavior["TargetOriginId"] == origin["Origins"][0]["Id"]
    association = origin["DefaultCacheBehavior"]["FunctionAssociations"][0]
    assert association["EventType"] == "viewer-request"
    assert association["FunctionARN"] == {
        "Fn::GetAtt": ["PortalDirectoryIndexFunction", "FunctionARN"]
    }
    policy = RESOURCES["ExamWebsiteBucketPolicy"]["Properties"]["PolicyDocument"]
    grant = next(item for item in policy["Statement"] if item["Effect"] == "Allow")
    assert grant["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert grant["Action"] == "s3:GetObject"
    assert (
        "${ExamWebsiteCloudFrontDistribution}"
        in grant["Condition"]["StringEquals"]["AWS:SourceArn"]["Fn::Sub"]
    )
    assert "WebsiteConfiguration" not in RESOURCES["ExamWebsiteBucket"]["Properties"]


def test_access_logs_expire_without_expiring_reports_or_creating_recursive_logs():
    logs = RESOURCES["S3AccessLogBucket"]["Properties"]
    assert "LoggingConfiguration" not in logs
    assert "VersioningConfiguration" not in logs
    expiry = logs["LifecycleConfiguration"]["Rules"][0]
    assert expiry["Prefix"] == "logs/" and expiry["ExpirationInDays"] == 30
    policy = RESOURCES["S3AccessLogBucketPolicy"]["Properties"]["PolicyDocument"]
    grant = next(item for item in policy["Statement"] if item["Effect"] == "Allow")
    assert grant["Principal"] == {"Service": "logging.s3.amazonaws.com"}
    assert grant["Action"] == "s3:PutObject"
    assert grant["Condition"]["StringEquals"]["aws:SourceAccount"] == {
        "Ref": "AWS::AccountId"
    }
    assert grant["Condition"]["ArnLike"]["aws:SourceArn"] == [
        {"Fn::GetAtt": [name, "Arn"]}
        for name in ("TestResultBucket", "ExamWebsiteBucket", "GameSourceBucket")
    ]
    reports = RESOURCES["TestResultBucket"]["Properties"]["LifecycleConfiguration"]
    for rule in reports["Fn::If"][1]["Rules"]:
        assert "ExpirationInDays" not in rule
        assert "NoncurrentVersionExpiration" not in rule
