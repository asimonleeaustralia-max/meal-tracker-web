"""Tiny logging helper so every service logs in a consistent JSON-ish format.

Production deployments to Azure Container Apps will surface these in
Log Analytics / Application Insights.
"""
from __future__ import annotations

import logging
import sys


def configure_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    fmt = (
        f'{{"ts":"%(asctime)s","svc":"{service_name}",'
        '"lvl":"%(levelname)s","logger":"%(name)s","msg":%(message)r}'
    )
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root = logging.getLogger()
    # Replace any default handlers so we don't double-log under uvicorn
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet down uvicorn access logs a bit
    logging.getLogger("uvicorn.access").setLevel("WARNING")

    return logging.getLogger(service_name)
