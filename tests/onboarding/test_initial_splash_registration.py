# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""First splash has a live Continue operator before deferred UI loading."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def load_bootstrap():
    path = ROOT / 'src/scripts/startup/bootstrap/__init__.py'
    spec = importlib.util.spec_from_file_location('lampway_splash_bootstrap_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_splash_operator_registers_before_first_bootstrap_menu(monkeypatch, tmp_path):
    boot = load_bootstrap()
    modules = tmp_path / 'modules'
    modules.mkdir()
    calls = []
    monkeypatch.setattr(boot, '_get_mixar_path', lambda: tmp_path)
    monkeypatch.setattr(boot, '_setup_mixar_packages', lambda: None)
    monkeypatch.setattr(boot, '_register_single_ui_module', lambda file, root: calls.append(('ui', file.relative_to(root).as_posix())))
    monkeypatch.setattr(boot, '_load_bootstrap_modules', lambda: calls.append(('bootstrap', None)))
    monkeypatch.setattr(boot, '_discover_ui_files', lambda root: [])
    monkeypatch.setattr(boot, '_initialize_theme_defaults', lambda: None)
    for name, attrs in {
        'mixar.modules.common.network': dict(configure_network=lambda: None),
        'mixar.modules.common.versioning.handlers': dict(register=lambda: None),
        'mixar.modules.common.core.lampway_night': dict(schedule_offer=lambda bpy: None),
        'mixar.modules.common.api': dict(start_executor=lambda: None, start_api_processor=lambda: None),
    }.items():
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(**attrs))
    boot.register()
    assert calls[:2] == [('ui', 'lampway_tools/ui/onboarding.py'), ('bootstrap', None)]


def test_deferred_revisit_preserves_early_registered_class_identity(monkeypatch, tmp_path):
    boot = load_bootstrap()
    ui = tmp_path / 'lampway_tools/ui/onboarding.py'
    ui.parent.mkdir(parents=True)
    ui.write_text('')
    cls = SimpleNamespace(is_registered=False)
    registrations = []
    def register():
        registrations.append(cls)
        cls.is_registered = True
    module = SimpleNamespace(classes=(cls,), register=register)
    monkeypatch.setitem(sys.modules, 'mixar.modules.lampway_tools.ui.onboarding', module)
    boot._register_single_ui_module(ui, tmp_path)
    boot._register_single_ui_module(ui, tmp_path)
    assert registrations == [cls]
    assert boot._loaded_ui_modules == [module]
