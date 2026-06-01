"""
Custom exception handler for Acadexis backend.
Injects rate limit headers into throttled responses for frontend consumption.
"""

from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import Throttled
import time


def custom_exception_handler(exc, context):
    """
    Custom exception handler that adds rate limit headers when a request is throttled.

    Frontend reads X-RateLimit-Reset to know when to retry the request.
    """
    response = drf_exception_handler(exc, context)

    if isinstance(exc, Throttled) and response is not None:
        # Calculate reset time (default to 1 hour if wait is not provided)
        reset_time = int(time.time()) + (exc.wait or 3600)

        # Add rate limit headers that the frontend reads
        response["X-RateLimit-Limit"] = "1000"
        response["X-RateLimit-Remaining"] = "0"
        response["X-RateLimit-Reset"] = str(reset_time)

    return response