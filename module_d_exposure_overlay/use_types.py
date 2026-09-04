"""건축물대장 주용도 매핑 로더 (Module D).

scripts/fetch_building_use_types.py가 만든 필지키(bd_mgt_sn 앞 19자리) -> 주용도
매핑을 읽는다. 이 파일은 API 산출물이라 저장소에 커밋되지 않으므로(.gitignore)
없을 수 있다 — 없으면 error가 아니라 빈 매핑으로 폴백하고, 실제로 조인이 필요한
건물이 있을 때만 호출측이 warning을 남긴다. §4.2의 "각 모듈은 다른 것 없이 pytest로
독립 실행 가능" 요건을 지키기 위해서다.

조인 정밀도는 필지까지다(동 단위 아님). 상세는 policies/module_d.json의
use_type_join 행과 data/precomputed/building_use_types.meta.json 참조.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ParcelUseTypes:
    """필지키 -> 주용도 원본 문자열. available=False면 매핑 없이 동작한다."""

    mapping: dict[str, str] = field(default_factory=dict)
    path: str = ""
    available: bool = False
    error: str | None = None

    def get(self, parcel_key: str) -> str | None:
        return self.mapping.get(parcel_key)

    def __len__(self) -> int:
        return len(self.mapping)


@lru_cache(maxsize=None)
def load(source_file: str) -> ParcelUseTypes:
    """저장소 루트 기준 상대경로로 매핑을 읽는다. 실패해도 예외를 올리지 않는다."""
    path = REPO_ROOT / source_file
    if not path.is_file():
        return ParcelUseTypes(path=str(path), available=False, error="파일 없음")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        return ParcelUseTypes(
            path=str(path), available=False, error=f"{type(exc).__name__}: {exc}"
        )
    if not isinstance(raw, dict):
        return ParcelUseTypes(path=str(path), available=False, error="최상위가 객체가 아님")
    mapping = {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
    return ParcelUseTypes(mapping=mapping, path=str(path), available=True)
