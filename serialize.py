import numpy as np
import base64


def numpy_to_buffer_json(value):
    def walk(obj):
        if isinstance(obj, np.ndarray):
            if not obj.flags["C_CONTIGUOUS"]:
                obj = np.ascontiguousarray(obj)

            obj = obj.ravel()
            return {
                "shape": obj.shape,
                "dtype": str(obj.dtype),
                "buffer": base64.b64encode(memoryview(obj)).decode(),
                "codec": "b64",
            }
        elif isinstance(obj, (tuple, list)):
            return [walk(el) for el in obj]
        elif isinstance(obj, dict):
            rv = {}
            for k, v in obj.items():
                rv[k] = walk(v)
            return rv
        else:
            return obj

    return walk(value)
