"""CargoPilot application package."""

from .foundation import (
    ROLE_ADMIN,
    ROLE_WAREHOUSE,
    authenticate,
    can,
    connect,
    create_user,
    get_setting,
    initialize_database,
    record_audit_log,
    record_file_metadata,
    set_setting,
)

__all__ = [
    "ROLE_ADMIN",
    "ROLE_WAREHOUSE",
    "authenticate",
    "can",
    "connect",
    "create_user",
    "get_setting",
    "initialize_database",
    "record_audit_log",
    "record_file_metadata",
    "set_setting",
]
