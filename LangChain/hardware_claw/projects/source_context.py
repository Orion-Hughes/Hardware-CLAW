"""Exact, bounded source excerpts. Line numbers are metadata, never added to text."""
from ..coordinator.store import WorkflowError


def line_excerpt(content, start_line=1, end_line=None, *, max_characters=16000):
    lines = content.splitlines(keepends=True)
    total = len(lines)
    if start_line < 1 or start_line > max(1, total) or (end_line is not None and end_line < start_line):
        raise WorkflowError('INVALID_SOURCE_RANGE', '行号从 1 开始，end_line 包含末行，范围不能超过文件。')
    end = min(end_line if end_line is not None else total, total)
    selected, size = [], 0
    for line in lines[start_line - 1:end]:
        if size + len(line) > max_characters:
            if not selected:
                raise WorkflowError('SOURCE_LINE_TOO_LONG', '这一行超过读取预算；请让生成阶段处理完整文件。')
            break
        selected.append(line)
        size += len(line)
    actual_end = start_line + len(selected) - 1
    return {'content': ''.join(selected), 'unit': 'lines', 'start_line': start_line,
            'end_line': actual_end, 'total_lines': total,
            'line_character_counts': [len(line.rstrip('\r\n')) for line in selected],
            'partial': start_line > 1 or actual_end < total,
            'next_start_line': actual_end + 1 if actual_end < total else None}
