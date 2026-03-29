"""CLI commands for property management domain."""

from remi.interfaces.cli.properties.leases import cmd as leases_cmd
from remi.interfaces.cli.properties.maintenance import cmd as maintenance_cmd
from remi.interfaces.cli.properties.portfolio import cmd as portfolio_cmd
from remi.interfaces.cli.properties.property import cmd as property_cmd
from remi.interfaces.cli.properties.report import cmd as report_cmd
from remi.interfaces.cli.properties.tenants import cmd as tenants_cmd
from remi.interfaces.cli.properties.units import cmd as units_cmd

__all__ = [
    "leases_cmd",
    "maintenance_cmd",
    "portfolio_cmd",
    "property_cmd",
    "report_cmd",
    "tenants_cmd",
    "units_cmd",
]
