# How to use @property http://xion.io/post/code/python-enums-are-ok.html

from enum import Enum
class VirtualMachineState(Enum):
    aws_pending = "pending"
    aws_running = "running"
    aws_shutting_down = "shutting-down"
    aws_terminated = "terminated"
    aws_stopping = "stopping"
    aws_stopped = "stopped"

    @property
    def is_running(self):
        return self in (VirtualMachineState.aws_running)