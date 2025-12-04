"""Tests for main entry point."""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
from main import validate_md5_hash, load_hashes_from_file, main


class TestValidateMD5Hash:
    """Tests for MD5 hash validation."""
    
    def test_valid_hash(self):
        """Test that valid MD5 hash passes validation."""
        assert validate_md5_hash("a" * 32) is True
        assert validate_md5_hash("1d0b28c7e3ef0ba9d3c04a4183b576ac") is True
    
    def test_invalid_hash_too_short(self):
        """Test that hash that's too short fails validation."""
        assert validate_md5_hash("a" * 31) is False
    
    def test_invalid_hash_too_long(self):
        """Test that hash that's too long fails validation."""
        assert validate_md5_hash("a" * 33) is False
    
    def test_invalid_hash_non_hex(self):
        """Test that hash with non-hex characters fails validation."""
        assert validate_md5_hash("g" * 32) is False
        assert validate_md5_hash("a" * 31 + "z") is False
    
    def test_hash_case_insensitive(self):
        """Test that validation is case-insensitive."""
        assert validate_md5_hash("A" * 32) is True
        assert validate_md5_hash("1D0B28C7E3EF0BA9D3C04A4183B576AC") is True


class TestLoadHashesFromFile:
    """Tests for loading hashes from file."""
    
    def test_load_valid_hashes(self, tmp_path):
        """Test loading file with valid hashes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("a" * 32 + "\n" + "b" * 32 + "\n" + "c" * 32)
        
        valid_hashes, invalid_hashes = load_hashes_from_file(str(test_file))
        
        assert len(valid_hashes) == 3
        assert len(invalid_hashes) == 0
        assert "a" * 32 in valid_hashes
        assert "b" * 32 in valid_hashes
        assert "c" * 32 in valid_hashes
    
    def test_load_empty_file(self, tmp_path):
        """Test loading empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        
        valid_hashes, invalid_hashes = load_hashes_from_file(str(test_file))
        
        assert len(valid_hashes) == 0
        assert len(invalid_hashes) == 0
    
    def test_load_file_with_empty_lines(self, tmp_path):
        """Test that empty lines are skipped."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("a" * 32 + "\n\n" + "b" * 32 + "\n   \n" + "c" * 32)
        
        valid_hashes, invalid_hashes = load_hashes_from_file(str(test_file))
        
        assert len(valid_hashes) == 3
        assert len(invalid_hashes) == 0
    
    def test_load_file_with_invalid_hashes(self, tmp_path):
        """Test that invalid hashes are separated from valid ones."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("a" * 32 + "\ninvalid\n" + "b" * 32 + "\ntoo_short")
        
        valid_hashes, invalid_hashes = load_hashes_from_file(str(test_file))
        
        assert len(valid_hashes) == 2
        assert len(invalid_hashes) == 2
        assert "a" * 32 in valid_hashes
        assert "b" * 32 in valid_hashes
        assert "invalid" in invalid_hashes
        assert "too_short" in invalid_hashes
    
    def test_load_file_with_mixed_case(self, tmp_path):
        """Test that hashes are normalized to lowercase."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("A" * 32 + "\n" + "B" * 32)
        
        valid_hashes, invalid_hashes = load_hashes_from_file(str(test_file))
        
        assert len(valid_hashes) == 2
        assert len(invalid_hashes) == 0
        assert "a" * 32 in valid_hashes
        assert "b" * 32 in valid_hashes
    
    def test_load_file_not_found(self):
        """Test that SystemExit is raised for non-existent file."""
        with pytest.raises(SystemExit):
            load_hashes_from_file("nonexistent_file_12345.txt")


class TestMain:
    """Tests for main() function."""
    
    @pytest.mark.asyncio
    async def test_main_empty_input(self, tmp_path, monkeypatch):
        """Test main with empty input file."""
        input_file = tmp_path / "empty.txt"
        input_file.write_text("")
        output_file = tmp_path / "output.txt"
        
        # Mock sys.argv
        monkeypatch.setattr(sys, "argv", ["main.py", str(input_file)])
        
        # Mock config
        with patch("main.config") as mock_config:
            mock_config.OUTPUT_FILE = str(output_file)
            mock_config.MINION_URLS = ["http://localhost:8000"]
            mock_config.MAX_CONCURRENT_JOBS = 3
            
            # Mock components to avoid actual initialization
            with patch("main.CrackedCache") as mock_cache_class, \
                 patch("main.MinionRegistry"), \
                 patch("main.MinionClient"), \
                 patch("main.JobManager"), \
                 patch("main.Scheduler"):
                
                # Create mock cache instance with clear method
                mock_cache = MagicMock()
                mock_cache_class.return_value = mock_cache
                
                # Should exit with code 0
                with pytest.raises(SystemExit) as exc_info:
                    await main()
                assert exc_info.value.code == 0
                
                # Verify CrackedCache was instantiated
                mock_cache_class.assert_called_once()
                
                # Verify cache.clear() was called at startup
                mock_cache.clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_main_no_args(self, monkeypatch):
        """Test main with no command line arguments."""
        monkeypatch.setattr(sys, "argv", ["main.py"])
        
        with pytest.raises(SystemExit) as exc_info:
            await main()
        assert exc_info.value.code == 1
    
    @pytest.mark.asyncio
    async def test_main_file_not_found(self, monkeypatch):
        """Test main with non-existent input file."""
        monkeypatch.setattr(sys, "argv", ["main.py", "nonexistent.txt"])
        
        with pytest.raises(SystemExit) as exc_info:
            await main()
        assert exc_info.value.code == 1


