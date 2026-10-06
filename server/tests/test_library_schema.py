"""Asset Vault schema (specs/asset_library/asset_schema.md section 10)."""
import sqlite3

import pytest

from lampway_server.library import schema as S


def test_every_kind_has_a_stats_table_and_a_file_roles_entry():
    assert set(S.KINDS) == {"mesh", "image", "material", "texture_set", "map", "uv_layout", "rig", "animation", "video", "hdri", "prompt", "receipt", "collection"}
    for kind, spec in S.KINDS.items():
        assert "file_roles" in spec and "subtypes" in spec and "stats_table" in spec, kind
        if spec["stats_table"]:
            assert f"CREATE TABLE {spec['stats_table']}(" in S.ddl(), kind


def test_the_ddl_creates_on_an_empty_db_and_foreign_keys_are_clean():
    db = sqlite3.connect(":memory:")
    db.executescript(S.ddl())
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("select count(*) from sqlite_master where name='asset_fts'").fetchone()[0] == 1


def test_a_relation_type_outside_the_check_fails():
    db = sqlite3.connect(":memory:")
    db.executescript(S.ddl())
    db.execute("insert into asset(id,kind,name,created_at,updated_at) values('a','mesh','a',0,0),('b','mesh','b',0,0)")
    db.execute("insert into relation(src,dst,type,by,created_at) values('a','b','derived_from','rule',0)")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into relation(src,dst,type,by,created_at) values('a','b','friends_with','rule',0)")


def test_schema_describe_sections_and_the_refusal_names_the_five():
    assert set(S.describe("kinds")["kinds"][0]) >= {"kind", "subtypes", "stats_table", "file_roles"}
    assert "derived_from" in S.describe("relations")["relation_types"]
    with pytest.raises(ValueError, match="kinds|relations|taxonomy|ddl|all"):
        S.describe("nope")
