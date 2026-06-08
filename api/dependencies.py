"""App-state container so handlers can reach the shared db/analyzer/executor
without re-instantiating them per request."""
from dataclasses import dataclass


@dataclass
class AppDependencies:
    db: object
    analyzer: object
    executor: object
    webhook_secret: str
