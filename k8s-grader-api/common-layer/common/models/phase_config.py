"""Phase configuration model"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PhaseConfig:
    """Configuration for a single task phase"""
    id: str                          # setup, challenge, check, cleanup
    name: str                        # Display name
    description: str                 # What this phase does
    test_file: str                   # test_01_setup.py
    required: bool = True            # Must pass to continue
    auto_run: bool = False           # Run automatically (cleanup)
    timeout_seconds: int = 30        # Test timeout
    max_attempts: int = 3            # Retry limit
    points: int = 0                  # Gamification
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhaseConfig':
        """Create PhaseConfig from dictionary"""
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            test_file=data['test_file'],
            required=data.get('required', True),
            auto_run=data.get('auto_run', False),
            timeout_seconds=data.get('timeout_seconds', 30),
            max_attempts=data.get('max_attempts', 3),
            points=data.get('points', 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'test_file': self.test_file,
            'required': self.required,
            'auto_run': self.auto_run,
            'timeout_seconds': self.timeout_seconds,
            'max_attempts': self.max_attempts,
            'points': self.points
        }
