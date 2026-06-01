from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockRequest:
    resource_type: str
    resource_key: str
    mode: str = "write"

    def normalized(self) -> "LockRequest":
        mode = self.mode.lower().strip()
        if mode not in {"read", "write"}:
            raise ValueError(f"Unsupported lock mode: {self.mode}")
        return LockRequest(
            resource_type=self.resource_type.lower().strip(),
            resource_key=normalize_key(self.resource_key),
            mode=mode,
        )


def locks_conflict(left: LockRequest, right: LockRequest) -> bool:
    left = left.normalized()
    right = right.normalized()

    if left.mode == "read" and right.mode == "read":
        return False

    if left.resource_type == "repo" or right.resource_type == "repo":
        return repo_conflict(left, right)

    if left.resource_type == right.resource_type and left.resource_key == right.resource_key:
        return True

    if {left.resource_type, right.resource_type} <= {"file", "dir"}:
        return path_conflict(left, right)

    return False


def normalize_key(value: str) -> str:
    return value.replace("\\", "/").strip().strip("/")


def repo_conflict(left: LockRequest, right: LockRequest) -> bool:
    if left.resource_type == "repo" and right.resource_type == "repo":
        return left.resource_key == right.resource_key or "*" in {left.resource_key, right.resource_key}
    return left.mode == "write" or right.mode == "write"


def path_conflict(left: LockRequest, right: LockRequest) -> bool:
    if left.resource_type == "file" and right.resource_type == "file":
        return left.resource_key == right.resource_key

    if left.resource_type == "dir" and right.resource_type == "file":
        return is_under_dir(right.resource_key, left.resource_key)

    if left.resource_type == "file" and right.resource_type == "dir":
        return is_under_dir(left.resource_key, right.resource_key)

    if left.resource_type == "dir" and right.resource_type == "dir":
        return is_under_dir(left.resource_key, right.resource_key) or is_under_dir(
            right.resource_key, left.resource_key
        )

    return False


def is_under_dir(path: str, directory: str) -> bool:
    path = normalize_key(path)
    directory = normalize_key(directory)
    return path == directory or path.startswith(f"{directory}/")
