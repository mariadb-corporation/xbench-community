class SigTermException(Exception):
    """SIGTERM signal"""
    
class RetryException(Exception):
    """General Retry error has occurred """

    def __init__(self, err_message=None):
        self.err_message = err_message

    def __str__(self):
        return "{err_message}".format(err_message=self.err_message)
  