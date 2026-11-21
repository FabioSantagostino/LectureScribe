import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lecturescribe_openvino import model_directory, MODEL_MAP, device_list


class OpenVINOTests(unittest.TestCase):
    def test_matching_model_paths(self):
        root = Path('models')
        self.assertEqual(model_directory(root, 'turbo'), root / 'whisper-large-v3-turbo')
        self.assertEqual(model_directory(root, 'large-v3'), root / 'whisper-large-v3')

    def test_device_discovery_no_crash(self):
        self.assertIsInstance(device_list(), list)


if __name__ == '__main__':
    unittest.main()
