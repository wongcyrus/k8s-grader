"""Student-facing stages for the exam-only task lifecycle."""


AUTO_CHAIN_EXAM_PHASES = {"setup": "ready", "challenge": "check"}


def lifecycle_payload(state=None, *, phase=None, running=False):
    status = getattr(getattr(state, "status", None), "value", "")
    phase = phase or getattr(state, "current_phase_id", None)
    if status in ("completed", "abandoned"):
        return {
            "stage": status,
            "label": "Finished" if status == "completed" else "Attempts exhausted",
            "message": "Cleanup finished. You may choose another question.",
            "phase": None,
        }
    if not state and not running:
        return {
            "stage": "not_started",
            "label": "Not started",
            "message": "Start question to prepare your environment.",
            "phase": None,
        }
    phase_state = getattr(state, "phase_states", {}).get(phase)
    failed = getattr(getattr(phase_state, "status", None), "value", "") == "failed"
    if phase in ("setup", "ready", "start"):
        label = "Preparing environment" if running else "Preparation needed"
        message = {
            "setup": "Creating the question's Kubernetes resources.",
            "ready": "Checking that the environment is ready.",
            "start": "Preparing the question.",
        }[phase]
        if not running:
            message = (
                "Preparation failed. Retry preparation before working on the question."
                if failed
                else "Prepare the environment before working on the question."
            )
        return {
            "stage": "preparation",
            "label": label,
            "phase": phase,
            "message": message,
            "run_label": "Retry preparation" if failed else "Prepare environment",
        }
    if phase in ("cleanup", "reset"):
        return {
            "stage": "cleanup",
            "label": "Cleaning up" if running else "Cleanup needs attention",
            "phase": "cleanup",
            "message": "Removing the question's Kubernetes resources. Do not start another question."
            if running
            else "Cleanup did not finish. Retry cleanup before continuing.",
            "run_label": "Retry cleanup",
        }
    if running:
        return {
            "stage": "assessment",
            "label": "Assessing your work",
            "phase": phase,
            "message": "Running the challenge against your work."
            if phase == "challenge"
            else "Checking your answer.",
        }
    return {
        "stage": "working",
        "label": "Your turn",
        "phase": phase,
        "message": "The last assessment did not pass. Update your Kubernetes work, then submit again."
        if failed
        else "The environment is ready. Complete the question, then submit your answer.",
        "run_label": "Submit answer",
    }
