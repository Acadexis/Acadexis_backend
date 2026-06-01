"""
Custom throttle classes for Acadexis backend.
Exposes rate limit headers for frontend consumption.
"""

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class AcadexisUserThrottle(UserRateThrottle):
    """Throttle class for authenticated users."""
    rate = "1000/day"


class AcadexisAnonThrottle(AnonRateThrottle):
    """Throttle class for anonymous users."""
    rate = "100/day"