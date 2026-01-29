"""Task state models"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class TaskStatus(Enum):
    """Task status enumeration"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PhaseStatus(Enum):
    """Phase status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


@dataclass
class PhaseState:
    """State of a single phase"""
    phase_id: str
    status: PhaseStatus
    attempts: int = 0
    passed_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    test_result: Optional[str] = None
    report_url: Optional[str] = None
    points_earned: int = 0
    
    def mark_passed(self, report_url: str, points: int):
        """Mark phase as passed"""
        self.status = PhaseStatus.PASSED
        self.test_result = "OK"
        self.report_url = report_url
        self.points_earned = points
        self.passed_at = datetime.now(timezone.utc).isoformat()
        self.last_attempt_at = self.passed_at
    
    def mark_failed(self, test_result: str, report_url: str):
        """Mark phase as failed"""
        self.status = PhaseStatus.FAILED
        self.attempts += 1
        self.test_result = test_result
        self.report_url = report_url
        self.last_attempt_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'phase_id': self.phase_id,
            'status': self.status.value,
            'attempts': self.attempts,
            'passed_at': self.passed_at,
            'last_attempt_at': self.last_attempt_at,
            'test_result': self.test_result,
            'report_url': self.report_url,
            'points_earned': self.points_earned
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhaseState':
        """Create PhaseState from dictionary"""
        return cls(
            phase_id=data['phase_id'],
            status=PhaseStatus(data['status']),
            attempts=data.get('attempts', 0),
            passed_at=data.get('passed_at'),
            last_attempt_at=data.get('last_attempt_at'),
            test_result=data.get('test_result'),
            report_url=data.get('report_url'),
            points_earned=data.get('points_earned', 0)
        )


@dataclass
class TaskState:
    """Complete state of a user's task"""
    email: str
    game: str
    task_id: str
    npc: str
    status: TaskStatus
    current_phase_id: Optional[str]
    phase_states: Dict[str, PhaseState] = field(default_factory=dict)
    session_data: Dict[str, Any] = field(default_factory=dict)
    total_points: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    
    @property
    def pk(self) -> str:
        """Partition key"""
        return self.email
    
    @property
    def sk(self) -> str:
        """Sort key"""
        return f"{self.game}#{self.task_id}"
    
    def get_phase_state(self, phase_id: str) -> Optional[PhaseState]:
        """Get phase state by ID"""
        return self.phase_states.get(phase_id)
    
    def get_or_create_phase_state(self, phase_id: str) -> PhaseState:
        """Get or create phase state"""
        if phase_id not in self.phase_states:
            self.phase_states[phase_id] = PhaseState(phase_id, PhaseStatus.PENDING)
        return self.phase_states[phase_id]
    
    def calculate_progress(self, manifest: 'TaskManifest') -> float:
        """Calculate completion percentage (0.0 to 1.0)"""
        from .task_manifest import TaskManifest
        
        required_phases = [p for p in manifest.phases 
                          if p.required and not p.auto_run]
        if not required_phases:
            return 1.0
        
        passed = sum(1 for p in required_phases
                    if self.phase_states.get(p.id) and 
                    self.phase_states[p.id].status == PhaseStatus.PASSED)
        return passed / len(required_phases)
    
    def mark_completed(self):
        """Mark task as completed"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.completed_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DynamoDB"""
        return {
            'email': self.email,
            'gameTask': self.sk,
            'game': self.game,
            'task_id': self.task_id,
            'npc': self.npc,
            'status': self.status.value,
            'current_phase_id': self.current_phase_id,
            'phase_states': {k: v.to_dict() for k, v in self.phase_states.items()},
            'session_data': self.session_data,
            'total_points': self.total_points,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'completed_at': self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskState':
        """Create TaskState from dictionary"""
        return cls(
            email=data['email'],
            game=data['game'],
            task_id=data['task_id'],
            npc=data['npc'],
            status=TaskStatus(data['status']),
            current_phase_id=data.get('current_phase_id'),
            phase_states={
                k: PhaseState.from_dict(v) 
                for k, v in data.get('phase_states', {}).items()
            },
            session_data=data.get('session_data', {}),
            total_points=data.get('total_points', 0),
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            completed_at=data.get('completed_at')
        )
