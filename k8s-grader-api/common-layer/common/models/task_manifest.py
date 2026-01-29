"""Task manifest model"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import json
import os
from .phase_config import PhaseConfig


@dataclass
class TaskManifest:
    """Complete task configuration"""
    task_id: str
    title: str
    description: str
    difficulty: str                  # beginner, intermediate, advanced
    estimated_minutes: int
    phases: List[PhaseConfig]
    prerequisites: List[str]         # Other task IDs required first
    tags: List[str]
    hints: List[str]                 # Optional hints
    
    @classmethod
    def load(cls, game: str, task_id: str) -> 'TaskManifest':
        """Load manifest from task directory"""
        path = f"/tmp/{game}/tests/{game}/{task_id}/manifest.json"
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Manifest not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskManifest':
        """Create TaskManifest from dictionary"""
        return cls(
            task_id=data['task_id'],
            title=data['title'],
            description=data['description'],
            difficulty=data['difficulty'],
            estimated_minutes=data['estimated_minutes'],
            phases=[PhaseConfig.from_dict(p) for p in data['phases']],
            prerequisites=data.get('prerequisites', []),
            tags=data.get('tags', []),
            hints=data.get('hints', [])
        )
    
    def get_phase(self, phase_id: str) -> Optional[PhaseConfig]:
        """Get phase configuration by ID"""
        return next((p for p in self.phases if p.id == phase_id), None)
    
    def get_next_phase(self, current_phase_id: str) -> Optional[PhaseConfig]:
        """Get next required phase after current"""
        try:
            current_idx = next(i for i, p in enumerate(self.phases) 
                             if p.id == current_phase_id)
            # Find next required phase that's not auto-run
            for phase in self.phases[current_idx + 1:]:
                if phase.required and not phase.auto_run:
                    return phase
            return None
        except StopIteration:
            return None
    
    def get_first_phase(self) -> PhaseConfig:
        """Get the first phase"""
        return self.phases[0]
    
    def get_total_points(self) -> int:
        """Calculate total points available"""
        return sum(p.points for p in self.phases if p.required)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'task_id': self.task_id,
            'title': self.title,
            'description': self.description,
            'difficulty': self.difficulty,
            'estimated_minutes': self.estimated_minutes,
            'phases': [p.to_dict() for p in self.phases],
            'prerequisites': self.prerequisites,
            'tags': self.tags,
            'hints': self.hints
        }
