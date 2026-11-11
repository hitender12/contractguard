"""ContractGuard -- catch breaking API changes before they reach production.

Compares an OpenAPI contract against a baseline and classifies every
change as BREAKING / WARNING / SAFE / UNKNOWN under a server or client
compatibility profile.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
