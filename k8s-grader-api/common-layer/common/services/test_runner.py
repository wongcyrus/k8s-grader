"""Test runner service for executing phase tests"""
from typing import Tuple, Dict, Any
from datetime import datetime, timezone
import logging
import os

from common.models.phase_config import PhaseConfig
from common.status import TestResult

logger = logging.getLogger(__name__)


class TestRunner:
    """Handles test execution and result management"""
    
    def run_phase(self, game: str, task_id: str, phase: PhaseConfig,
                  session_data: Dict[str, Any]) -> Tuple[TestResult, str]:
        """
        Run tests for a phase and return result + report URL
        
        Args:
            game: Game identifier
            task_id: Task identifier
            phase: Phase configuration
            session_data: Session data including K8s credentials
            
        Returns:
            Tuple of (TestResult, report_url)
        """
        try:
            # Prepare test environment
            endpoint = session_data.get('$endpoint')
            if not endpoint:
                logger.error("No endpoint in session data")
                return TestResult.USAGE_ERROR, ""
            
            # Import here to avoid circular dependencies
            from common.file import create_json_input
            from common.pytest import run_tests
            
            # Create input file for tests
            create_json_input(endpoint, session_data)
            
            # Run tests with timeout
            test_result = run_tests(
                phase.id, 
                game, 
                task_id,
                timeout=phase.timeout_seconds
            )
            
            # Only upload report to S3 if tests failed
            # Players don't need to see successful test reports
            report_url = ""
            if test_result != TestResult.OK:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
                report_url = self._upload_report(
                    game, task_id, phase.id, timestamp, session_data.get('$email', 'unknown')
                )
                if report_url:
                    logger.info(f"Phase {phase.id} failed: {test_result.name}, report uploaded")
                else:
                    logger.warning(f"Phase {phase.id} failed: {test_result.name}, report upload failed")
            else:
                logger.info(f"Phase {phase.id} passed: {test_result.name}")
            
            return test_result, report_url
            
        except FileNotFoundError as e:
            logger.error(f"Test file not found: {e}")
            return TestResult.NO_TESTS_COLLECTED, ""
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return TestResult.INTERNAL_ERROR, ""
    
    def _upload_report(self, game: str, task_id: str, phase_id: str,
                      timestamp: str, email: str) -> str:
        """
        Upload test report to S3 and return presigned URL
        
        Args:
            game: Game identifier
            task_id: Task identifier
            phase_id: Phase identifier
            timestamp: Timestamp string
            email: User email
            
        Returns:
            Presigned URL to report
        """
        try:
            from common.s3 import upload_test_result, generate_presigned_url
            
            upload_test_result(
                "/tmp/report.html",
                phase_id,
                timestamp,
                email,
                game,
                task_id
            )
            
            return generate_presigned_url(
                phase_id,
                timestamp,
                email,
                game,
                task_id
            )
        except Exception as e:
            logger.error(f"Failed to upload report: {e}")
            return ""
