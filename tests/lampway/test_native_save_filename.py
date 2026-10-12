# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the actual save-path routine against controlled RNA/path boundaries."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/source/blender/windowmanager/intern/wm_files.cc'


def save_path_function():
    source = SOURCE.read_text()
    start = source.index('static void save_set_filepath(bContext *C, wmOperator *op)')
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def test_native_save_path_preserves_existing_suffix_and_selected_extension(tmp_path):
    compiler = shutil.which('g++') or shutil.which('clang++')
    assert compiler, 'C++ compiler required for native save-path controls'
    preamble = r'''
#include <string>
#include <cstring>
#include <cassert>
#include <cctype>
constexpr int FILE_MAX = 1024;
constexpr const char *BLENDER_ASSET_FILE_SUFFIX = ".asset.blend";
struct Main { char filepath[FILE_MAX]; bool is_asset_edit_file = false; } main_data;
struct RecentFile { const char *filepath; };
struct bContext {};
struct Properties { bool filepath_set = false; int extension = 0; std::string output; };
struct wmOperator { Properties *ptr; };
struct PropertyRNA { int kind; } path_property{0}, extension_property{1};
struct { struct { void *first = nullptr; } recent_files; } G;
Main *CTX_data_main(bContext *) { return &main_data; }
PropertyRNA *RNA_struct_find_property(Properties *, const char *name) {
  return strcmp(name,"filepath")==0 ? &path_property : &extension_property;
}
bool RNA_property_is_set(Properties *p, PropertyRNA *prop) { return prop->kind ? true : p->filepath_set; }
int RNA_property_enum_get(Properties *p, PropertyRNA *) { return p->extension; }
void RNA_property_string_set(Properties *p, PropertyRNA *, const char *value) { p->output=value; }
const char *BKE_main_blendfile_path(Main *main) { return main->filepath; }
#define STRNCPY(dest, src) strcpy(dest, src)
struct StringRef : std::string {
  using std::string::string;
  bool endswith(const char *s) { return ends_with(s); }
};
bool BLI_path_extension_check(const char *path, const char *ext) {
  std::string s=path, suffix=ext;
  for(char &c:s) c=std::tolower((unsigned char)c);
  return s.size()>suffix.size() && s.ends_with(suffix);
}
/* Blender path_utils treats a leading-dot basename as having no extension. */
void BLI_path_extension_replace(char *path, int, const char *ext) {
  std::string s=path;
  auto slash=s.find_last_of('/'), dot=s.find_last_of('.');
  if(dot!=std::string::npos && dot>(slash==std::string::npos ? 0 : slash+1)) s.resize(dot);
  s+=ext;strcpy(path,s.c_str());
}
void BLI_path_extension_ensure(char *path, int, const char *ext) {
  if(!BLI_path_extension_check(path,ext)) strcat(path,ext);
}
void wm_filepath_default(Main *, char *path, const char *ext) {
  if(!path[0]) { strcpy(path,"Untitled");strcat(path,ext); }
}
''' + save_path_function() + r'''
int main() {
  bContext context; Properties properties; wmOperator op{&properties};
  for(const char *path : {"/owned/helmet-suite.mixar", "/owned/.mixar", "/owned/helmet.v2.MIXAR"}) {
    strcpy(main_data.filepath,path); properties.extension=0;
    save_set_filepath(&context,&op);assert(properties.output==path);
    strcpy(main_data.filepath,properties.output.c_str());
    save_set_filepath(&context,&op);assert(properties.output==path);
  }
  strcpy(main_data.filepath,"/owned/helmet.blend");properties.extension=0;
  save_set_filepath(&context,&op);assert(properties.output=="/owned/helmet.mixar");
  strcpy(main_data.filepath,"/owned/helmet.mixar");properties.extension=1;
  save_set_filepath(&context,&op);assert(properties.output=="/owned/helmet.blend");
  properties.filepath_set=true; properties.output="explicit";
  save_set_filepath(&context,&op);assert(properties.output=="explicit");
}
'''
    file = tmp_path / 'save_path.cc'
    file.write_text(preamble)
    executable = tmp_path / 'save_path'
    built = subprocess.run([compiler, '-std=c++20', '-DLAMPWAY', str(file), '-o', str(executable)],capture_output=True,text=True)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(executable)],capture_output=True,text=True)
    assert run.returncode == 0, run.stderr
