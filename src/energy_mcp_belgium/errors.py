class EnergyError(Exception):
    """An expected, safe-to-display request or provider failure."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")
