import slim_bindings


def parse_name(name_str: str) -> slim_bindings.Name:
    """Parse 'org/namespace/app' string into slim_bindings.Name."""
    parts = name_str.split('/')
    if len(parts) >= 3:
        return slim_bindings.Name(parts[0], parts[1], parts[2])
    raise ValueError(f"Name must be org/namespace/app format, got: {name_str}")
