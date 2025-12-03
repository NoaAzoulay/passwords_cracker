"""Abstract password scheme interface."""

from abc import ABC, abstractmethod
from typing import Tuple


class PasswordScheme(ABC):
    """Abstract password scheme interface.
    
    All password schemes must implement:
    - index_to_password: Convert an index to a password string
    - get_space_bounds: Return the valid index range (min, max) inclusive
    """
    
    @abstractmethod
    def index_to_password(self, index: int) -> str:
        """Convert index to password.
        
        Args:
            index: Integer index in the password space
            
        Returns:
            Password string corresponding to the index
            
        Raises:
            ValueError: If index is out of valid range
        """
        pass
    
    @abstractmethod
    def get_space_bounds(self) -> Tuple[int, int]:
        """Return the valid index range for this scheme.
        
        Returns:
            Tuple of (min_index, max_index) inclusive
        """
        pass

