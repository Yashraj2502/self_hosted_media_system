"""
YouTube Download Manager
A system to download, organize, and manage YouTube videos
"""

from multiprocessing import managers
import yt_dlp
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import re

class YouTubeDownloadManager:
    def __init__(self, base_path: str = "./media", db_path: str = "./youtube_library.db"):
        self.base_path = Path(base_path)
        self.db_path = db_path
        self.setup_directories()
        self.setup_database()

    def setup_directories(self):
        """Create necessary folder structure"""
        (self.base_path / "videos").mkdir(parents=True, exist_ok=True)
        (self.base_path / "shorts").mkdir(parents=True, exist_ok=True)
        (self.base_path / "thumbnails").mkdir(parents=True, exist_ok=True)

    def setup_database(self):
        """Initialize SQLite database for metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Main videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                uploader TEXT,
                upload_date TEXT,
                duration INTEGER,
                description TEXT,
                view_count INTEGER,
                is_short BOOLEAN DEFAULT 0,
                file_path TEXT,
                thumbnail_path TEXT,
                download_date TEXT,
                original_url TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                tag TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)

        # Playlists table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id TEXT UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                created_date TEXT
            )
        """)

        # Playlist items junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                playlist_id INTEGER,
                videos_id INTEGER,
                position INTEGER,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id)
                FOREIGN KEY (videos_id) REFERENCES videos(id)
            )
        """)

        conn.commit()
        conn.close()

    def sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename"""
        # Replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Limit length
        return filename[:200]

    def is_youtube_short(self, info: dict) -> bool :
        """Determine if video is a YouTube Short"""
        # Shorts are typically <60 seconds and have specific aspect ratio
        duration = info.get('duration', 0)
        width = info.get('width', 0)
        height = info.get('height', 0)

        # Check duration and aspect ration (9:16 for shorts)
        is_short_duration = duration and duration <= 60
        is_vertical = height > width if (height and width) else False

        # Also check URL pattern
        url = info.get('web_page_url', '')
        is_short_url = '/shorts/' in url

        return is_short_url or (is_short_duration and is_vertical)

    def download_video(
            self,
            url: str,
            custom_tags: Optional[List[str]] = None,
            playlist_name: Optional[str] = None
        ) -> Dict:
        """Download a single video and save metadata"""

        # First, extract info without downloading
        ydl_info_opts = {
            'quiet': True,
            'no_warnings': True
        }

        with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                return {'status': 'error', 'message': str(e)}

        # Determine if short or regular video
        is_short = self.is_youtube_short(info)
        video_type = "shorts" if is_short else "videos"

        # Prepare output path
        uploader = self.sanitize_filename(info.get('uploader', 'Unknown'))
        title = self.sanitize_filename(info.get('title', 'Untitled'))

        output_dir = self.base_path / video_type / uploader
        output_dir.mkdir(parents=True, exist_ok=True)

        output_template = str(output_dir / f"{title}.%(ext)s")

        # Scenario 1: Maximum quality under 1080p (recommended for Pi)
        # 'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'

        # Scenario 2: Save space (lower quality audio)
        # 'format': 'bestvideo[height<=720]+bestaudio[abr<=128]/best[height<=720]'

        # Scenario 3: Audio only (for music)
        # 'format': 'bestaudio[ext=m4a]/bestaudio'

        # Scenario 4: Fastest download (pre-merged, might not be best quality)
        # 'format': 'best[height<=1080]'

        # Scenario 5: Maximum everything (not recommended for Pi)
        # 'format': 'bestvideo+bestaudio/best'


        # Download options
        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]', # Limit to 1080p max (saves bandwidth & storage)
            'concurrent_fragment_downloads': 1, # Don't overwhelm the Pi
            'ratelimit': 5000000, # 5MB/s limit (optiona, prevents network congestion)
            'outtmpl': output_template,
            'writethumbnail': True,
            'writeinfojson': False,
            'writesubtitles': True,
            'writeautomaticsub': False,
            'postprocessors': [
                # {
                #     'key': 'FFmpegVideoConvertor',
                #     'preferedformat': 'mp4',
                # },
                {
                    'key': 'FFmpegEmbedSubtitle',
                },
                # {
                #     'key': 'EmbedThumbnail',
                # }
            ],
            'progress_hooks': [self.progress_hook],
        }

        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
            except Exception as e:
                return {'status': 'error', 'message': str(e)}

        # Save to database
        video_data = {
            'video_id': info.get('id'),
            'title': info.get('title'),
            'uploader': info.get('uploader'),
            'upload_date': info.get('upload_date'),
            'duration': info.get('duration'),
            'description': info.get('description'),
            'view_count': info.get('view_count'),
            'is_short': is_short,
            'file_path': downloaded_file,
            'thumbnail_path': info.get('thumbnail'),
            'download_date': datetime.now().isoformat(),
            'original_url': url,
            'status': 'completed'
        }

        db_video_id = self.save_to_database(video_data, custom_tags, playlist_name)

        return {
            'status': 'success',
            'video_id': info.get('id'),
            'title': info.get('title'),
            'is_short': is_short,
            'db_id': db_video_id
        }

    def download_playlist(self, playlist_url: str, custom_tags: Optional[List[str]] = None) -> Dict:
        """Download all videos from a playlist"""

        # Extract playlist info
        ydl_opts = {
            'extract_flat': True,
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                playlist_info = ydl.extract_info(playlist_url, download=False)
            except Exception as e:
                return {'status': 'error', 'message': str(e)}

        playlist_name = playlist_info.get('title', 'Unknown Playlist')
        playlist_id = playlist_info.get('id')

        # Save playlist to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO playlists (playlist_id, name, description, created_date)
            VALUES (?, ?, ?, ?)
        """, (playlist_id, playlist_name, playlist_info.get('description', ''),
              datetime.now().isoformat()))
        conn.commit()

        cursor.execute("SELECT id FROM playlists WHERE playlist_id = ?", (playlist_id, ))
        db_playlist_id = cursor.fetchone()[0]
        conn.close()

        # Download each video in playlist
        entries = playlist_info.get('entries', [])
        results = []

        for idx, entry in enumerate(entries):
            video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
            print(f"Downloading {idx + 1}/{len(entries)}: {entry.get('title')}")

            result = self.download_video(video_url, custom_tags, playlist_name)

            # Link to playlist
            if result['status'] == 'success':
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO playlist_items (playlist_id, videos_id, position)
                    VALUES (?, ?, ?)
                """, (db_playlist_id, result['db_id'], idx))
                conn.commit()
                conn.close()

            results.append(result)

        return {
            'status': 'success',
            'playlist_name': playlist_name,
            'total_videos': len(entries),
            'results': results
        }

    def save_to_database(
            self,
            video_data: Dict,
            tags: Optional[List[str]] = None,
            playlist_name: Optional[str] = None
        ) -> int:
        """Save video metadata to database"""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Insert video
        cursor.execute("""
            INSERT OR REPLACE INTO videos 
            (video_id, title, uploader, upload_date, duration, description, 
             view_count, is_short, file_path, thumbnail_path, download_date, 
             original_url, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_data.get('video_id'),
            video_data.get('title'),
            video_data.get('uploader'),
            video_data.get('upload_date'),
            video_data.get('duration'),
            video_data.get('description'),
            video_data.get('view_count'),
            video_data.get('is_short', False),
            video_data.get('file_path'),
            video_data.get('thumbnail_path'),
            video_data.get('download_date'),
            video_data.get('original_url'),
            video_data.get('status', 'completed')
        ))

        video_db_id = cursor.lastrowid

        # Add default YouTube tag
        all_tags = ['YouTube']
        if tags:
            all_tags.extend(tags)

        for tag in all_tags:
            cursor.execute("""
                INSERT INTO tags (video_id, tag)
                VALUES (?, ?)
            """, (video_db_id, tag))

        conn.commit()
        conn.close()

        return video_db_id

    def progress_hook(self, d):
        """Display download progress"""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            print(f"\rDownloading: {percent} at {speed}", end=' ')
        elif d['status'] == 'finished':
            print(f"\nDownload complete, processing...")

    def get_all_videos(self, is_short: Optional[bool] = None) -> List[Dict]:
        """Retrieve all videos from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if is_short is None:
            cursor.execute("SELECT * FROM videos WHERE status = 'completed'")
        else:
            cursor.execute("SELECT * FROM videos WHERE status = 'completed' AND is_short = ?", (is_short,))

        columns = [description[0] for description in cursor.description]
        videos = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return videos

    def search_videos(self, query: str) -> List[Dict]:
        """Search videos by title or uploader"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM videos
            WHERE (title LIKE ? OR uploader LIKE ?)
            AND status = 'completed
        """, (f'%{query}%', f'%{query}%'))

        columns = [description[0] for description in cursor.description]
        videos = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return videos


# Example usage
if __name__ == '__main__':
    # Initialize manager
    manager = YouTubeDownloadManager(base_path="./youtube_media")

    # # Download a single video with custom tags
    # result = manager.download_video(
    #     "https://www.youtube.com/watch?v=zGUaiLanzAc",
    #     custom_tags=["Podcast", "Spiritual", "TRS"]
    # )
    # print(f"Download result: {result}")

    # # Download a playlist
    playlist_result = manager.download_playlist(
        "https://www.youtube.com/playlist?list=PLxxxxxxxx",
        custom_tags=["Tutorial", "Python"]
    )

    # Get all regular videos (not shorts)
    videos = manager.get_all_videos(is_short=False)
    print(f"\nTotal videos: {len(videos)}")

    # Get all shorts
    shorts = manager.get_all_videos(is_short=True)
    print(f"Total shorts: {len(shorts)}")