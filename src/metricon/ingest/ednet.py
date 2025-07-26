from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from metricon.schema.events import canonical_json, digest
from metricon.storage.hashing import atomic_json, file_hash, read_json

EDNET_REPOSITORY = "https://github.com/riiid/ednet"
EDNET_LICENSE = "CC BY-NC 4.0"
EDNET_LINKS = {"kt1": "https://bit.ly/ednet_kt1", "contents": "https://bit.ly/ednet-content"}
EDNET_ADAPTER_VERSION = "ednet-kt1/1"


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self.active = False

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attributes_dict = dict(attributes)
        if tag == "form" and attributes_dict.get("id") == "download-form":
            self.active = True
            self.action = attributes_dict.get("action")
        if tag == "input" and self.active and attributes_dict.get("type") == "hidden":
            name = attributes_dict.get("name")
            value = attributes_dict.get("value")
            if name is not None and value is not None:
                self.fields[name] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.active = False


def download_ednet(cache: Path, kind: str, maximum_bytes: int = 2_000_000_000) -> dict[str, Any]:
    if kind not in EDNET_LINKS:
        raise ValueError("EdNet source must be kt1 or contents")
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / ("EdNet-KT1.zip" if kind == "kt1" else "contents.zip")
    manifest_path = destination.with_suffix(".provenance.json")
    if destination.exists() and manifest_path.exists():
        manifest = read_json(manifest_path)
        if file_hash(destination) != manifest["sha256"]:
            raise ValueError("Cached EdNet archive checksum changed")
        return manifest
    url = EDNET_LINKS[kind]
    started = time.time()
    with urllib.request.urlopen(url, timeout=60) as response:
        final_url = response.url
    if "/file/d/" in final_url:
        match = re.search(r"/file/d/([^/]+)", final_url)
        if match is None:
            raise ValueError("Unrecognized EdNet download redirect")
        url = "https://drive.google.com/uc?" + urllib.parse.urlencode(
            {"export": "download", "id": match.group(1)}
        )
    else:
        url = final_url
    request = urllib.request.Request(url, headers={"User-Agent": "Metricon-research/2"})
    response = urllib.request.urlopen(request, timeout=60)
    try:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            html = response.read(1_000_001)
            if len(html) > 1_000_000:
                raise ValueError("Download HTML exceeds safety bound")
            form = DownloadForm()
            form.feed(html.decode("utf-8"))
            if (
                not form.action
                or urllib.parse.urlparse(form.action).hostname != "drive.usercontent.google.com"
            ):
                raise ValueError("EdNet download blocked or requires unavailable authentication")
            response.close()
            request = urllib.request.Request(
                form.action + "?" + urllib.parse.urlencode(form.fields),
                headers={"User-Agent": "Metricon-research/2"},
            )
            response = urllib.request.urlopen(request, timeout=60)
        temporary = destination.with_suffix(".partial")
        count = 0
        sha = hashlib.sha256()
        try:
            with temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > maximum_bytes:
                        raise ValueError("Download exceeds configured byte bound")
                    handle.write(chunk)
                    sha.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if not zipfile.is_zipfile(temporary):
                raise ValueError("EdNet source returned something other than a ZIP archive")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        response.close()
    manifest = {
        "source": EDNET_LINKS[kind],
        "repository": EDNET_REPOSITORY,
        "resolved_url": response.url,
        "license": EDNET_LICENSE,
        "sha256": sha.hexdigest(),
        "bytes": count,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": time.time() - started,
        "integrity": "Locally computed SHA-256; no publisher checksum is supplied",
    }
    atomic_json(manifest_path, manifest)
    return manifest


def question_metadata(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith("/questions.csv") or name == "questions.csv"
        ]
        if len(candidates) != 1:
            raise ValueError("EdNet content archive requires exactly one questions.csv")
        member = archive.getinfo(candidates[0])
        if member.file_size > 20_000_000:
            raise ValueError("EdNet metadata exceeds expected bounded size")
        with (
            archive.open(member) as binary,
            io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as handle,
        ):
            result = {}
            for row in csv.DictReader(handle):
                identifier = row["question_id"]
                if identifier in result:
                    raise ValueError("Duplicate EdNet question metadata")
                correct = row["correct_answer"].strip().lower()
                if correct not in {"a", "b", "c", "d"}:
                    raise ValueError("Invalid metadata correct_answer")
                tags = sorted(
                    set(tag for tag in row.get("tags", "").split(";") if tag and tag != "-1")
                )
                result[identifier] = {
                    "correct_answer": correct,
                    "bundle_id": row["bundle_id"],
                    "skills": ["ednet:" + tag for tag in tags],
                    "part": int(row["part"]),
                }
    return result, file_hash(path)


def create_subset(
    archive_path: Path,
    contents_path: Path,
    destination: Path,
    minimum_interactions: int = 200_000,
    minimum_learners: int = 1000,
    seed: int = 2026,
    maximum_learners: int = 10_000,
    minimum_sessions: int = 5,
) -> dict[str, Any]:
    if minimum_interactions < 1 or minimum_learners < 1 or maximum_learners < minimum_learners:
        raise ValueError("Invalid EdNet subset bounds")
    metadata, metadata_hash = question_metadata(contents_path)
    archive_hash = file_hash(archive_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    exclusions: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    interactions = 0
    with zipfile.ZipFile(archive_path) as archive, temporary.open("w", encoding="utf-8") as output:
        members = [
            member
            for member in archive.infolist()
            if re.search(r"(^|/)u\d+\.csv$", member.filename)
        ]
        members.sort(key=lambda member: digest([seed, member.filename]))
        for member in members:
            if len(selected) >= maximum_learners:
                break
            if member.file_size > 50_000_000:
                exclusions["oversized_learner"] += 1
                continue
            learner_id = Path(member.filename).stem
            session_ids = set()
            rows = 0
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as learner_output:
                with (
                    archive.open(member) as binary,
                    io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as handle,
                ):
                    reader = csv.DictReader(handle)
                    required = {
                        "timestamp",
                        "solving_id",
                        "question_id",
                        "user_answer",
                        "elapsed_time",
                    }
                    if not required.issubset(reader.fieldnames or []):
                        raise ValueError("EdNet KT1 header differs from documented schema")
                    for sequence, row in enumerate(reader):
                        question = metadata.get(row["question_id"])
                        if question is None:
                            exclusions["missing_question_metadata"] += 1
                            continue
                        answer = row["user_answer"].strip().lower()
                        valid_answers = (
                            {"a", "b", "c"} if question["part"] == 2 else {"a", "b", "c", "d"}
                        )
                        if answer not in valid_answers:
                            exclusions["invalid_answer"] += 1
                            continue
                        try:
                            milliseconds = int(row["timestamp"])
                            timestamp = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
                            elapsed = int(row["elapsed_time"])
                            solving_id = int(row["solving_id"])
                            if milliseconds < 0 or solving_id < 0:
                                raise ValueError("negative identifier or timestamp")
                        except (ValueError, OverflowError):
                            exclusions["malformed_numeric"] += 1
                            continue
                        session = str(solving_id)
                        session_ids.add(session)
                        event = {
                            "source_namespace": "ednet-kt1",
                            "event_id": f"{learner_id}:{sequence}",
                            "learner_id": learner_id,
                            "question_id": row["question_id"],
                            "skills": question["skills"],
                            "correct": answer == question["correct_answer"],
                            "attempt_kind": "practice",
                            "source_sequence": sequence,
                            "timestamp": timestamp.isoformat(),
                            "duration_ms": elapsed if elapsed >= 0 else None,
                            "session_id": session,
                            "bundle_id": question["bundle_id"],
                            "order_scope": "learner",
                            "time_semantics": "shifted",
                            "duration_scope": "bundle" if elapsed >= 0 else "unknown",
                        }
                        learner_output.write(canonical_json(event) + "\n")
                        rows += 1
                if len(session_ids) < minimum_sessions:
                    exclusions["insufficient_sessions_learner"] += 1
                    exclusions["insufficient_sessions_rows"] += rows
                    continue
                learner_output.seek(0)
                for chunk in iter(lambda: learner_output.read(1024 * 1024), ""):
                    output.write(chunk)
            interactions += rows
            selected.append(
                {
                    "member": member.filename,
                    "learner": learner_id,
                    "rows": rows,
                    "sessions": len(session_ids),
                    "crc32": member.CRC,
                }
            )
            if interactions >= minimum_interactions and len(selected) >= minimum_learners:
                break
        output.flush()
        os.fsync(output.fileno())
    if interactions < minimum_interactions or len(selected) < minimum_learners:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            f"EdNet subset gate unmet: {interactions} interactions, {len(selected)} learners"
        )
    os.replace(temporary, destination)
    manifest = {
        "adapter_version": EDNET_ADAPTER_VERSION,
        "repository": EDNET_REPOSITORY,
        "license": EDNET_LICENSE,
        "archive_sha256": archive_hash,
        "content_sha256": metadata_hash,
        "subset_sha256": file_hash(destination),
        "seed": seed,
        "interactions": interactions,
        "learners": len(selected),
        "minimum_sessions": minimum_sessions,
        "selected": selected,
        "exclusions": dict(exclusions),
        "selection": "SHA-256 order of seed/member name; complete eligible learner files",
        "timestamp_semantics": "Shifted source milliseconds; no real-world calendar inference",
        "duration_semantics": "Bundle-level repeated durations counted once per learner/session/bundle",
        "redistribution": "Raw learner records are local and ignored by Git; cite original source and license.",
    }
    atomic_json(destination.with_suffix(".manifest.json"), manifest)
    return manifest
