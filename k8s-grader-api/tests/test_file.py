"""Tests for file utility functions"""
import json
import os
import tempfile
from unittest.mock import patch

from common.file import create_json_input, clear_tmp_directory, write_user_files


class TestCreateJsonInput:
    """Test create_json_input function"""
    
    def test_basic_json_input(self):
        """Test creating basic JSON input"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('common.file.open', create=True) as mock_open:
                mock_file = mock_open.return_value.__enter__.return_value
                
                create_json_input("https://k8s.example.com")
                
                # Verify file was opened for writing
                mock_open.assert_called_once_with("/tmp/json_input.json", "w", encoding="utf-8")
                
                # Get the JSON that was written
                written_data = ''.join(call.args[0] for call in mock_file.write.call_args_list)
                data = json.loads(written_data)
                
                assert data['host'] == "https://k8s.example.com"
                assert data['cert_file'] == "/tmp/client_certificate.crt"
                assert data['key_file'] == "/tmp/client_key.key"
    
    def test_json_input_with_extra_data(self):
        """Test creating JSON input with extra data"""
        with patch('common.file.open', create=True) as mock_open:
            mock_file = mock_open.return_value.__enter__.return_value
            
            extra_data = {
                'namespace': 'default',
                'pod_name': 'test-pod'
            }
            
            create_json_input("https://k8s.example.com", extra_data)
            
            # Get the JSON that was written
            written_data = ''.join(call.args[0] for call in mock_file.write.call_args_list)
            data = json.loads(written_data)
            
            assert data['namespace'] == 'default'
            assert data['pod_name'] == 'test-pod'
    
    def test_json_input_filters_metadata_keys(self):
        """Test that metadata keys (starting with $) are filtered out"""
        with patch('common.file.open', create=True) as mock_open:
            mock_file = mock_open.return_value.__enter__.return_value
            
            extra_data = {
                '$instruction': 'Do something',
                '$endpoint': 'https://k8s.example.com',
                '$client_certificate': 'cert-data',
                '$client_key': 'key-data',
                '$email': 'user@example.com',
                'namespace': 'default',  # This should be kept
                'pod_name': 'test-pod'   # This should be kept
            }
            
            create_json_input("https://k8s.example.com", extra_data)
            
            # Get the JSON that was written
            written_data = ''.join(call.args[0] for call in mock_file.write.call_args_list)
            data = json.loads(written_data)
            
            # Metadata keys should be removed
            assert '$instruction' not in data
            assert '$endpoint' not in data
            assert '$client_certificate' not in data
            assert '$client_key' not in data
            assert '$email' not in data
            
            # Regular keys should be kept
            assert data['namespace'] == 'default'
            assert data['pod_name'] == 'test-pod'
            assert data['host'] == "https://k8s.example.com"
    
    def test_json_input_with_no_metadata_keys(self):
        """Test that function works when no metadata keys are present"""
        with patch('common.file.open', create=True) as mock_open:
            mock_file = mock_open.return_value.__enter__.return_value
            
            extra_data = {
                'namespace': 'default',
                'pod_name': 'test-pod'
            }
            
            # Should not raise any errors
            create_json_input("https://k8s.example.com", extra_data)
            
            # Get the JSON that was written
            written_data = ''.join(call.args[0] for call in mock_file.write.call_args_list)
            data = json.loads(written_data)
            
            assert data['namespace'] == 'default'
            assert data['pod_name'] == 'test-pod'


class TestWriteUserFiles:
    """Test write_user_files function"""
    
    def test_write_user_files(self):
        """Test writing certificate and key files"""
        with patch('builtins.open', create=True) as mock_open:
            cert_data = "CERTIFICATE DATA"
            key_data = "KEY DATA"
            
            write_user_files(cert_data, key_data)
            
            # Verify both files were opened
            assert mock_open.call_count == 2
            
            # Check certificate file
            calls = mock_open.call_args_list
            assert calls[0][0][0] == "/tmp/client_certificate.crt"
            assert calls[0][0][1] == "w"
            
            # Check key file
            assert calls[1][0][0] == "/tmp/client_key.key"
            assert calls[1][0][1] == "w"
