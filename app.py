import os
import requests
import zipfile
import sqlite3
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog, ttk
from threading import Thread
from time import sleep
from concurrent.futures import ThreadPoolExecutor


class GitHubDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GitHub File Zipper")
        self.geometry("600x400")
        self.token = None
        self.headers = {}
        self.db_init()
        self.create_widgets()

        self.repo_owner = None
        self.repo_name = None
        self.folder_path = None
        self.destination = None
        self.enterprise_url = None

    def db_init(self):
        """Initialize the database for tracking download history."""
        self.conn = sqlite3.connect('download_history.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                                id INTEGER PRIMARY KEY,
                                repo_owner TEXT,
                                repo_name TEXT,
                                folder_path TEXT,
                                destination TEXT,
                                download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()

    def create_widgets(self):
        tk.Label(self, text="Repository Owner:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        tk.Label(self, text="Repository Name:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        tk.Label(self, text="Folder Path (Leave blank for full repo):").grid(row=2, column=0, sticky="e", padx=5,
                                                                             pady=5)
        tk.Label(self, text="Destination:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        tk.Label(self, text="GitHub Enterprise URL (Optional):").grid(row=4, column=0, sticky="e", padx=5, pady=5)

        self.entry_owner = tk.Entry(self)
        self.entry_repo = tk.Entry(self)
        self.entry_folder = tk.Entry(self)
        self.entry_destination = tk.Entry(self)
        self.entry_gh_enterprise = tk.Entry(self)

        self.entry_owner.grid(row=0, column=1, padx=5, pady=5)
        self.entry_repo.grid(row=1, column=1, padx=5, pady=5)
        self.entry_folder.grid(row=2, column=1, padx=5, pady=5)
        self.entry_destination.grid(row=3, column=1, padx=5, pady=5)
        self.entry_gh_enterprise.grid(row=4, column=1, padx=5, pady=5)

        tk.Button(self, text="Select Destination", command=self.select_destination).grid(row=3, column=2)
        tk.Button(self, text="Download", command=self.start_download).grid(row=5, column=0, columnspan=3, pady=10)

        self.progress = ttk.Progressbar(self, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=3, pady=5)

        tk.Label(self, text="A Suryanshu Banerjee Production", font=("Arial", 8)).grid(row=7, column=0, columnspan=3,
                                                                                       pady=10)

    def select_destination(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.entry_destination.delete(0, tk.END)
            self.entry_destination.insert(0, folder_selected)

    def start_download(self):
        Thread(target=self.prepare_download).start()

    def prepare_download(self):
        self.repo_owner = self.entry_owner.get().strip()
        self.repo_name = self.entry_repo.get().strip()
        self.folder_path = self.entry_folder.get().strip()
        self.destination = self.entry_destination.get().strip()
        self.enterprise_url = self.entry_gh_enterprise.get().strip()

        if not all([self.repo_owner, self.repo_name, self.destination]):
            messagebox.showerror("Error", "All fields except GitHub Enterprise URL must be filled.")
            return

        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            self.after(0, self.prompt_for_token)
        else:
            self.run_download()

    def prompt_for_token(self):
        self.token = simpledialog.askstring("GitHub Token", "Enter your GitHub token (optional):", show='*')
        self.run_download()

    def run_download(self):
        if not self.validate_repo():
            return

        self.headers = {
            'Authorization': f'token {self.token}'} if self.token else {}  # Only add header if token is provided
        self.download_files()

    def validate_repo(self):
        base_url = self.enterprise_url if self.enterprise_url else "https://api.github.com"
        url = f"{base_url}/repos/{self.repo_owner}/{self.repo_name}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.RequestException:
            messagebox.showerror("Error", "Repository not found or access denied!")
            return False

    def download_files(self):
        os.makedirs(self.destination, exist_ok=True)
        zip_file_path = os.path.join(self.destination, f'{self.folder_path.strip("/").replace("/", "_")}_files.zip')

        base_url = self.enterprise_url if self.enterprise_url else "https://api.github.com"
        folder_url = f"{base_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{self.folder_path}" if self.folder_path else f"{base_url}/repos/{self.repo_owner}/{self.repo_name}/zipball"

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                    if self.folder_path:
                        files = self.fetch_files(folder_url)
                        self.progress['maximum'] = len(files)
                        futures = [executor.submit(self.download_and_write_file, zipf, file) for file in files]
                        for i, future in enumerate(futures):
                            future.result()
                            self.update_progress(i + 1)
                    else:
                        self.download_entire_repo(folder_url, zip_file_path)

            self.track_download()
            messagebox.showinfo("Success", f"Files downloaded and zipped at:\n{zip_file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Download failed: {e}")

    def fetch_files(self, url, retry_count=3):
        while retry_count > 0:
            try:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                retry_count -= 1
                sleep(2)
                if retry_count == 0:
                    raise e

    def download_entire_repo(self, url, zip_file_path):
        response = requests.get(url, headers=self.headers, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0

        with open(zip_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # Update progress only if total_size is greater than zero
                    if total_size > 0:
                        self.update_progress((downloaded_size / total_size) * 100)
                    else:
                        # Skip progress update if content-length is zero
                        self.update_progress(0)  # Or leave this out if you'd rather have no progress updates

    def download_and_write_file(self, zipf, file):
        if file['type'] == 'file':
            response = requests.get(file['download_url'], headers=self.headers)
            response.raise_for_status()
            zipf.writestr(file['path'], response.content)
        elif file['type'] == 'dir':
            subfiles = self.fetch_files(file['url'])
            for subfile in subfiles:
                self.download_and_write_file(zipf, subfile)

    def update_progress(self, value):
        """Update progress based on download progress percentage."""
        self.progress['value'] = value
        self.update_idletasks()

    def track_download(self):
        self.cursor.execute("INSERT INTO history (repo_owner, repo_name, folder_path, destination) VALUES (?, ?, ?, ?)",
                            (self.repo_owner, self.repo_name, self.folder_path, self.destination))
        self.conn.commit()


if __name__ == "__main__":
    app = GitHubDownloader()
    app.mainloop()
