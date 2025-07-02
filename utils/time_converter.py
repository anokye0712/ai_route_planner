import datetime
from typing import List, Tuple

def convert_to_seconds_from_midnight(time_str: str) -> int:
    """
    Converts a time string (e.g., "8 AM", "5 PM") to seconds from midnight (00:00:00).
    Assumes times are in a 12-hour or 24-hour format that can be parsed by datetime.strptime.
    """
    # This is a placeholder. Dify.ai *should* ideally provide seconds directly.
    # If Dify.ai outputs human-readable strings, you'll need robust parsing here.
    # For now, let's assume Dify.ai *can* output seconds or a consistent format.
    # If Dify.ai gives "8 AM to 5 PM" as separate strings, this function helps.
    # However, the prompt implies Dify.ai converts to [[start_seconds, end_seconds]] directly.
    # So, this function might be more useful if Dify.ai provides specific single time points.

    # Example for parsing "8 AM", "1 PM"
    try:
        dt_object = datetime.datetime.strptime(time_str, "%I %p") # For "8 AM", "1 PM"
    except ValueError:
        try:
            dt_object = datetime.datetime.strptime(time_str, "%H:%M") # For "13:00"
        except ValueError:
            raise ValueError(f"Could not parse time string: {time_str}. Expected 'HH:MM' or 'H AM/PM'.")

    return dt_object.hour * 3600 + dt_object.minute * 60 + dt_object.second

def convert_time_windows_to_seconds(time_windows_dify: List[List[int]]) -> List[List[int]]:
    """
    Ensures time windows are in seconds. Dify.ai is expected to already do this.
    This function acts as a safeguard/identity function if Dify.ai directly provides seconds.
    If Dify.ai provides different formats (e.g., HH:MM strings), this function would
    be extended to parse them.
    """
    # Dify.ai's expected output already specifies seconds, so this is mostly an identity check.
    # However, if it were to output "8 AM", "5 PM" for a window, this is where you'd convert.
    # As per prompt: time_windows: Array of [start_seconds, end_seconds] pairs.
    # So, we expect it to be correct already.
    # Example: [[0, 32400]] is already seconds from midnight.
    validated_windows = []
    for window in time_windows_dify:
        if len(window) == 2 and all(isinstance(t, int) for t in window):
            validated_windows.append(window)
        else:
            # This indicates an issue with Dify.ai's output if it's not [int, int]
            raise ValueError(f"Invalid time window format from Dify.ai: {window}. Expected [int, int].")
    return validated_windows