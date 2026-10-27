"""Read-only in-memory file interface for unchanged dataset-quality helpers.
No path discovery, writes or fallback to the host filesystem.
"""
import fnmatch
import io

class SnapshotFile:
    def __init__(self, name, data):
        self.name, self.data = name, data
    def is_file(self):return self.data is not None
    def read_bytes(self):
        if self.data is None:raise FileNotFoundError(self.name)
        return self.data
    def open(self, mode='r', encoding=None):
        if mode == 'rb':return io.BytesIO(self.read_bytes())
        if mode == 'r':return io.StringIO(self.read_text(encoding or 'utf-8'))
        raise ValueError('Snapshot access is read-only.')
    def read_text(self, encoding='utf-8'):return self.read_bytes().decode(encoding)
    def __lt__(self, other):return self.name < other.name
    def __str__(self):return self.name

class SnapshotDirectory:
    def __init__(self, name, files):
        self.name, self.files = name, dict(files)
    def __truediv__(self, name):return SnapshotFile(name, self.files.get(name))
    def iterdir(self):return [self / name for name in sorted(self.files)]
    def glob(self, pattern):return [self / name for name in sorted(self.files) if fnmatch.fnmatchcase(name, pattern)]
