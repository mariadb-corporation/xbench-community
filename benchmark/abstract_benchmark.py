from abc import ABCMeta, abstractmethod


class AbstractBenchmarkRunner(metaclass=ABCMeta):
    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def prepare(self):
        pass

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def data_check(self):
        pass

    # Only overridden in benchbase_runner for now
    def setup(self):
        pass
