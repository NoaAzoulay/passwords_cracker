"""Factory for creating password scheme instances."""

from shared.interfaces.password_scheme import PasswordScheme
from shared.implementations.schemes import IlPhone05xDashScheme
from shared.domain.consts import PasswordSchemeName


SCHEMES: dict[str, type[PasswordScheme]] = {
    PasswordSchemeName.IL_PHONE_05X_DASH: IlPhone05xDashScheme,
}


def create_scheme(scheme_name: str) -> PasswordScheme:
    """Factory for creating password schemes.
        
    Returns:
        PasswordScheme instance
        
    Raises:
        ValueError: If scheme_name is unknown
    """
    try:
        scheme_cls = SCHEMES[scheme_name]
    except KeyError:
        raise ValueError(f"Unknown scheme: {scheme_name}")
    return scheme_cls()

