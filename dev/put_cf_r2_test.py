from pathlib import Path
import boto3, os


s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)

s3.put_object(
    Bucket=os.environ["R2_BUCKET"],
    Key="test_ok.txt",
    Body=b"ok",
    ContentType="text/plain",
)
