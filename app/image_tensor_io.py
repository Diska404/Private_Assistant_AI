"""Read safetensors a tensor at a time, avoiding Windows private whole-file mapping.

Opt-in for owned image workers. Never deserializes pickle or writes checkpoint files.
"""
import json
import math
from pathlib import Path
import struct


class StreamSafeOpen:
    def __init__(self, filename, framework='pt', device='cpu'):
        if framework not in ('pt', 'pytorch') or str(device) not in ('cpu', 'None'):
            raise ValueError('stream_reader_cpu_pytorch_only')
        self.path = Path(filename)
        self.stream = self.path.open('rb')
        try:
            raw = self.stream.read(8)
            if len(raw) != 8: raise ValueError('safetensors_missing_header')
            size = struct.unpack('<Q', raw)[0]
            if not 2 <= size <= 16_000_000: raise ValueError('safetensors_header_size')
            self.header = json.loads(self.stream.read(size))
            if not isinstance(self.header, dict): raise ValueError('safetensors_header_type')
            self.offset = 8 + size
            available = self.path.stat().st_size - self.offset
            intervals = []
            for name, item in self.header.items():
                if name == '__metadata__': continue
                if not isinstance(item, dict): raise ValueError('safetensors_tensor_descriptor')
                shape = item.get('shape')
                offsets = item.get('data_offsets')
                if not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
                    raise ValueError('safetensors_tensor_shape')
                if not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets):
                    raise ValueError('safetensors_tensor_offsets')
                start, end = offsets
                if not 0 <= start <= end <= available: raise ValueError('safetensors_truncated_or_invalid_offsets')
                intervals.append((start, end))
            previous = 0
            for start, end in sorted(intervals):
                if start != previous: raise ValueError('safetensors_overlapping_or_gapped_data')
                previous = end
            if previous != available: raise ValueError('safetensors_unindexed_data')
        except BaseException:
            self.stream.close()
            raise

    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def keys(self): return [key for key in self.header if key != '__metadata__']
    def metadata(self): return self.header.get('__metadata__')
    def offset_keys(self): return sorted(self.keys(),key=lambda name:self.header[name]['data_offsets'][0])
    def get_slice(self, name):
        reader=self
        descriptor=self.header[name]
        class TensorSlice:
            def get_shape(self):return list(descriptor['shape'])
            def get_dtype(self):return descriptor['dtype']
            def __getitem__(self, item):return reader.get_tensor(name)[item]
        return TensorSlice()

    def get_tensor(self, name):
        import torch
        item = self.header[name]
        types = {'F64': 'float64', 'F32': 'float32', 'F16': 'float16', 'BF16': 'bfloat16',
                 'I64': 'int64', 'I32': 'int32', 'I16': 'int16', 'I8': 'int8', 'U8': 'uint8', 'BOOL': 'bool',
                 'F8_E4M3': 'float8_e4m3fn', 'F8_E5M2': 'float8_e5m2', 'U16': 'uint16', 'U32': 'uint32', 'U64': 'uint64'}
        attr = types.get(item['dtype'])
        if not attr or not hasattr(torch, attr): raise ValueError('safetensors_unsupported_dtype:' + item['dtype'])
        dtype = getattr(torch, attr)
        start, end = item['data_offsets']
        count = math.prod(item['shape'])
        if count * torch.empty((), dtype=dtype).element_size() != end - start:
            raise ValueError('safetensors_tensor_byte_count')
        if count == 0: return torch.empty(item['shape'], dtype=dtype)
        data = bytearray(end - start)
        self.stream.seek(self.offset + start)
        view = memoryview(data)
        while view:
            read = self.stream.readinto(view)
            if not read: raise ValueError('safetensors_truncated_tensor')
            view = view[read:]
        return torch.frombuffer(data, dtype=dtype, count=count).reshape(item['shape'])


def install_stream_reader():
    import safetensors
    import sys
    original = safetensors.safe_open

    def open_owned(filename, framework='pt', device='cpu', *args, **kwargs):
        if str(device) in ('cpu', 'None') and framework in ('pt', 'pytorch') and not args and not kwargs:
            return StreamSafeOpen(filename, framework, device)
        return original(filename, framework=framework, device=device, *args, **kwargs)

    safetensors.safe_open = open_owned
    # Do not import torch before ComfyUI configures its CUDA allocator/environment.
    loaded = sys.modules.get('safetensors.torch')
    if loaded is not None: loaded.safe_open = open_owned
