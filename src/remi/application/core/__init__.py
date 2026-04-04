"""Domain — pure business logic with no infrastructure dependencies.

    models/         Entity DTOs, enums, value objects
    protocols.py    Repository ABCs (PropertyStore and narrow per-entity protocols)
    rollups.py      RollupStore ABC + ManagerSnapshot / PropertySnapshot DTOs
    rules.py        Stateless business rule functions
"""
