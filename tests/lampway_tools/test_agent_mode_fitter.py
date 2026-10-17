# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the shipped pure chip fitter in both fork modes; this is not a Blender build."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / 'src/source/blender/editors/space_agent_bubble'
HARNESS = r'''
#include "agent_ui_chip_fit.hh"
#include <cassert>
#include <cstring>
#include <cstdio>
using namespace blender;
int main() {
  AgentChipMetrics metrics{18, 8, 12, 40, 44, 30, 18};
  int cases = 0;
  for (bool available : {false, true}) {
    for (bool byoa : {false, true}) {
      for (bool active : {false, true}) {
        AgentChipRowInputs in;
        in.model_available = true;
        in.model_label = "A deliberately very long model label";
        in.scribble_available = true;
        in.voice_available = true;
        in.voice_capturing = active;
        in.mark_count = active ? 2 : 0;
#ifdef LAMPWAY
        in.agent_mode_available = available;
        in.agent_byoa = byoa;
#endif
        AgentChipForms chips[AGENT_CHIP_SLOT_COUNT];
        agent_chip_forms(in, metrics, [](const char *s) {return float(std::strlen(s)) * 10;}, chips);
        for (float span = 480; span <= 1500; span += 3) {
          const auto fit = agent_chip_fit(chips, span, 12);
          assert(fit.fits);
          float used = 0;
          for (float width : fit.width) if (width > 0) used += width + 12;
          assert(used <= span + 0.5f);
#ifdef LAMPWAY
          const int mode = AGENT_CHIP_SLOT_AGENT_MODE;
          assert(available ? fit.width[mode] >= chips[mode].width[1] : fit.width[mode] == 0);
          if (available && span == 1500) assert(fit.form[mode] == 0);
#endif
          ++cases;
        }
      }
    }
  }
  std::printf("PASS %d cases\n", cases);
}
'''


def test_mode_switch_fits_with_and_without_lampway(tmp_path):
    compiler = shlex.split(os.environ.get('CXX') or 'c++')
    assert shutil.which(compiler[0]), 'a compiler is required for the pure header contract'
    source = tmp_path / 'mode_fit.cc'
    source.write_text(HARNESS)
    for enabled in (False, True):
        binary = tmp_path / ('mode-on' if enabled else 'mode-off')
        flags = ['-DLAMPWAY'] if enabled else []
        compiled = subprocess.run([*compiler, '-std=c++17', '-O0', *flags, '-I', str(HEADER), str(source), '-o', str(binary)],
                                  capture_output=True, text=True)
        assert compiled.returncode == 0, compiled.stderr
        ran = subprocess.run([str(binary)], capture_output=True, text=True)
        assert ran.returncode == 0 and ran.stdout.startswith('PASS '), ran.stdout + ran.stderr
