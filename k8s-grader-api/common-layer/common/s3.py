import os

import boto3
from botocore.exceptions import ClientError
from common.status import GamePhrase

TestResultBucket = os.getenv("TestResultBucket")


def upload_test_result(file_name, game_phase, time, email, game, task):
    """
    Upload test result to S3.
    
    Args:
        game_phase: Either a GamePhrase enum or a string ('setup', 'check', etc.)
    """
    # Convert to string if it's an enum
    phase_name = game_phase.name if isinstance(game_phase, GamePhrase) else game_phase
    
    object_name = f"{game}/{email}/{task}/a_test_report_{phase_name}.html"
    object_name_with_time = (
        f"{game}/{email}/{task}/test_report_{phase_name}_{time}.html"
    )

    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(
            file_name,
            TestResultBucket,
            object_name,
            ExtraArgs={"ContentType": "text/html"},
        )
        s3_client.upload_file(
            file_name,
            TestResultBucket,
            object_name_with_time,
            ExtraArgs={"ContentType": "text/html"},
        )
    except ClientError:
        print("Credentials not available")
        return False
    return True


def generate_presigned_url(
    game_phase,
    time,
    email,
    game,
    task,
    expiration=604800,  # 7 days in seconds
):
    """
    Generate presigned URL for S3 object.
    
    Args:
        game_phase: Either a GamePhrase enum or a string ('setup', 'check', etc.)
    """
    try:
        _, object_name_with_time = get_bucket_key(email, game, task, game_phase, time)
        s3_client = boto3.client("s3")
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": TestResultBucket, "Key": object_name_with_time},
            ExpiresIn=expiration,
        )
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None


def get_bucket_key(email, game, task, game_phase, time):
    """
    Get S3 bucket and key for test report.
    
    Args:
        game_phase: Either a GamePhrase enum or a string ('setup', 'check', etc.)
    """
    # Convert to string if it's an enum
    phase_name = game_phase.name if isinstance(game_phase, GamePhrase) else game_phase
    
    object_name_with_time = (
        f"{game}/{email}/{task}/test_report_{phase_name}_{time}.html"
    )
    return TestResultBucket, object_name_with_time
