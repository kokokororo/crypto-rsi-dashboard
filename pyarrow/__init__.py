# Mock PyArrow for 32-bit Windows compatibility
__version__ = "10.0.0"

class Table:
    @staticmethod
    def from_pandas(*args, **kwargs):
        raise NotImplementedError("Mock PyArrow Table.from_pandas is not implemented.")

class RecordBatch:
    pass

class Array:
    pass

class ChunkedArray:
    pass

class DataType:
    pass

class Schema:
    pass

def int64():
    return None

def string():
    return None

def float64():
    return None

class lib:
    class ArrowInvalid(Exception):
        pass
    class ArrowTypeError(Exception):
        pass

ArrowInvalid = lib.ArrowInvalid
ArrowTypeError = lib.ArrowTypeError
