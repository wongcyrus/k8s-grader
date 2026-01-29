"""Tests for PhaseConfig model"""
import pytest
from common.models.phase_config import PhaseConfig


class TestPhaseConfig:
    """Test PhaseConfig model"""
    
    def test_create_phase_config(self, sample_phase_config):
        """Test creating a PhaseConfig instance"""
        assert sample_phase_config.id == "setup"
        assert sample_phase_config.name == "Setup"
        assert sample_phase_config.required is True
        assert sample_phase_config.auto_run is False
        assert sample_phase_config.timeout_seconds == 30
        assert sample_phase_config.max_attempts == 3
        assert sample_phase_config.points == 0
    
    def test_from_dict(self):
        """Test creating PhaseConfig from dictionary"""
        data = {
            'id': 'challenge',
            'name': 'Challenge',
            'description': 'Complete the challenge',
            'test_file': 'test_04_challenge.py',
            'required': True,
            'auto_run': False,
            'timeout_seconds': 60,
            'max_attempts': 5,
            'points': 100
        }
        
        phase = PhaseConfig.from_dict(data)
        
        assert phase.id == 'challenge'
        assert phase.name == 'Challenge'
        assert phase.timeout_seconds == 60
        assert phase.max_attempts == 5
        assert phase.points == 100
    
    def test_from_dict_with_defaults(self):
        """Test creating PhaseConfig with default values"""
        data = {
            'id': 'test',
            'name': 'Test',
            'description': 'Test phase',
            'test_file': 'test.py'
        }
        
        phase = PhaseConfig.from_dict(data)
        
        assert phase.required is True
        assert phase.auto_run is False
        assert phase.timeout_seconds == 30
        assert phase.max_attempts == 3
        assert phase.points == 0
    
    def test_to_dict(self, sample_phase_config):
        """Test converting PhaseConfig to dictionary"""
        data = sample_phase_config.to_dict()
        
        assert data['id'] == 'setup'
        assert data['name'] == 'Setup'
        assert data['required'] is True
        assert data['auto_run'] is False
        assert data['timeout_seconds'] == 30
        assert data['max_attempts'] == 3
        assert data['points'] == 0
    
    def test_round_trip_conversion(self, sample_phase_config):
        """Test converting to dict and back"""
        data = sample_phase_config.to_dict()
        phase = PhaseConfig.from_dict(data)
        
        assert phase.id == sample_phase_config.id
        assert phase.name == sample_phase_config.name
        assert phase.required == sample_phase_config.required
        assert phase.timeout_seconds == sample_phase_config.timeout_seconds
