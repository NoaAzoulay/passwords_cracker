"""Israeli phone number password scheme implementation."""

from typing import Tuple
from shared.interfaces.password_scheme import PasswordScheme


class IlPhone05xDashScheme(PasswordScheme):
    """Israeli phone number scheme: 05X-XXXXXXX.
    
    Password format: {prefix}-{suffix}
    - Prefix: 050, 051, 052, 053, 054, 055, 056, 057, 058, 059
    - Suffix: 7-digit zero-padded number (0000000-9999999)
    
    Total search space: 10 prefixes × 10,000,000 numbers = 100,000,000
    Index range: 0 to 99,999,999 (inclusive)
    """
    
    PREFIXES = ["050", "051", "052", "053", "054", "055", "056", "057", "058", "059"]
    NUMBERS_PER_PREFIX = 10_000_000  # 0000000 to 9999999
    
    def index_to_password(self, index: int) -> str:
        """Convert index to password format 05X-XXXXXXX.
        
        Optimized for performance: uses string formatting efficiently.
        
        Args:
            index: Integer index in range [0, 99,999,999]
            
        Returns:
            Password string in format "05X-XXXXXXX"
            
        Raises:
            ValueError: If index is negative or exceeds valid range
        """
        if index < 0:
            raise ValueError(f"Index {index} is negative")
        
        prefix_index = index // self.NUMBERS_PER_PREFIX
        local_number = index % self.NUMBERS_PER_PREFIX
        
        if prefix_index >= len(self.PREFIXES):
            raise ValueError(f"Index {index} exceeds valid range")
        
        # Optimized: single f-string instead of multiple string operations
        return f"{self.PREFIXES[prefix_index]}-{local_number:07d}"
    
    def get_space_bounds(self) -> Tuple[int, int]:
        """Return (0, total_space - 1) inclusive.
        
        Returns:
            Tuple of (0, 99,999,999)
        """
        total_space = len(self.PREFIXES) * self.NUMBERS_PER_PREFIX
        return (0, total_space - 1)

