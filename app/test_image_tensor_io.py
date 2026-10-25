import json
from pathlib import Path
import struct
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
except ImportError:
    raise unittest.SkipTest('Run image tensor tests using either installed image engine Python.')
from image_tensor_io import StreamSafeOpen


class TensorStreamTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.safetensors'

    def test_matches_native_values_shapes_dtypes_metadata_and_preserves_file(self):
        values={'float':torch.arange(24,dtype=torch.float32).reshape(2,3,4),
                'half':torch.arange(7,dtype=torch.float16),'bf':torch.ones(3,dtype=torch.bfloat16),
                'int':torch.tensor([-1,3],dtype=torch.int64),'bool':torch.tensor([True,False]),
                'empty':torch.empty((0,3),dtype=torch.float32),'scalar':torch.tensor(4.)}
        save_file(values,str(self.path),metadata={'source':'test'})
        original=self.path.read_bytes()
        with safe_open(str(self.path),framework='pt') as native, StreamSafeOpen(self.path) as streamed:
            self.assertEqual(set(native.keys()),set(streamed.keys()))
            self.assertEqual(native.metadata(),streamed.metadata())
            for key in values:
                actual=streamed.get_tensor(key)
                self.assertEqual(actual.dtype,native.get_tensor(key).dtype)
                self.assertTrue(torch.equal(actual,native.get_tensor(key)))
                if actual.numel():actual.fill_(0)
        self.assertEqual(original,self.path.read_bytes())

    def test_rejects_truncation_before_allocating_tensor(self):
        save_file({'a':torch.ones(8)},str(self.path))
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,'truncated'):StreamSafeOpen(self.path)

    def test_slice_metadata_and_indexing_match_safetensors_interface(self):
        value=torch.arange(24,dtype=torch.float16).reshape(2,3,4)
        save_file({'a':value},str(self.path))
        with StreamSafeOpen(self.path) as reader:
            sliced=reader.get_slice('a')
            self.assertEqual(sliced.get_shape(),[2,3,4]);self.assertEqual(sliced.get_dtype(),'F16')
            self.assertTrue(torch.equal(sliced[0,:,1:3],value[0,:,1:3]))
            self.assertEqual(reader.offset_keys(),['a'])

    def test_rejects_overlapping_tensor_ranges(self):
        header=json.dumps({'a':{'dtype':'F32','shape':[2],'data_offsets':[0,8]},'b':{'dtype':'F32','shape':[2],'data_offsets':[4,12]}}).encode()
        self.path.write_bytes(struct.pack('<Q',len(header))+header+b'\0'*12)
        with self.assertRaisesRegex(ValueError,'overlapping'):StreamSafeOpen(self.path)

    def test_rejects_wrong_shape_byte_count(self):
        header=json.dumps({'a':{'dtype':'F32','shape':[3],'data_offsets':[0,8]}}).encode()
        self.path.write_bytes(struct.pack('<Q',len(header))+header+b'\0'*8)
        with StreamSafeOpen(self.path) as reader:
            with self.assertRaisesRegex(ValueError,'byte_count'):reader.get_tensor('a')


if __name__=='__main__':unittest.main()
