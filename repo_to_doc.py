import argparse
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List, Set, Optional, Tuple, Iterator, IO

import pathspec
from git import Repo

# Constants for filtering
SYSTEM_DIRS = {
    ".git", "node_modules", "venv", "env", "__pycache__", 
    ".pytest_cache", "dist", "build", ".idea", ".vscode"
}
LOCK_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", 
    "poetry.lock", "Gemfile.lock"
}

def generate_tree(dir_path: Path, filtered_files: Set[Path], current_dir: Optional[Path] = None, prefix: str = "") -> str:
    """Generates a visual directory tree for filtered files."""
    if current_dir is None:
        current_dir = dir_path
        
    tree_lines = []
    
    # Get all entries in the current directory and sort them
    try:
        entries = sorted(os.listdir(current_dir))
    except (PermissionError, FileNotFoundError):
        return ""
    
    # Filter entries that are actually part of the documentation path
    valid_dirs = []
    valid_files = []
    
    for entry in entries:
        full_path = current_dir / entry
        if full_path.is_dir():
            # Check if any file in filtered_files is under this directory
            if any(str(f).startswith(str(full_path)) for f in filtered_files):
                valid_dirs.append(entry)
        elif full_path in filtered_files:
            valid_files.append(entry)
            
    valid_entries = valid_dirs + valid_files
    
    for i, entry in enumerate(valid_entries):
        is_last = (i == len(valid_entries) - 1)
        connector = "└── " if is_last else "├── "
        tree_lines.append(f"{prefix}{connector}{entry}")
        
        full_path = current_dir / entry
        if full_path.is_dir():
            extension = "    " if is_last else "│   "
            sub_tree = generate_tree(dir_path, filtered_files, full_path, prefix + extension)
            if sub_tree:
                tree_lines.append(sub_tree)
            
    return "\n".join(tree_lines)

def get_word_count(text: str) -> int:
    """Counts words in a string."""
    return len(text.split())

class DocWriter:
    def __init__(self, base_output: str, repo_name: str, split_words: int, total_files: int):
        self.base_output = base_output
        self.repo_name = repo_name
        self.split_words = split_words
        self.total_files = total_files
        self.current_part = 1
        self.current_word_count = 0
        self.file_handle: Optional[IO] = None
        self.part_word_counts: List[int] = []
        
    def _get_filename(self) -> str:
        name, ext = os.path.splitext(self.base_output)
        return f"{name}_part{self.current_part}{ext}"

    def write_header(self, tree_str: str = ""):
        filename = self._get_filename()
        self.file_handle = open(filename, "w", encoding="utf-8")
        
        if self.current_part == 1:
            header = (
                f"Repository: {self.repo_name}\n"
                f"Files analyzed: {self.total_files}\n"
                f"Estimated words: [TOTAL_WORDS_PLACEHOLDER]\n\n"
                f"Directory structure:\n"
                f"{tree_str}\n"
                f"{'='*48}\n\n"
            )
        else:
            header = (
                f"[Repository: {self.repo_name} | Part {self.current_part}]\n"
                f"(Это продолжение исходного кода. Структуру директорий проекта см. в Части 1)\n"
                f"{'='*48}\n\n"
            )
        
        self.file_handle.write(header)
        self.current_word_count = get_word_count(header)

    def write_content(self, content: str):
        words = get_word_count(content)
        
        # If writing this content exceeds the limit, and we've already written something substantial
        if self.current_word_count + words > self.split_words and self.current_word_count > 0:
            self.close_current_part()
            self.current_part += 1
            self.write_header()
            
        if self.file_handle:
            self.file_handle.write(content)
            self.current_word_count += words

    def close_current_part(self):
        if self.file_handle:
            self.part_word_counts.append(self.current_word_count)
            self.file_handle.close()
            self.file_handle = None

    def finalize(self, total_words: int):
        self.close_current_part()
        # Update placeholder in part 1
        part1_file = f"{os.path.splitext(self.base_output)[0]}_part1{os.path.splitext(self.base_output)[1]}"
        if os.path.exists(part1_file):
            with open(part1_file, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("[TOTAL_WORDS_PLACEHOLDER]", str(total_words))
            with open(part1_file, "w", encoding="utf-8") as f:
                f.write(content)

def main():
    parser = argparse.ArgumentParser(description="RepoToDoc - Repository to Documentation utility")
    parser.add_argument("--url", help="GitHub repository URL")
    parser.add_argument("--path", help="Local repository path")
    parser.add_argument("--output", default="repo_doc.txt", help="Output filename (default: repo_doc.txt)")
    parser.add_argument("--extensions", help="Comma-separated list of extensions (e.g., .py,.js)")
    parser.add_argument("--max-size", type=int, default=200, help="Max file size in KB (default: 200)")
    parser.add_argument("--split-words", type=int, default=128000, help="Max words per output file (default: 500000)")
    
    args = parser.parse_args()

    # Validation
    if not args.url and not args.path:
        print("КРИТИЧЕСКАЯ ОШИБКА: Необходимо указать --url или --path")
        sys.exit(1)
    if args.url and args.path:
        print("КРИТИЧЕСКАЯ ОШИБКА: Укажите только один источник (--url ИЛИ --path)")
        sys.exit(1)

    work_dir = None
    temp_dir_obj = None
    
    try:
        if args.url:
            print(f"Клонирование репозитория {args.url}...")
            temp_dir_obj = tempfile.TemporaryDirectory()
            work_dir = Path(temp_dir_obj.name)
            try:
                Repo.clone_from(args.url, work_dir)
            except Exception as e:
                print(f"ОШИБКА СЕТИ: Невозможно клонировать репозиторий. {e}")
                sys.exit(1)
            repo_name = args.url.rstrip("/").split("/")[-1]
        else:
            work_dir = Path(args.path).resolve()
            if not work_dir.exists() or not work_dir.is_dir():
                print("КРИТИЧЕСКАЯ ОШИБКА: Директория не найдена")
                sys.exit(1)
            repo_name = work_dir.name

        # Filters
        allowed_exts = set(args.extensions.split(",")) if args.extensions else None
        
        # Load .gitignore if exists
        gitignore_path = work_dir / ".gitignore"
        spec = None
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                spec = pathspec.PathSpec.from_lines('gitwildmatch', f.readlines())

        # Pass 1: Collect filtered files
        filtered_files = []
        for root, dirs, files in os.walk(work_dir):
            rel_root = Path(root).relative_to(work_dir)
            
            # Filter directories
            dirs[:] = [d for d in dirs if d not in SYSTEM_DIRS]
            if spec:
                dirs[:] = [d for d in dirs if not spec.match_file(str(rel_root / d))]
            
            for f in files:
                rel_file_path = rel_root / f
                full_path = Path(root) / f
                
                # Check .gitignore
                if spec and spec.match_file(str(rel_file_path)):
                    continue
                
                # Check Lock files
                if f in LOCK_FILES:
                    continue
                
                # Check extensions
                if allowed_exts and full_path.suffix not in allowed_exts:
                    continue
                
                filtered_files.append(full_path)

        filtered_files.sort()
        tree_str = generate_tree(work_dir, set(filtered_files))
        
        # Pass 2: Process files and write documentation
        writer = DocWriter(args.output, repo_name, args.split_words, len(filtered_files))
        writer.write_header(tree_str)
        
        total_words = 0
        skipped_count = 0
        processed_count = 0
        
        for file_path in filtered_files:
            rel_path = file_path.relative_to(work_dir)
            
            file_header = (
                f"{'='*48}\n"
                f"FILE: {rel_path}\n"
                f"{'='*48}\n"
            )
            
            # Max size check
            size_kb = file_path.stat().st_size / 1024
            if size_kb > args.max_size:
                content = file_header + f"```\n[СОДЕРЖИМОЕ ПРОПУЩЕНО: Размер файла превышает лимит --max-size]\n```\n\n"
                writer.write_content(content)
                total_words += get_word_count(content)
                skipped_count += 1
                continue

            try:
                # Determine language for markdown block if possible
                lang = file_path.suffix.lstrip(".") if file_path.suffix else ""
                
                # Write header and start of markdown block
                writer.write_content(file_header + f"```{lang}\n")
                
                # Streaming read: process line by line or in chunks to stay low-RAM
                with open(file_path, "r", encoding="utf-8", errors='replace') as f:
                    for line in f:
                        writer.write_content(line)
                        total_words += get_word_count(line)
                
                # Close markdown block
                writer.write_content("\n```\n\n")
                processed_count += 1
                
            except (UnicodeDecodeError, PermissionError):
                content = file_header + f"```\n[СОДЕРЖИМОЕ ПРОПУЩЕНО: Бинарный файл или неверная кодировка]\n```\n\n"
                writer.write_content(content)
                total_words += get_word_count(content)
                skipped_count += 1

        writer.finalize(total_words)
        
        # CLI Output
        print("✅ Обход завершен!")
        print(f"📂 Обработано файлов: {processed_count}")
        print(f"🚫 Пропущено (превышен лимит размера или бинарники): {skipped_count}")
        print(f"🧮 Общее количество слов: {total_words}")
        print(f"\n📄 Документация разбита на {writer.current_part} файл(а):")
        for i, count in enumerate(writer.part_word_counts, 1):
            name, ext = os.path.splitext(args.output)
            print(f"- {name}_part{i}{ext} ({count} слов)")

    finally:
        if temp_dir_obj:
            temp_dir_obj.cleanup()

if __name__ == "__main__":
    main()
