from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from prompt_architect.security import redact_secrets


TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html", ".ini",
    ".java", ".js", ".json", ".jsx", ".md", ".php", ".properties", ".py", ".rb",
    ".rs", ".scss", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf"}
MAX_FILES = 10
MAX_TEXT_BYTES = 256 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_CHARS = 1_000_000
MAX_CONTEXT_CHARS = 128_000


class ContextGrantError(ValueError):
    pass


@dataclass
class GrantedFile:
    path: Path
    display_name: str
    temporary: bool = False
    readable: bool = True


@dataclass
class ContextGrant:
    id: str
    files: list[GrantedFile] = field(default_factory=list)


@dataclass
class ContextBundle:
    text: str
    filenames: list[str]
    warnings: list[str]


class ContextGrantStore:
    """Session-scoped authorization registry; grants are never persisted."""

    def __init__(self, temp_root: Path) -> None:
        self.temp_root = temp_root.resolve()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        for candidate in self.temp_root.iterdir():
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
        self._grants: dict[str, ContextGrant] = {}

    def grant_desktop(self, paths: list[str]) -> ContextGrant:
        if len(paths) > MAX_FILES:
            raise ContextGrantError(f"一次最多选择 {MAX_FILES} 个文件。")
        files: list[GrantedFile] = []
        for raw in paths:
            candidate = Path(raw).expanduser().resolve()
            if not candidate.exists():
                raise ContextGrantError(f"文件不存在：{candidate.name}")
            if candidate.is_dir():
                files.append(GrantedFile(candidate, candidate.name, readable=False))
                continue
            self._validate_file(candidate)
            files.append(GrantedFile(candidate, candidate.name))
        return self._register(files)

    def grant_uploads(self, uploads: list[tuple[str, bytes]]) -> ContextGrant:
        if len(uploads) > MAX_FILES:
            raise ContextGrantError(f"一次最多上传 {MAX_FILES} 个文件。")
        identifier = str(uuid4())
        grant_dir = (self.temp_root / identifier).resolve()
        if not grant_dir.is_relative_to(self.temp_root):
            raise ContextGrantError("临时目录无效。")
        grant_dir.mkdir(parents=True)
        files: list[GrantedFile] = []
        try:
            for index, (raw_name, content) in enumerate(uploads):
                name = Path(raw_name or f"file-{index}").name
                if name in {"", ".", ".."}:
                    raise ContextGrantError("文件名无效。")
                target = (grant_dir / f"{index:02d}-{name}").resolve()
                if not target.is_relative_to(grant_dir):
                    raise ContextGrantError("文件名无效。")
                target.write_bytes(content)
                self._validate_file(target, display_name=name)
                files.append(GrantedFile(target, name, temporary=True))
        except Exception:
            shutil.rmtree(grant_dir, ignore_errors=True)
            raise
        grant = ContextGrant(identifier, files)
        self._grants[identifier] = grant
        return grant

    def consume(self, identifiers: list[str]) -> list[GrantedFile]:
        files: list[GrantedFile] = []
        for identifier in identifiers:
            grant = self._grants.get(identifier)
            if grant is None:
                raise ContextGrantError("上下文授权已过期，请重新选择文件。")
            files.extend(grant.files)
        if len(files) > MAX_FILES:
            raise ContextGrantError(f"一次最多使用 {MAX_FILES} 个文件。")
        return files

    def release(self, identifiers: list[str]) -> None:
        for identifier in identifiers:
            grant = self._grants.pop(identifier, None)
            if not grant:
                continue
            roots = {item.path.parent for item in grant.files if item.temporary}
            for root in roots:
                resolved = root.resolve()
                if resolved.is_relative_to(self.temp_root):
                    shutil.rmtree(resolved, ignore_errors=True)

    @staticmethod
    def public(grant: ContextGrant) -> dict:
        return {
            "id": grant.id,
            "files": [
                {"name": item.display_name, "readable": item.readable}
                for item in grant.files
            ],
        }

    def _register(self, files: list[GrantedFile]) -> ContextGrant:
        grant = ContextGrant(str(uuid4()), files)
        self._grants[grant.id] = grant
        return grant

    @staticmethod
    def _validate_file(path: Path, *, display_name: str | None = None) -> None:
        extension = Path(display_name or path.name).suffix.casefold()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ContextGrantError(f"暂不支持该文件类型：{extension or '无扩展名'}")
        size = path.stat().st_size
        limit = MAX_PDF_BYTES if extension == ".pdf" else MAX_TEXT_BYTES
        if size > limit:
            label = "20 MiB" if extension == ".pdf" else "256 KiB"
            raise ContextGrantError(f"文件 {display_name or path.name} 超过 {label} 限制。")


class ContextLoader:
    def load(self, files: list[GrantedFile]) -> ContextBundle:
        sections: list[str] = []
        warnings: list[str] = []
        total = 0
        names: list[str] = []
        for item in files:
            names.append(item.display_name)
            if not item.readable:
                warnings.append(f"目录 {item.display_name} 仅建立索引，未递归读取。")
                continue
            extension = Path(item.display_name).suffix.casefold()
            if extension == ".pdf":
                content = self._pdf_text(item.path)
                if not content.strip():
                    warnings.append(f"PDF {item.display_name} 未提取到文字，可能是扫描版文件。")
                    continue
                content = content[:MAX_EXTRACTED_CHARS]
            else:
                try:
                    content = item.path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    raise ContextGrantError(f"无法读取文件：{item.display_name}") from exc
            content, found = redact_secrets(content)
            if found:
                warnings.append(f"已从 {item.display_name} 中移除疑似敏感信息。")
            remaining = MAX_CONTEXT_CHARS - total
            if remaining <= 0:
                warnings.append("上下文已达到约 32K Token 限制，其余内容未发送。")
                break
            clipped = content[:remaining]
            if len(clipped) < len(content):
                warnings.append(f"{item.display_name} 内容过长，已截断。")
            sections.append(
                f"<authorized_context file={item.display_name!r}>\n{clipped}\n</authorized_context>"
            )
            total += len(clipped)
        return ContextBundle("\n\n".join(sections), names, warnings)

    @staticmethod
    def _pdf_text(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ContextGrantError("PDF 读取组件不可用。") from exc
        try:
            reader = PdfReader(path)
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ContextGrantError(f"无法解析 PDF：{path.name}") from exc
