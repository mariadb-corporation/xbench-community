class SkySQLBackendException(Exception):
    """base exception class"""


class SkySQLBackendDBException(SkySQLBackendException):
    """database related errors"""
