"""Tests for password scheme factory."""

import pytest
from shared.factories.scheme_factory import create_scheme, SCHEMES
from shared.domain.consts import PasswordSchemeName
from shared.implementations.schemes import IlPhone05xDashScheme


class TestSchemeFactory:
    """Tests for password scheme factory."""
    
    def test_create_scheme_valid(self):
        """Test creating a valid scheme."""
        # Test with enum member (should work since it's str, Enum)
        scheme = create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH)
        assert isinstance(scheme, IlPhone05xDashScheme)
        
        # Test with string value (should also work)
        scheme2 = create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH.value)
        assert isinstance(scheme2, IlPhone05xDashScheme)
    
    def test_create_scheme_unknown_raises_value_error(self):
        """Test that unknown scheme raises ValueError."""
        with pytest.raises(ValueError, match="Unknown scheme"):
            create_scheme("unknown_scheme")
    
    def test_create_scheme_empty_string_raises_value_error(self):
        """Test that empty string scheme raises ValueError."""
        with pytest.raises(ValueError, match="Unknown scheme"):
            create_scheme("")
    
    def test_create_scheme_case_sensitive(self):
        """Test that scheme names are case-sensitive."""
        # Should fail because case doesn't match
        with pytest.raises(ValueError, match="Unknown scheme"):
            create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH.upper())
    
    def test_schemes_dict_contains_expected_scheme(self):
        """Test that SCHEMES dict contains expected scheme."""
        # Enum member itself works as dict key (since it's a str, Enum)
        assert PasswordSchemeName.IL_PHONE_05X_DASH in SCHEMES
        assert SCHEMES[PasswordSchemeName.IL_PHONE_05X_DASH] == IlPhone05xDashScheme
        # String value also works (enum members that are str, Enum compare equal to strings)
        assert PasswordSchemeName.IL_PHONE_05X_DASH.value in SCHEMES
        assert SCHEMES[PasswordSchemeName.IL_PHONE_05X_DASH.value] == IlPhone05xDashScheme
    
    def test_create_scheme_returns_new_instance(self):
        """Test that each call returns a new instance."""
        scheme1 = create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH)
        scheme2 = create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH)
        
        # Should be different instances
        assert scheme1 is not scheme2
        # But should be same type
        assert type(scheme1) == type(scheme2)
    
    def test_create_scheme_works_with_scheme_instance(self):
        """Test that created scheme works correctly."""
        scheme = create_scheme(PasswordSchemeName.IL_PHONE_05X_DASH)
        
        # Verify it implements the interface
        password = scheme.index_to_password(0)
        assert password == "050-0000000"
        
        min_idx, max_idx = scheme.get_space_bounds()
        assert min_idx == 0
        assert max_idx == 99_999_999

