"""Native file-picker launcher for the local asset viewer."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


HERE = Path(__file__).resolve().parent
SETTINGS = HERE / 'output' / 'launcher.json'
DEFAULT_ROOT = HERE.parent / 'test' / 'sac' / 'extracted'
EXTRACTOR = HERE / 'tools' / 'extract_sac.py'
sys.path.insert(0, str(EXTRACTOR.parent))
from archive_support import iso_files


def identify(iso):
    with Path(iso).open('rb') as stream:
        entries = iso_files(stream, Path(iso).stat().st_size)
        config = next((r for r in entries if r[0].as_posix().upper() == 'SYSTEM.CNF'), None)
        if not config or config[2] > 65536:
            raise ValueError('Missing or invalid SYSTEM.CNF.')
        stream.seek(config[1])
        text = stream.read(config[2]).decode('ascii', errors='replace')
        if not re.search(r'BOOT2\s*=.*SCUS_976\.23;1', text, re.I):
            raise ValueError('Choose the supported Secret Agent Clank PS2 USA disc (SCUS-97623).')
        if not any(r[0].as_posix().upper() == 'IMAGE.ZIP' for r in entries):
            raise ValueError('This disc is missing IMAGE.ZIP.')
    return dict(id='ntscu', label='Secret Agent Clank USA')


def extraction_target(iso, destination):
    iso, destination = Path(iso).resolve(), Path(destination).resolve()
    if not iso.is_file():
        raise ValueError('Choose an existing Secret Agent Clank PS2 ISO.')
    region = identify(iso)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Choose a new or empty extraction folder. To reuse extracted assets, use Open existing extraction.')
    return iso, destination, region


def existing_root(folder):
    root = Path(folder).resolve()
    for name in ('manifest.json', 'disc/SYSTEM.CNF'):
        if not (root / name).is_file():
            raise ValueError(f'This extraction is incomplete: missing {name}. Choose the folder containing disc, image and unpacked.')
    config = (root / 'disc/SYSTEM.CNF').read_text(encoding='ascii', errors='replace')
    if not re.search(r'BOOT2\s*=.*SCUS_976\.23;1', config, re.I):
        raise ValueError('This is not a supported Secret Agent Clank PS2 extraction.')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('errors'):
        raise ValueError('The extraction manifest reports errors. Complete extraction before opening it.')
    for key in ('files', 'zip_entries', 'archives'):
        if not isinstance(manifest.get(key), list) or not manifest[key]:
            raise ValueError(f'This extraction is incomplete: missing {key} records.')
    if not any((root / 'image/Levels').glob('*/*.cooked')):
        raise ValueError('This extraction is missing cooked level assets.')
    for entry in manifest['archives']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid archive path in extraction manifest.')
        for name in ('payload.bin', 'manifest.json'):
            if not (root / 'unpacked' / relative / name).is_file():
                raise ValueError(f'This extraction is incomplete: missing {relative}/{name}.')
    return root


class Launcher:
    def __init__(self, window):
        self.window = window
        self.events = queue.Queue()
        self.process = None
        self.busy = False
        self.url = None
        self.generation = 0
        self.cancelled = threading.Event()
        self.process_lock = threading.Lock()
        self.iso = tk.StringVar()
        self.destination = tk.StringVar()
        self.status = tk.StringVar(value='Choose an ISO to extract, or open an existing extraction.')
        try:
            self.recent = json.loads(SETTINGS.read_text()).get('recent', [])[:10]
        except (OSError, ValueError, AttributeError):
            self.recent = []
        self.recent = [p for p in self.recent if isinstance(p, str)]
        if not self.recent and (DEFAULT_ROOT / 'manifest.json').is_file():
            self.recent = [str(DEFAULT_ROOT)]
        window.title('Secret Agent Clank Asset Viewer')
        window.geometry('820x570')
        window.minsize(660, 470)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Secret Agent Clank Asset Viewer', font=('', 18, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Extract a PS2 ISO once, then browse levels, mobys, textures and animations.').pack(anchor='w', pady=(6, 18))
        self.controls = []
        for title, variable, action in [('ISO', self.iso, self.choose_iso), ('Extraction folder', self.destination, self.choose_destination)]:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=title, width=19).pack(side='left')
            entry = ttk.Entry(row, textvariable=variable)
            entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
            button = ttk.Button(row, text='Browse...', command=action)
            button.pack(side='right')
            self.controls.extend((entry, button))
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        for label, action in [('Extract and open', self.extract), ('Open existing extraction...', self.choose_existing)]:
            button = ttk.Button(row, text=label, command=action)
            button.pack(side='left', padx=(0, 8))
            self.controls.append(button)
        self.browser = ttk.Button(row, text='Open browser', command=lambda: webbrowser.open(self.url), state='disabled')
        self.browser.pack(side='right')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, text='Recent folders', width=19).pack(side='left')
        self.history = ttk.Combobox(row, values=self.recent, state='readonly')
        self.history.pack(side='left', fill='x', expand=True, padx=(0, 8))
        if self.recent:
            self.history.current(0)
        button = ttk.Button(row, text='Open', command=lambda: self.open_existing(self.history.get()))
        button.pack(side='right')
        self.controls.append(button)
        ttk.Label(frame, textvariable=self.status, wraplength=750).pack(anchor='w', pady=4)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=6)
        self.log = ScrolledText(frame, height=12, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True)
        ttk.Label(frame, text='Keep this launcher open while using the viewer.').pack(anchor='w', pady=(8, 0))
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.after(100, self.poll)

    def choose_iso(self):
        path = filedialog.askopenfilename(initialdir='D:/PS2/ISOs' if Path('D:/PS2/ISOs').is_dir() else str(HERE), parent=self.window, title='Choose Secret Agent Clank PS2 ISO', filetypes=[('PS2 ISO', '*.iso'), ('All files', '*.*')])
        if path:
            self.iso.set(path)
            if not self.destination.get():
                self.destination.set(str(HERE / 'data' / (Path(path).stem + '-extracted')))

    def choose_destination(self):
        path = filedialog.askdirectory(parent=self.window, title='Choose or create an empty extraction folder', mustexist=False)
        if path:
            self.destination.set(path)

    def choose_existing(self):
        path = filedialog.askdirectory(parent=self.window, title='Choose extracted game folder')
        if path:
            self.open_existing(path)

    def extract(self):
        try:
            if not self.iso.get().strip() or not self.destination.get().strip():
                raise ValueError('Choose both an ISO and an extraction folder.')
            iso, root, region = extraction_target(self.iso.get(), self.destination.get())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('Cannot extract', str(exc), parent=self.window)
            return
        commands = [([str(EXTRACTOR), str(iso), '--output', str(root)], f'Extracting {region["label"]} disc, textures and WADs...')]
        self.start(root, commands)

    def open_existing(self, path):
        if not path:
            return
        try:
            root = existing_root(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('Cannot open extraction', str(exc), parent=self.window)
            return
        self.start(root, [])

    def start(self, root, commands):
        if self.busy:
            return
        self.stop_server()
        self.cancelled = threading.Event()
        self.busy = True
        self.url = None
        self.generation += 1
        for control in self.controls:
            control.configure(state='disabled')
        self.browser.configure(state='disabled')
        self.progress.start()
        self.status.set('Preparing assets...')
        threading.Thread(target=self.work, args=(root, commands, self.generation, self.cancelled), daemon=True).start()

    def work(self, root, commands, generation, cancelled):
        def emit(event, value):
            self.events.put((generation, event, value))
        try:
            for args, status in commands:
                emit('status', status)
                self.run(args, emit=emit, cancelled=cancelled)
            existing_root(root)
            emit('status', 'Preparing previews (first launch takes longer)...')
            output = HERE / 'output' if root == DEFAULT_ROOT.resolve() else root / '.viewer'
            self.run([str(HERE / 'browse.py'), '--root', str(root), '--out', str(output), '--port', '0'], root, emit, cancelled)
        except Exception as exc:
            emit('error', str(exc))
        finally:
            emit('done', None)

    def run(self, args, root=None, emit=None, cancelled=None):
        with self.process_lock:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError('Operation stopped.')
            process = subprocess.Popen([sys.executable, '-u', '-B', *args], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            self.process = process
        with process.stdout:
            for line in process.stdout:
                emit('log', line)
                match = re.match(r'Browse (http://127\.0\.0\.1:\d+)', line)
                if root is not None and match:
                    emit('ready', (root, match[1]))
        if process.wait():
            raise RuntimeError(f'{Path(args[0]).name} failed. See the log above. Extracted files have been retained.')

    def poll(self):
        for _ in range(200):
            try:
                generation, event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            if event == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', value)
                self.log.see('end')
                self.log.configure(state='disabled')
            elif event == 'status':
                self.status.set(value)
            elif event == 'ready':
                self.busy = False
                for control in self.controls:
                    control.configure(state='normal')
                root, self.url = value
                self.status.set(f'Ready: {root}')
                self.progress.stop()
                self.browser.configure(state='normal')
                self.recent = [str(root)] + [p for p in self.recent if p != str(root)]
                self.recent = self.recent[:10]
                self.history.configure(values=self.recent)
                self.history.current(0)
                try:
                    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                    SETTINGS.write_text(json.dumps({'recent': self.recent}, indent=2))
                except OSError as exc:
                    self.events.put((self.generation, 'log', f'Could not save recent folders: {exc}\n'))
                webbrowser.open(self.url)
            elif event == 'error':
                self.status.set('Could not finish. See the log for details.')
                messagebox.showerror('Asset viewer', value, parent=self.window)
            elif event == 'done':
                if self.url:
                    self.status.set('Viewer stopped. Open an extraction to start it again.')
                self.url = None
                self.busy = False
                self.progress.stop()
                for control in self.controls:
                    control.configure(state='normal')
                self.browser.configure(state='disabled')
        self.window.after(100, self.poll)

    def stop_server(self):
        with self.process_lock:
            self.cancelled.set()
            process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def close(self):
        if self.busy and not self.url:
            if not messagebox.askyesno('Stop extraction?', 'Extraction is still running. Stop it and close? Partial files will remain.', parent=self.window):
                return
        self.stop_server()
        self.window.destroy()


def main():
    window = tk.Tk()
    Launcher(window)
    window.mainloop()


if __name__ == '__main__':
    main()
