"""Backward-compat shim -- use gateway.rest_shim instead."""

from gateway.rest_shim import RESTShim as RESTApp, create_app  # noqa: F401

__all__ = ["RESTApp", "create_app"]
