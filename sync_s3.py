"""Download snapshots from S3 that are not yet in data/raw."""
import os
from pathlib import Path

import boto3

BUCKET = os.environ.get("TFL_BUCKET", "tfl-raw-2026")
PREFIX = "raw/"
DEST = Path("data/raw")


def main() -> None:
    s3 = boto3.client("s3", region_name="eu-west-2")
    downloaded = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            target = DEST / Path(obj["Key"]).relative_to("raw")
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(BUCKET, obj["Key"], str(target))
            downloaded += 1
    print(f"Downloaded {downloaded} new snapshots")


if __name__ == "__main__":
    main()  