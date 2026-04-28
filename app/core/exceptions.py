class DriveAuthRequiredException(Exception):

    def __init__(self, message: str, drive_auth_url: str = ""):
        self.message = message
        self.drive_auth_url = drive_auth_url
        super().__init__(self.message)
