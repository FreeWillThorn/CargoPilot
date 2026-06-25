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
from .master_data import (
    create_consignee,
    create_supplier,
    create_warehouse,
    get_consignee_order_defaults,
    list_suppliers,
    list_warehouses,
    update_consignee,
    update_supplier,
    update_warehouse,
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
    "create_consignee",
    "create_supplier",
    "create_warehouse",
    "get_consignee_order_defaults",
    "list_suppliers",
    "list_warehouses",
    "update_consignee",
    "update_supplier",
    "update_warehouse",
]
