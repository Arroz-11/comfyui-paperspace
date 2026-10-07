"""Exercise real ipywidgets callbacks with downloads mocked; no network or GPU."""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('paperspace_hub', ROOT / 'scripts/hub.py')
hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hub)

PRESETS = {
    'first': {
        'name': 'First model', 'about': '',
        'components': {
            'diffusion': {'folder': 'diffusion_models', 'options': [
                {'label': 'base', 'repo': 'test/first', 'file': 'base.safetensors', 'gb': 2},
                {'label': 'quant', 'repo': 'test/first', 'file': 'quant.safetensors', 'gb': 1},
            ]},
            'vae': {'folder': 'vae', 'options': [
                {'label': 'shared', 'repo': 'test/shared', 'file': 'shared.safetensors', 'gb': 0.5},
            ]},
            'extras': {'folder': 'loras', 'optional': True, 'multi': True, 'options': [
                {'label': 'a', 'repo': 'test/extras', 'file': 'a.safetensors', 'gb': 0.1},
                {'label': 'b', 'repo': 'test/extras', 'file': 'b.safetensors', 'gb': 0.2},
            ]},
        },
    },
    'second': {'name': 'Second model', 'components': {
        'vae': {'folder': 'vae', 'options': [
            {'label': 'shared', 'repo': 'test/shared', 'file': 'shared.safetensors', 'gb': 0.5},
        ]},
    }},
}


class PresetsUITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.models = pathlib.Path(self.temp.name)
        self.displayed = []
        for target, replacement in (
            ('_presets', lambda: copy.deepcopy(PRESETS)),
            ('_keys', lambda: {}),
            ('MODELS', self.models),
        ):
            manager = patch.object(hub, target, replacement)
            manager.start()
            self.addCleanup(manager.stop)
        display_patch = patch('IPython.display.display', side_effect=self.displayed.append)
        display_patch.start()
        self.addCleanup(display_patch.stop)
        self.access = patch.object(hub, 'hf_check', return_value=('ok', 'OK')).start()
        self.addCleanup(patch.stopall)
        self.download = patch.object(hub, '_hf_stream', side_effect=self.install).start()
        hub.presets_ui()
        self.ui = self.displayed[-1]

    def install(self, repo, file, folder, token, progress, rename=None):
        target = self.models / folder / (rename or pathlib.Path(file).name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'test model placeholder')
        return target, True

    def controls(self):
        checks, choices = {}, {}
        import ipywidgets as W
        for widget in self.ui.children[2].children:
            if isinstance(widget, W.Checkbox):
                checks[widget.description] = widget
            elif isinstance(widget, (W.Dropdown, W.SelectMultiple)):
                choices[widget.description] = widget
        return checks, choices

    def test_starts_unchecked_including_fixed_and_nonoptional_components(self):
        checks, choices = self.controls()
        self.assertEqual(set(checks), {'diffusion', 'vae', 'extras'})
        self.assertTrue(all(not check.value for check in checks.values()))
        self.assertTrue(all(choice.disabled for choice in choices.values()))
        self.assertTrue(self.ui.children[4].disabled)
        self.assertIn('tick the components', self.ui.children[3].value)
        self.download.assert_not_called()

    def test_download_only_chosen_quant_and_preserve_selection(self):
        checks, choices = self.controls()
        checks['diffusion'].value = True
        choices['diffusion'].value = 1
        self.ui.children[4].click()
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(self.download.call_args.args[:3], ('test/first', 'quant.safetensors', 'diffusion_models'))
        checks, choices = self.controls()
        self.assertTrue(checks['diffusion'].value)
        self.assertEqual(choices['diffusion'].value, 1)
        self.assertFalse(checks['vae'].value)
        self.assertTrue(self.ui.children[4].disabled)

    def test_single_option_vae_can_be_downloaded_alone(self):
        checks, _ = self.controls()
        checks['vae'].value = True
        self.ui.children[4].click()
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(self.download.call_args.args[:3], ('test/shared', 'shared.safetensors', 'vae'))

    def test_unchecking_excludes_retained_quant_choice(self):
        checks, choices = self.controls()
        checks['diffusion'].value = True
        choices['diffusion'].value = 1
        checks['diffusion'].value = False
        self.assertTrue(choices['diffusion'].disabled)
        self.assertTrue(self.ui.children[4].disabled)
        checks['vae'].value = True
        self.ui.children[4].click()
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(self.download.call_args.args[1], 'shared.safetensors')

    def test_multi_option_selection_requires_component_checkbox(self):
        checks, choices = self.controls()
        checks['extras'].value = True
        choices['extras'].value = (1,)
        checks['extras'].value = False
        self.assertTrue(self.ui.children[4].disabled)
        checks['extras'].value = True
        self.ui.children[4].click()
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(self.download.call_args.args[1], 'b.safetensors')
        checks, choices = self.controls()
        self.assertTrue(checks['extras'].value)
        self.assertEqual(choices['extras'].value, (1,))

    def test_switching_model_resets_all_selections_and_shared_files_are_skipped(self):
        checks, _ = self.controls()
        checks['vae'].value = True
        self.ui.children[4].click()
        self.download.reset_mock()
        self.access.reset_mock()
        self.ui.children[1].value = 'second'
        checks, _ = self.controls()
        self.assertFalse(checks['vae'].value)
        checks['vae'].value = True
        self.assertTrue(self.ui.children[4].disabled)
        self.assertIn('already installed', self.ui.children[3].value)
        self.download.assert_not_called()
        self.access.assert_not_called()

    def test_every_versioned_preset_has_independent_unchecked_components(self):
        presets = json.loads((ROOT / 'config/presets.json').read_text(encoding='utf-8'))
        presets = {key: value for key, value in presets.items() if not key.startswith('_')}
        with patch.object(hub, '_presets', return_value=presets):
            hub.presets_ui()
        self.ui = self.displayed[-1]
        for key, preset in presets.items():
            with self.subTest(model=key):
                self.ui.children[1].value = key
                checks, _ = self.controls()
                self.assertEqual(set(checks), set(preset['components']))
                self.assertTrue(all(not check.value for check in checks.values()))
                self.assertTrue(self.ui.children[4].disabled)


if __name__ == '__main__':
    unittest.main()
