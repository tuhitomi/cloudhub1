"""Lambda entry point for the management API.

Importing the SDK and the request-path modules here moves that work into the
Lambda init phase. With SnapStart enabled the imported state is captured in the
snapshot, so a cold start restores it instead of re-importing. Nothing in this
module opens a network connection, reads credentials or creates an AWS client:
those stay lazy in cloudhub.api so they are created after restore.
"""
import boto3  # noqa: F401  (botocore and boto3 import cost is the main cold start)
import botocore.session  # noqa: F401

from . import api
from . import runtime  # noqa: F401
from . import service  # noqa: F401
from . import public_catalog  # noqa: F401

handler = api.handler
