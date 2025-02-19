from datetime import datetime

class DateValidator:
    @staticmethod
    def validate_iso_date(date_str: str) -> bool:
        try:
            datetime.fromisoformat(date_str)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_date_range(start: str, end: str) -> bool:
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            return start_dt <= end_dt
        except ValueError:
            return False
