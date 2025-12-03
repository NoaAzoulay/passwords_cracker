"""Tests for password scheme implementations."""

import pytest
from shared.implementations.schemes import IlPhone05xDashScheme


class TestIlPhone05xDashScheme:
    """Tests for Israeli phone number scheme."""
    
    def test_index_0_maps_to_first_password(self):
        """Test that index 0 maps to '050-0000000'."""
        scheme = IlPhone05xDashScheme()
        password = scheme.index_to_password(0)
        assert password == "050-0000000"
    
    def test_index_1_maps_to_second_password(self):
        """Test that index 1 maps to '050-0000001'."""
        scheme = IlPhone05xDashScheme()
        password = scheme.index_to_password(1)
        assert password == "050-0000001"
    
    def test_index_9999999_maps_to_last_of_first_prefix(self):
        """Test that index 9,999,999 maps to '050-9999999'."""
        scheme = IlPhone05xDashScheme()
        password = scheme.index_to_password(9_999_999)
        assert password == "050-9999999"
    
    def test_prefix_boundary_at_10_million(self):
        """Test boundary where prefix changes at index 10,000,000."""
        scheme = IlPhone05xDashScheme()
        
        # Last of prefix 050
        password = scheme.index_to_password(9_999_999)
        assert password == "050-9999999"
        
        # First of prefix 051
        password = scheme.index_to_password(10_000_000)
        assert password == "051-0000000"
    
    def test_last_index_maps_to_last_password(self):
        """Test that last index maps to '059-9999999'."""
        scheme = IlPhone05xDashScheme()
        min_idx, max_idx = scheme.get_space_bounds()
        password = scheme.index_to_password(max_idx)
        assert password == "059-9999999"
    
    def test_get_space_bounds_returns_correct_range(self):
        """Test that get_space_bounds returns (0, 99,999,999)."""
        scheme = IlPhone05xDashScheme()
        min_idx, max_idx = scheme.get_space_bounds()
        
        assert min_idx == 0
        assert max_idx == 99_999_999
        assert max_idx - min_idx + 1 == 100_000_000  # Total space
    
    def test_total_space_is_100_million(self):
        """Test that total search space is exactly 100,000,000."""
        scheme = IlPhone05xDashScheme()
        min_idx, max_idx = scheme.get_space_bounds()
        total_space = max_idx - min_idx + 1
        assert total_space == 100_000_000
    
    def test_all_prefixes_covered(self):
        """Test that all 10 prefixes (050-059) are covered."""
        scheme = IlPhone05xDashScheme()
        prefixes = set()
        
        # Check first index of each prefix
        for i in range(0, 100_000_000, 10_000_000):
            password = scheme.index_to_password(i)
            prefix = password.split('-')[0]
            prefixes.add(prefix)
        
        assert len(prefixes) == 10
        expected_prefixes = {"050", "051", "052", "053", "054", "055", "056", "057", "058", "059"}
        assert prefixes == expected_prefixes
    
    def test_password_format_is_correct(self):
        """Test that all passwords match format 05X-XXXXXXX."""
        scheme = IlPhone05xDashScheme()
        
        test_indices = [0, 1, 100, 1000, 9_999_999, 10_000_000, 99_999_999]
        
        for idx in test_indices:
            password = scheme.index_to_password(idx)
            
            # Format: 05X-XXXXXXX (11 characters total)
            assert len(password) == 11
            assert password[3] == '-'
            
            # Prefix: 05X where X is 0-9
            prefix = password[:3]
            assert prefix.startswith("05")
            assert prefix[2] in "0123456789"
            
            # Suffix: 7 digits
            suffix = password[4:]
            assert len(suffix) == 7
            assert suffix.isdigit()
    
    def test_index_to_password_injectivity(self):
        """Test that different indices produce different passwords (injective)."""
        scheme = IlPhone05xDashScheme()
        passwords = set()
        
        # Test a sample of indices
        for i in range(0, 1000, 7):
            password = scheme.index_to_password(i)
            assert password not in passwords, f"Duplicate password at index {i}: {password}"
            passwords.add(password)
    
    def test_index_to_password_deterministic(self):
        """Test that same index always produces same password."""
        scheme = IlPhone05xDashScheme()
        
        for idx in [0, 100, 1000, 10_000_000, 99_999_999]:
            password1 = scheme.index_to_password(idx)
            password2 = scheme.index_to_password(idx)
            assert password1 == password2
    
    def test_invalid_index_raises_error(self):
        """Test that index out of range raises ValueError."""
        scheme = IlPhone05xDashScheme()
        
        # Test index that's too large
        with pytest.raises(ValueError, match="exceeds valid range"):
            scheme.index_to_password(100_000_000)  # Out of range
        
        # Test negative index
        with pytest.raises(ValueError, match="is negative"):
            scheme.index_to_password(-1)  # Negative index
    
    @pytest.mark.parametrize("index,expected_prefix,expected_suffix", [
        (0, "050", "0000000"),
        (1, "050", "0000001"),
        (9_999_999, "050", "9999999"),
        (10_000_000, "051", "0000000"),
        (19_999_999, "051", "9999999"),
        (20_000_000, "052", "0000000"),
        (99_999_999, "059", "9999999"),
    ])
    def test_specific_indices(self, index, expected_prefix, expected_suffix):
        """Test specific index mappings."""
        scheme = IlPhone05xDashScheme()
        password = scheme.index_to_password(index)
        prefix, suffix = password.split('-')
        assert prefix == expected_prefix
        assert suffix == expected_suffix

