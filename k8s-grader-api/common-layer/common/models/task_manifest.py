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
        """
        Load manifest from task directory.
        If manifest.json doesn't exist, auto-generate from test files.
        """
        # Ensure game tests are present under /tmp before loading manifest.
        # This prevents /exam/start from failing on cold containers where
        # TaskManifest is loaded before any pytest-driven download path runs.
        from common.pytest import get_tests
        get_tests(game)

        path = f"/tmp/{game}/tests/{game}/{task_id}/manifest.json"
        
        if os.path.exists(path):
            # Load from manifest.json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        else:
            # Auto-generate from test files
            return cls._auto_generate(game, task_id)
    
    @classmethod
    def _auto_generate(cls, game: str, task_id: str) -> 'TaskManifest':
        """
        Auto-generate manifest by discovering test files.
        Provides backward compatibility with old system.
        Requires instruction.md file to be present.
        """
        task_dir = f"/tmp/{game}/tests/{game}/{task_id}"
        
        # Read instruction.md - this is REQUIRED
        instruction_path = os.path.join(task_dir, 'instruction.md')
        if not os.path.exists(instruction_path):
            raise FileNotFoundError(
                f"instruction.md is required but not found in {task_dir}. "
                "Every task must have an instruction.md file with the game instructions."
            )
        
        try:
            with open(instruction_path, 'r', encoding='utf-8') as f:
                task_instruction = f.read().strip()
        except Exception as e:
            raise ValueError(f"Failed to read instruction.md in {task_dir}: {e}")
        
        if not task_instruction:
            raise ValueError(f"instruction.md in {task_dir} is empty. Please provide game instructions.")
        
        # Discover test files with descriptions
        # Answer phase: Show instruction (player needs to know what to do)
        # Check phase: Also show instruction (so player knows what failed)
        phase_mapping = {
            'test_01_setup.py': ('setup', 'Setup', 'Initialize the task environment', 0),
            'test_02_ready.py': ('ready', 'Ready', 'Verify prerequisites are met', 5),
            'test_03_answer.py': ('answer', 'Answer', task_instruction, 10),
            'test_04_challenge.py': ('challenge', 'Challenge', task_instruction, 15),
            'test_05_check.py': ('check', 'Check', task_instruction, 20),
            'test_06_cleanup.py': ('cleanup', 'Cleanup', 'Clean up resources', 0),
        }
        
        phases = []
        for test_file, (phase_id, phase_name, description, points) in phase_mapping.items():
            test_path = os.path.join(task_dir, test_file)
            if os.path.exists(test_path):
                phases.append(PhaseConfig(
                    id=phase_id,
                    name=phase_name,
                    description=description,
                    test_file=test_file,
                    required=(phase_id != 'cleanup'),
                    auto_run=(phase_id == 'cleanup'),
                    timeout_seconds=30,
                    max_attempts=3,
                    points=points
                ))
        
        if not phases:
            raise FileNotFoundError(f"No test files found in {task_dir}")
        
        # Generate basic metadata
        title = task_id.replace('_', ' ').title()
        
        return cls(
            task_id=task_id,
            title=title,
            description=task_instruction,
            difficulty='beginner',
            estimated_minutes=15,
            phases=phases,
            prerequisites=[],
            tags=['auto-generated'],
            hints=[]
        )
    
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
