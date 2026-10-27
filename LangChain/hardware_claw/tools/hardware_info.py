"""First read-only capability. Teaching fixture, separate from purchased hardware."""
from langchain.tools import tool


@tool
def get_board_info(board_id: str) -> dict:
    """Query the project's supported board profile by ID; use esp32-s3-demo.

    This is a teaching profile, not verified electrical or pinout data.
    Unknown IDs return not_found rather than fabricated specifications.
    """
    if board_id != "esp32-s3-demo":
        return {"status": "not_found", "supported_ids": ["esp32-s3-demo"]}
    return {
        "status": "ok",
        "board_id": board_id,
        "family": "ESP32-S3",
        "profile_kind": "teaching_fixture",
        "verified_for_wiring": False,
        "exact_board_model": None,
        "constraints": [
            "Confirm the exact board revision and module before assigning pins.",
            "Flash/PSRAM capacity and exposed pins are not specified in this profile.",
            "Do not infer safe wiring or voltage compatibility from this fixture.",
        ],
    }
