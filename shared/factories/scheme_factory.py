"""Factory for creating password scheme instances."""

from shared.interfaces.password_scheme import PasswordScheme
from shared.implementations.schemes import IlPhone05xDashScheme
from shared.consts import PasswordSchemeName


def create_scheme(scheme_name: str) -> PasswordScheme:
    """Factory for creating password schemes.
    
    Args:
        scheme_name: Name of the scheme to create
        
    Returns:
        PasswordScheme instance
        
    Raises:
        ValueError: If scheme_name is unknown
    """
    if scheme_name == PasswordSchemeName.IL_PHONE_05X_DASH:
        return IlPhone05xDashScheme()
    
    raise ValueError(f"Unknown scheme: {scheme_name}")

