"""YAML 配置存储（M2）。

config.yaml — 全局运行参数；rooms.yaml — 房间列表 + 分房间分时段调度。
缺失键按默认值自愈；mtime 变化时热重载（借鉴 DLR 的热重载思路，改用 YAML）。
Cookie 优先读环境变量 DY_COOKIE，其次 config.yaml（红线：不写死在代码）。
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

DEFAULT_SETTINGS = {
    "output_dir": "recordings",
    "poll_interval": 60,
    "poll_schedule": "",
    "quality": "OD",
    "cookie": "",
    "proxy": "",
    "log_level": "INFO",
    "video": {"enabled": True, "segment_size_mb": 1024, "remux_mp4": True},
    "danmaku": {"enabled": True, "reconnect": True},
}


@dataclass
class Settings:
    output_dir: str = "recordings"
    poll_interval: int = 60
    poll_schedule: str = ""
    quality: str = "OD"
    cookie: str = ""
    proxy: str = ""
    log_level: str = "INFO"
    video: dict = field(default_factory=lambda: dict(DEFAULT_SETTINGS["video"]))
    danmaku: dict = field(default_factory=lambda: dict(DEFAULT_SETTINGS["danmaku"]))


@dataclass
class Room:
    id: str
    url: str
    name: str = ""
    enabled: bool = True
    poll_schedule: str = ""
    quality: str = ""
    record_video: bool = True
    record_danmaku: bool = True


def settings_from_dict(d: dict) -> Settings:
    merged = {**DEFAULT_SETTINGS, **(d or {})}
    # 嵌套段单独合并，避免整段被覆盖丢默认键
    merged["video"] = {**DEFAULT_SETTINGS["video"], **(d or {}).get("video", {})}
    merged["danmaku"] = {**DEFAULT_SETTINGS["danmaku"], **(d or {}).get("danmaku", {})}
    return Settings(**{k: merged[k] for k in Settings.__dataclass_fields__})


def room_from_dict(d: dict) -> Room:
    known = {k: d.get(k, v) for k, v in Room.__dataclass_fields__.items() if k in d}
    base = Room(id=str(d.get("id", "")), url=d.get("url", ""))
    for k, v in known.items():
        setattr(base, k, v)
    return base


def room_to_dict(r: Room) -> dict:
    return asdict(r)


class ConfigStore:
    def __init__(self, config_path: str = "config.yaml", rooms_path: str = "rooms.yaml"):
        self.config_path = Path(config_path)
        self.rooms_path = Path(rooms_path)
        self.settings = Settings()
        self.rooms: list[Room] = []
        self._mtime: dict[str, float] = {}
        self.load()

    # ---- 读取 ----
    def _read_yaml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load(self) -> None:
        cfg = self._read_yaml(self.config_path)
        self.settings = settings_from_dict(cfg)
        rooms_doc = self._read_yaml(self.rooms_path)
        self.rooms = [room_from_dict(r) for r in (rooms_doc.get("rooms") or [])]
        self._mtime = {
            "config": self._mtime_of(self.config_path),
            "rooms": self._mtime_of(self.rooms_path),
        }

    @staticmethod
    def _mtime_of(path: Path) -> float:
        return path.stat().st_mtime if path.exists() else 0.0

    def reload_if_changed(self) -> bool:
        cur = {
            "config": self._mtime_of(self.config_path),
            "rooms": self._mtime_of(self.rooms_path),
        }
        if cur != self._mtime:
            self.load()
            return True
        return False

    # ---- 访问 ----
    def enabled_rooms(self) -> list[Room]:
        return [r for r in self.rooms if r.enabled]

    def cookie(self) -> str | None:
        return os.environ.get("DY_COOKIE") or self.settings.cookie or None

    # ---- 房间 CRUD（写回 rooms.yaml）----
    def _save_rooms(self) -> None:
        doc = {"rooms": [room_to_dict(r) for r in self.rooms]}
        self.rooms_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rooms_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        self._mtime["rooms"] = self._mtime_of(self.rooms_path)

    def save_settings(self) -> None:
        doc = asdict(self.settings)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        self._mtime["config"] = self._mtime_of(self.config_path)

    def add_room(self, url: str, *, room_id: str = "", name: str = "", **overrides) -> Room:
        rid = room_id or url.rstrip("/").split("/")[-1]
        if any(r.id == rid for r in self.rooms):
            raise ValueError(f"room already exists: {rid}")
        room = Room(id=rid, url=url, name=name, **overrides)
        self.rooms.append(room)
        self._save_rooms()
        return room

    def remove_room(self, room_id: str) -> bool:
        before = len(self.rooms)
        self.rooms = [r for r in self.rooms if r.id != room_id]
        if len(self.rooms) != before:
            self._save_rooms()
            return True
        return False

    def set_enabled(self, room_id: str, enabled: bool) -> bool:
        for r in self.rooms:
            if r.id == room_id:
                r.enabled = enabled
                self._save_rooms()
                return True
        return False

    def update_room(self, room_id: str, **fields) -> bool:
        for r in self.rooms:
            if r.id == room_id:
                for k, v in fields.items():
                    if k in Room.__dataclass_fields__:
                        setattr(r, k, v)
                self._save_rooms()
                return True
        return False

    def get_room(self, room_id: str) -> Room | None:
        for r in self.rooms:
            if r.id == room_id:
                return r
        return None
