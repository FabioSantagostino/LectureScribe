import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scribelane_openvino import model_directory, MODEL_MAP, device_list
import scribelane_openvino as backend


class OpenVINOTests(unittest.TestCase):
    def test_matching_model_paths(self):
        root = Path('models')
        self.assertEqual(model_directory(root, 'turbo'), root / 'whisper-large-v3-turbo')
        self.assertEqual(model_directory(root, 'large-v3'), root / 'whisper-large-v3')

    def test_device_discovery_no_crash(self):
        self.assertIsInstance(device_list(), list)

    def test_npu_cache_exhaustion_retries_on_gpu(self):
        npu, gpu = object(), object()
        result = [(0, 1, "lecture")]
        phases = []
        with (patch.object(backend, "device_list", return_value=["NPU", "GPU"]),
              patch.object(backend, "resolve_model", return_value=Path("model")),
              patch.object(backend, "convert_audio"),
              patch.object(backend, "read_audio", return_value=[0.0]),
              patch.object(backend, "choose_device", return_value=("NPU", npu)),
              patch.object(backend, "make_pipe", return_value=gpu) as make,
              patch.object(backend, "transcribe_on_device",
                           side_effect=[backend.OpenVINOUnavailable("NPU_KV_CACHE"), result]) as transcribe):
            self.assertEqual(
                backend.transcribe_if_available(Path("audio.wav"), "small", "it", Path("models"),
                                                Path("bench"), on_status=phases.append),
                (result, "GPU"),
            )
        make.assert_called_once_with(Path("model"), "GPU")
        self.assertEqual(transcribe.call_args.args[2:4], (gpu, "GPU"))
        self.assertIn("ov_retry_gpu", phases)

    def test_queue_skips_npu_in_automatic_language_mode(self):
        with patch.object(backend, "device_list") as discover:
            self.assertIsNone(backend.prepare_parallel([], "small", None, Path("models"),
                                                       lambda: False, lambda _: None))
        discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
