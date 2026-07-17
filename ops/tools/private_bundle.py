from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import shutil
import struct
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"SBB1"
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
EXCLUDED_DIRECTORIES = {"basemap-cache", "tile-cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".log", ".pyc"}


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise ValueError("passphrase must not be empty")
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    return kdf.derive(passphrase.encode("utf-8"))


def _archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    path = PurePosixPath(info.name)
    if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
        return None
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return None
    if info.issym() or info.islnk():
        return None
    return info


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum(path: Path) -> None:
    checksum_path = Path(f"{path}.sha256")
    checksum_path.write_text(f"{_sha256(path)}  {path.name}\n", encoding="ascii")


def _verify_checksum(path: Path) -> None:
    checksum_path = Path(f"{path}.sha256")
    if not checksum_path.is_file():
        return
    expected = checksum_path.read_text(encoding="ascii").split()[0].lower()
    actual = _sha256(path)
    if expected != actual:
        raise ValueError("bundle checksum verification failed")


def create_bundle(source: str | Path, output: str | Path, passphrase: str) -> Path:
    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if not source_path.is_dir():
        raise ValueError(f"source directory does not exist: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="smart-bamboo-bundle-") as temp_dir:
        archive_path = Path(temp_dir) / "private-data.tar.gz"
        with tarfile.open(archive_path, "w:gz", compresslevel=9) as archive:
            archive.add(source_path, arcname="data", recursive=True, filter=_archive_filter)

        salt = os.urandom(SALT_SIZE)
        nonce = os.urandom(NONCE_SIZE)
        encryptor = Cipher(algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
        temporary_output = output_path.with_suffix(f"{output_path.suffix}.tmp")
        try:
            with archive_path.open("rb") as source_handle, temporary_output.open("wb") as output_handle:
                output_handle.write(MAGIC)
                output_handle.write(salt)
                output_handle.write(nonce)
                for chunk in iter(lambda: source_handle.read(CHUNK_SIZE), b""):
                    output_handle.write(encryptor.update(chunk))
                output_handle.write(encryptor.finalize())
                output_handle.write(encryptor.tag)
            temporary_output.replace(output_path)
        finally:
            temporary_output.unlink(missing_ok=True)

    _write_checksum(output_path)
    return output_path


def _assert_safe_archive(archive: tarfile.TarFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise ValueError("bundle contains an unsupported link")
        target = (destination_root / member.name).resolve()
        if target != destination_root and destination_root not in target.parents:
            raise ValueError("bundle contains an unsafe path")


def extract_bundle(bundle: str | Path, destination: str | Path, passphrase: str) -> Path:
    bundle_path = Path(bundle).resolve()
    destination_path = Path(destination).resolve()
    _verify_checksum(bundle_path)

    minimum_size = len(MAGIC) + SALT_SIZE + NONCE_SIZE + TAG_SIZE
    if not bundle_path.is_file() or bundle_path.stat().st_size <= minimum_size:
        raise ValueError("bundle is missing or invalid")

    with bundle_path.open("rb") as source_handle:
        if source_handle.read(len(MAGIC)) != MAGIC:
            raise ValueError("bundle format is not supported")
        salt = source_handle.read(SALT_SIZE)
        nonce = source_handle.read(NONCE_SIZE)
        ciphertext_start = source_handle.tell()
        ciphertext_size = bundle_path.stat().st_size - minimum_size
        source_handle.seek(-TAG_SIZE, os.SEEK_END)
        tag = source_handle.read(TAG_SIZE)
        source_handle.seek(ciphertext_start)

        with tempfile.TemporaryDirectory(prefix="smart-bamboo-restore-") as temp_dir:
            archive_path = Path(temp_dir) / "private-data.tar.gz"
            decryptor = Cipher(
                algorithms.AES(_derive_key(passphrase, salt)),
                modes.GCM(nonce, tag),
            ).decryptor()
            remaining = ciphertext_size
            try:
                with archive_path.open("wb") as archive_handle:
                    while remaining:
                        chunk = source_handle.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            raise ValueError("bundle ciphertext is truncated")
                        remaining -= len(chunk)
                        archive_handle.write(decryptor.update(chunk))
                    archive_handle.write(decryptor.finalize())
            except InvalidTag as exc:
                raise ValueError("bundle authentication failed; check passphrase") from exc

            destination_path.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, "r:gz") as archive:
                _assert_safe_archive(archive, destination_path)
                archive.extractall(destination_path, filter="data")

    return destination_path


def _passphrase() -> str:
    return os.environ.get("SMART_BAMBOO_BUNDLE_PASSPHRASE") or getpass.getpass("Bundle passphrase: ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypt or restore a Smart Bamboo private data bundle.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("source")
    create_parser.add_argument("output")
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("bundle")
    extract_parser.add_argument("destination")
    args = parser.parse_args()

    passphrase = _passphrase()
    if args.command == "create":
        result = create_bundle(args.source, args.output, passphrase)
    else:
        result = extract_bundle(args.bundle, args.destination, passphrase)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
