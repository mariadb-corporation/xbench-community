from ..exceptions import CloudException


class ColoCloudEx(CloudException):
    pass


class ColoCloudHostLockedEx(ColoCloudEx):
    pass


class ColoCloudProvisioningEx(ColoCloudEx):
    pass
