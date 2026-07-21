from __future__ import annotations

from pathlib import Path, PurePath

from prompt_architect.schemas import (
    ContextCategory,
    ContextItem,
    ContextManifest,
    Language,
    TaskSpec,
)


class ContextManager:
    IGNORED_PARTS = {".git", "build", "dist", "logs", "generated", "node_modules", "__pycache__"}
    REFERENCE_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"}
    OPTIONAL_EXTENSIONS = {".md", ".csv", ".xls", ".xlsx"}

    def build(self, task: TaskSpec, *, base_dir: Path | None = None) -> ContextManifest:
        base = (base_dir or Path.cwd()).resolve()
        items: list[ContextItem] = []
        for raw_path in task.available_files:
            pure = PurePath(raw_path.replace("\\", "/"))
            lower_parts = {part.casefold() for part in pure.parts}
            extension = pure.suffix.casefold()
            if lower_parts & self.IGNORED_PARTS:
                category = ContextCategory.IGNORED
                purpose = self._text(task, "避免读取生成物、缓存或日志。", "Avoid generated, cached, or log content.")
                read_when = None
            elif extension in self.REFERENCE_EXTENSIONS:
                category = ContextCategory.REFERENCE_ONLY
                purpose = self._text(task, "按需引用相关章节，不要默认完整读取。", "Reference relevant sections on demand; do not read the whole file by default.")
                read_when = self._text(task, "只有当前阶段需要其中的事实或接口时读取。", "Read only when the current stage needs a fact or interface from it.")
            elif extension in self.OPTIONAL_EXTENSIONS:
                category = ContextCategory.OPTIONAL
                purpose = self._text(task, "需要补充背景或数据时读取。", "Read when additional background or data is needed.")
                read_when = self._text(task, "现有必需上下文不足时。", "When required context is insufficient.")
            else:
                category = ContextCategory.REQUIRED
                purpose = self._text(task, "与本次任务直接相关，应在修改前读取。", "Directly relevant; read before making changes.")
                read_when = None

            candidate = Path(raw_path)
            resolved = candidate if candidate.is_absolute() else base / candidate
            items.append(
                ContextItem(
                    path=raw_path,
                    category=category,
                    purpose=purpose,
                    read_when=read_when,
                    exists=resolved.exists(),
                )
            )

        notes: list[str] = []
        missing_required = [item.path for item in items if item.category == ContextCategory.REQUIRED and item.exists is False]
        if missing_required:
            notes.append(
                self._text(task, "以下必需路径当前不存在：", "The following required paths do not currently exist: ")
                + ", ".join(missing_required)
            )
        if not items:
            notes.append(
                self._text(task, "未提供具体文件路径；目标 AI 应只读取完成任务所需的最小上下文。", "No file paths were supplied; the target AI should load only the minimum context needed.")
            )
        return ContextManifest(items=items, notes=notes)

    @staticmethod
    def _text(task: TaskSpec, zh: str, en: str) -> str:
        return zh if task.language == Language.ZH_CN else en

    def render_markdown(self, task: TaskSpec, manifest: ContextManifest) -> str:
        title = "# 项目上下文清单" if task.language == Language.ZH_CN else "# Context Manifest"
        labels = {
            ContextCategory.REQUIRED: ("必须读取", "Required"),
            ContextCategory.OPTIONAL: ("需要时读取", "Optional"),
            ContextCategory.REFERENCE_ONLY: ("仅供参考", "Reference only"),
            ContextCategory.IGNORED: ("本次忽略", "Ignored"),
        }
        lines = [title, ""]
        for category in ContextCategory:
            label = labels[category][0 if task.language == Language.ZH_CN else 1]
            lines.extend([f"## {label}", ""])
            selected = manifest.by_category(category)
            if not selected:
                lines.extend(["- （无）" if task.language == Language.ZH_CN else "- None", ""])
                continue
            for item in selected:
                existence = ""
                if item.exists is False:
                    existence = "（当前不存在）" if task.language == Language.ZH_CN else " (not currently found)"
                lines.append(f"- `{item.path}`{existence} — {item.purpose}")
                if item.read_when:
                    prefix = "读取条件" if task.language == Language.ZH_CN else "Read when"
                    lines.append(f"  - {prefix}: {item.read_when}")
            lines.append("")
        if manifest.notes:
            lines.extend(["## 说明" if task.language == Language.ZH_CN else "## Notes", ""])
            lines.extend(f"- {note}" for note in manifest.notes)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
