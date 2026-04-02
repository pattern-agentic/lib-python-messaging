import slim_bindings


def parse_name(name_str: str) -> slim_bindings.Name:
    """Parse 'org/namespace/app' string into slim_bindings.Name."""
    return slim_bindings.Name.from_string(name_str)
