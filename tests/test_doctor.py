import unittest

from agent_vm.doctor import _has_models, _kandev_pi_capabilities


class DoctorTests(unittest.TestCase):
    def test_model_catalog_must_be_nonempty(self):
        self.assertTrue(_has_models('{"data": [{"id": "gpt-test"}]}'))
        self.assertFalse(_has_models('{"data": []}'))
        self.assertFalse(_has_models('{"status": "ok"}'))
        self.assertFalse(_has_models('not json'))

    def test_kandev_pi_capabilities_require_ok_with_models(self):
        ready, detail = _kandev_pi_capabilities(
            '{"status":"ok","models":[{"id":"gpt-test"}]}'
        )
        self.assertTrue(ready)
        self.assertIn("1 model", detail)

        for response in (
            '{"status":"failed","error":"ACP initialize failed"}',
            '{"status":"ok","models":[]}',
            'not json',
        ):
            with self.subTest(response=response):
                self.assertFalse(_kandev_pi_capabilities(response)[0])


if __name__ == "__main__":
    unittest.main()
