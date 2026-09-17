"""配置 store 单测（离线，用临时目录）。"""
import os

import yaml

from config.store import ConfigStore


def _store(tmp_path):
    return ConfigStore(
        config_path=str(tmp_path / "config.yaml"),
        rooms_path=str(tmp_path / "rooms.yaml"),
    )


def test_missing_files_use_defaults(tmp_path):
    s = _store(tmp_path)
    assert s.settings.poll_interval == 60
    assert s.settings.output_dir == "recordings"
    assert s.rooms == []


def test_partial_config_self_heals(tmp_path):
    (tmp_path / "config.yaml").write_text("poll_interval: 30\n", encoding="utf-8")
    s = _store(tmp_path)
    assert s.settings.poll_interval == 30
    assert s.settings.quality == "OD"          # 缺失键回落默认
    assert s.settings.video["remux_mp4"] is True  # 嵌套段默认保留


def test_rooms_parse(tmp_path):
    (tmp_path / "rooms.yaml").write_text(
        "rooms:\n"
        "  - id: '111'\n"
        "    url: https://live.dy.example/111\n"
        "    name: A\n"
        "    enabled: true\n"
        "    poll_schedule: '20:00-22:00=15'\n"
        "  - id: '222'\n"
        "    url: https://live.dy.example/222\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    s = _store(tmp_path)
    assert len(s.rooms) == 2
    assert s.rooms[0].poll_schedule == "20:00-22:00=15"
    assert [r.id for r in s.enabled_rooms()] == ["111"]


def test_add_remove_persists(tmp_path):
    s = _store(tmp_path)
    s.add_room("https://live.dy.example/333", name="C")
    on_disk = yaml.safe_load((tmp_path / "rooms.yaml").read_text(encoding="utf-8"))
    assert on_disk["rooms"][0]["id"] == "333"

    reloaded = _store(tmp_path)
    assert [r.id for r in reloaded.rooms] == ["333"]

    assert s.remove_room("333") is True
    assert s.remove_room("nope") is False
    assert _store(tmp_path).rooms == []


def test_duplicate_room_rejected(tmp_path):
    s = _store(tmp_path)
    s.add_room("https://live.dy.example/444")
    try:
        s.add_room("https://live.dy.example/444")
        assert False, "should raise"
    except ValueError:
        pass


def test_set_enabled_and_update_persist(tmp_path):
    s = _store(tmp_path)
    s.add_room("https://live.dy.example/555")
    assert s.set_enabled("555", False) is True
    assert _store(tmp_path).get_room("555").enabled is False

    assert s.update_room("555", poll_schedule="01:00-05:00=120", quality="HD") is True
    r = _store(tmp_path).get_room("555")
    assert r.poll_schedule == "01:00-05:00=120"
    assert r.quality == "HD"


def test_hot_reload_on_mtime_change(tmp_path):
    s = _store(tmp_path)
    assert s.rooms == []
    assert s.reload_if_changed() is False

    (tmp_path / "rooms.yaml").write_text(
        "rooms:\n  - id: '777'\n    url: https://live.dy.example/777\n", encoding="utf-8"
    )
    os.utime(tmp_path / "rooms.yaml", (9e9, 9e9))  # 强制 mtime 变化
    assert s.reload_if_changed() is True
    assert [r.id for r in s.rooms] == ["777"]


if __name__ == "__main__":
    import pathlib
    import tempfile

    failed = 0
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(pathlib.Path(td))
                print(f"PASS {fn.__name__}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
