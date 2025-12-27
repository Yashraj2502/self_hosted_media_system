"""
Web Interface for YouTube Download Manager using FastAPI
Run with: uvicorn web_interface:app --reload --host 0.0.0.0 --port 8000
"""

"""
Observation:
- DOesn't download when already downloading something (It does. But doesn't show/tell)
- pressing 'Enter' doesn't start the download
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
import sqlite3
from pathlib import Path
import mimetypes

# Import the download manager (assumes previous code is saved as youtube_manager.py)
from youtube_manager import YouTubeDownloadManager

app = FastAPI(title="YouTube Library Manager")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize download manager
manager = YouTubeDownloadManager(base_path="./youtube_media", db_path="./youtube_library.db")

# Pydantic models for API
class VideoDownloadRequest(BaseModel):
    url: HttpUrl
    tags: Optional[List[str]] = []
    
class PlaylistDownloadRequest(BaseModel):
    url: HttpUrl
    tags: Optional[List[str]] = []

class DownloadResponse(BaseModel):
    status: str
    message: str
    task_id: Optional[str] = None

# In-memory task tracking (in production, use Redis or similar)
download_tasks = {}

# API Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main web interface"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>YouTube Library Manager</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .tabs {
                display: flex;
                background: #f5f5f5;
                border-bottom: 2px solid #ddd;
            }
            .tab {
                flex: 1;
                padding: 15px;
                text-align: center;
                cursor: pointer;
                background: #f5f5f5;
                border: none;
                font-size: 16px;
                font-weight: 600;
                transition: all 0.3s;
            }
            .tab:hover { background: #e0e0e0; }
            .tab.active {
                background: white;
                border-bottom: 3px solid #667eea;
                color: #667eea;
            }
            .content {
                padding: 30px;
            }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #333;
            }
            input[type="text"], textarea {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 16px;
                transition: border 0.3s;
            }
            input[type="text"]:focus, textarea:focus {
                outline: none;
                border-color: #667eea;
            }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .status {
                margin-top: 20px;
                padding: 15px;
                border-radius: 8px;
                display: none;
            }
            .status.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .video-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .video-card {
                background: white;
                border: 1px solid #ddd;
                border-radius: 12px;
                overflow: hidden;
                transition: transform 0.3s, box-shadow 0.3s;
                cursor: pointer;
            }
            .video-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            }
            .video-thumbnail {
                width: 100%;
                height: 180px;
                object-fit: cover;
                background: #f0f0f0;
            }
            .video-info {
                padding: 15px;
            }
            .video-title {
                font-weight: 600;
                margin-bottom: 8px;
                color: #333;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            .video-uploader {
                color: #666;
                font-size: 14px;
            }
            .filter-bar {
                display: flex;
                gap: 15px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            .filter-bar input, .filter-bar select {
                flex: 1;
                min-width: 200px;
            }
            .badge {
                display: inline-block;
                padding: 4px 8px;
                background: #667eea;
                color: white;
                border-radius: 4px;
                font-size: 12px;
                margin-right: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📺 YouTube Library Manager</h1>
                <p>Download and organize your YouTube content</p>
            </div>
            
            <div class="tabs">
                <button class="tab active" onclick="switchTab('download')">⬇️ Download</button>
                <button class="tab" onclick="switchTab('videos')">🎬 Videos</button>
                <button class="tab" onclick="switchTab('shorts')">📱 Shorts</button>
                <button class="tab" onclick="switchTab('playlists')">📋 Playlists</button>
            </div>
            
            <div class="content">
                <!-- Download Tab -->
                <div id="download" class="tab-content active">
                    <h2>Download Content</h2>
                    
                    <div class="form-group">
                        <label for="video-url">YouTube URL:</label>
                        <input type="text" id="video-url" 
                               placeholder="https://www.youtube.com/watch?v=... or playlist link">
                    </div>
                    
                    <div class="form-group">
                        <label for="tags">Tags (comma-separated):</label>
                        <input type="text" id="tags" 
                               placeholder="e.g., Tutorial, Python, Programming">
                    </div>
                    
                    <button class="btn" onclick="downloadContent()">⬇️ Download</button>
                    
                    <div id="download-status" class="status"></div>
                </div>
                
                <!-- Videos Tab -->
                <div id="videos" class="tab-content">
                    <h2>Regular Videos</h2>
                    
                    <div class="filter-bar">
                        <input type="text" id="video-search" 
                               placeholder="Search videos..." 
                               oninput="filterVideos(false)">
                        <select id="video-sort" onchange="filterVideos(false)">
                            <option value="recent">Most Recent</option>
                            <option value="title">Title (A-Z)</option>
                            <option value="uploader">Uploader</option>
                        </select>
                    </div>
                    
                    <div id="videos-grid" class="video-grid">
                        <!-- Videos will be loaded here -->
                    </div>
                </div>
                
                <!-- Shorts Tab -->
                <div id="shorts" class="tab-content">
                    <h2>YouTube Shorts</h2>
                    
                    <div class="filter-bar">
                        <input type="text" id="shorts-search" 
                               placeholder="Search shorts..." 
                               oninput="filterVideos(true)">
                    </div>
                    
                    <div id="shorts-grid" class="video-grid">
                        <!-- Shorts will be loaded here -->
                    </div>
                </div>
                
                <!-- Playlists Tab -->
                <div id="playlists" class="tab-content">
                    <h2>Playlists</h2>
                    <div id="playlists-list">
                        <!-- Playlists will be loaded here -->
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function switchTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                });
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Show selected tab
                document.getElementById(tabName).classList.add('active');
                event.target.classList.add('active');
                
                // Load content for the tab
                if (tabName === 'videos') loadVideos(false);
                if (tabName === 'shorts') loadVideos(true);
                if (tabName === 'playlists') loadPlaylists();
            }
            
            async function downloadContent() {
                const url = document.getElementById('video-url').value;
                const tags = document.getElementById('tags').value.split(',').map(t => t.trim());
                const statusDiv = document.getElementById('download-status');
                
                if (!url) {
                    showStatus('error', 'Please enter a URL');
                    return;
                }
                
                statusDiv.style.display = 'block';
                statusDiv.className = 'status';
                statusDiv.textContent = 'Downloading... This may take a while.';
                
                try {
                    const endpoint = url.includes('playlist') ? '/api/download-playlist' : '/api/download-video';
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url, tags })
                    });
                    
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        showStatus('success', result.message || 'Download started successfully!');
                        document.getElementById('video-url').value = '';
                        document.getElementById('tags').value = '';
                    } else {
                        showStatus('error', result.message || 'Download failed');
                    }
                } catch (error) {
                    showStatus('error', 'Error: ' + error.message);
                }
            }
            
            function showStatus(type, message) {
                const statusDiv = document.getElementById('download-status');
                statusDiv.style.display = 'block';
                statusDiv.className = 'status ' + type;
                statusDiv.textContent = message;
            }
            
            async function loadVideos(isShort) {
                const gridId = isShort ? 'shorts-grid' : 'videos-grid';
                const grid = document.getElementById(gridId);

                // Show loading state
                grid.innerHTML = '<p style="padding: 20px; text-align: center;">Loading...</p>';
                
                try {
                    const response = await fetch(`/api/videos?is_short=${isShort}`);
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const videos = await response.json();
                    if (video.length === 0) {
                        grid.innerHTML = '<p style="padding: 20px; text-align: center; color: #666;">No videos yet. Download some to get started!</p>';
                        return;
                    }
                    
                    grid.innerHTML = videos.map(video => `
                        <div class="video-card" onclick="playVideo('${video.id}')">
                            <img class="video-thumbnail" 
                                 src="/api/thumbnail/${video.id}" 
                                 alt="${video.title}"
                                 onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\'%3E%3Crect fill=\\'%23ddd\\' width=\\'100\\' height=\\'100\\'/%3E%3C/svg%3E'">
                            <div class="video-info">
                                <div class="video-title">${video.title}</div>
                                <div class="video-uploader">${video.uploader}</div>
                                ${isShort ? '<span class="badge">Short</span>' : ''}
                            </div>
                        </div>
                    `).join('');
                } catch (error) {
                    grid.innerHTML = '<p>Error loading videos: ' + error.message + '</p>';
                }
            }
            
            async function loadPlaylists() {
                const list = document.getElementById('playlists-list');
                
                try {
                    const response = await fetch('/api/playlists');
                    const playlists = await response.json();
                    
                    list.innerHTML = playlists.map(playlist => `
                        <div style="padding: 20px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 15px;">
                            <h3>${playlist.name}</h3>
                            <p>${playlist.description || 'No description'}</p>
                            <small>Created: ${new Date(playlist.created_date).toLocaleDateString()}</small>
                        </div>
                    `).join('');
                } catch (error) {
                    list.innerHTML = '<p>Error loading playlists</p>';
                }
            }

            function filterVideos(isShort) {
                const searchId = isShort ? 'shorts-search' : 'video-search';
                const sortId = isShort ? null : 'video-sort';
                const gridId = isShort ? 'shorts-grid' : 'videos-grid';
                
                const searchQuery = document.getElementById(searchId).value.toLowerCase();
                const sortBy = sortId ? document.getElementById(sortId).value : 'recent';
                
                // Fetch and filter videos
                fetch(`/api/videos?is_short=${isShort}`)
                    .then(res => res.json())
                    .then(videos => {
                        // Filter by search query
                        let filtered = videos.filter(v => 
                            v.title.toLowerCase().includes(searchQuery) ||
                            v.uploader.toLowerCase().includes(searchQuery)
                        );
                        
                        // Sort
                        if (sortBy === 'title') {
                            filtered.sort((a, b) => a.title.localeCompare(b.title));
                        } else if (sortBy === 'uploader') {
                            filtered.sort((a, b) => a.uploader.localeCompare(b.uploader));
                        } else {
                            // Most recent (default)
                            filtered.sort((a, b) => new Date(b.download_date) - new Date(a.download_date));
                        }
                        
                        // Render filtered results
                        const grid = document.getElementById(gridId);
                        grid.innerHTML = filtered.map(video => `
                            <div class="video-card" onclick="playVideo('${video.file_path}')">
                                <img class="video-thumbnail" 
                                    src="/api/thumbnail/${video.id}" 
                                    alt="${video.title}"
                                    onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\'%3E%3Crect fill=\\'%23ddd\\' width=\\'100\\' height=\\'100\\'/%3E%3C/svg%3E'">
                                <div class="video-info">
                                    <div class="video-title">${video.title}</div>
                                    <div class="video-uploader">${video.uploader}</div>
                                    ${isShort ? '<span class="badge">Short</span>' : ''}
                                </div>
                            </div>
                        `).join('');
                    });
            }
            
            function playVideo(videoId) {
                // Open video in new window or implement custom player
                // Encode the entire path properly for special characters
                // const encodedPath = encodeURIComponent(filePath);
                // window.open(`/api/stream/${encodedPath}`, '_blank');
                window.open(`/api/stream-by-id/${videoId}`, '_blank');
            }
            
            // Load videos on initial page load
            // loadVideos(false);
        </script>
    </body>
    </html>
    """

@app.post("/api/download-video")
async def download_video(request: VideoDownloadRequest, background_tasks: BackgroundTasks):
    """Download a single video"""
    try:
        # In production, run this in background
        background_tasks.add_task(manager.download_video, str(request.url), request.tags)
        
        # For now, download synchronously (replace with background task in production)
        result = manager.download_video(str(request.url), request.tags)
        
        if result['status'] == 'success':
            return {
                "status": "success",
                "message": f"Successfully downloaded: {result['title']}"
            }
        else:
            return {
                "status": "error",
                "message": result.get('message', 'Download failed')
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download-playlist")
async def download_playlist(request: PlaylistDownloadRequest, background_tasks: BackgroundTasks):
    """Download entire playlist"""
    try:
        # Background task for long-running playlist downloads
        background_tasks.add_task(manager.download_playlist, str(request.url), request.tags)
        
        result = manager.download_playlist(str(request.url), request.tags)
        
        return {
            "status": "success",
            "message": f"Playlist download started: {result.get('playlist_name')}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos")
async def get_videos(is_short: bool = False):
    """Get all videos or shorts"""
    try:
        videos = manager.get_all_videos(is_short=is_short)
        return videos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/playlists")
async def get_playlists():
    """Get all playlists"""
    try:
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM playlists")
        
        columns = [description[0] for description in cursor.description]
        playlists = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
async def search_videos(q: str):
    """Search videos"""
    try:
        results = manager.search_videos(q)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/thumbnail/{video_id}")
# async def get_thumbnail(video_id: int):
#     """Serve video thumbnail"""
#     try:
#         conn = sqlite3.connect(manager.db_path)
#         cursor = conn.cursor()
#         cursor.execute("SELECT file_path FROM videos WHERE id = ?", (video_id,))
#         result = cursor.fetchone()
#         conn.close()
        
#         if result and result[0]:
#             thumb_path = Path(result[0])
#             if thumb_path.exists():
#                 return FileResponse(thumb_path)
        
#         # Return placeholder if thumbnail not found
#         raise HTTPException(status_code=404, detail="Thumbnail not found")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/thumbnail/{video_id}")
async def get_thumbnail(video_id: int):
    """Serve video thumbnail"""
    try:
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM videos WHERE id = ?", (video_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            # Look for thumbnail saved next to video file
            video_path = Path(result[0])
            video_dir = video_path.parent
            video_name = video_path.stem  # filename without extension
            
            # Try common thumbnail extensions yt-dlp saves
            for ext in ['.jpg', '.webp', '.png']:
                thumb_path = video_dir / f"{video_name}{ext}"
                if thumb_path.exists():
                    return FileResponse(thumb_path)
        
        # Not found - let browser use fallback gray box
        raise HTTPException(status_code=404, detail="Thumbnail not found")
        
    except Exception as e:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

@app.get("/api/stream/{file_path:path}")
async def stream_video(file_path: str, request: Request):
    """Stream video file with range support"""
    try:
        video_path = Path(file_path)
        
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Get file size
        file_size = video_path.stat().st_size
        
        # Handle range requests for video seeking
        range_header = request.headers.get("range")
        
        if range_header:
            # Parse range header
            range_match = range_header.replace("bytes=", "").split("-")
            start = int(range_match[0])
            end = int(range_match[1]) if range_match[1] else file_size - 1
            
            # Read chunk
            chunk_size = end - start + 1
            
            def iterfile():
                with open(video_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        chunk = f.read(min(8192, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": "video/mp4",
            }
            
            return StreamingResponse(iterfile(), status_code=206, headers=headers)
        
        # No range request - serve entire file
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get library statistics"""
    try:
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM videos WHERE is_short = 0")
        video_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM videos WHERE is_short = 1")
        shorts_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM playlists")
        playlist_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(duration) FROM videos")
        total_duration = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total_videos": video_count,
            "total_shorts": shorts_count,
            "total_playlists": playlist_count,
            "total_duration_seconds": total_duration,
            "total_duration_hours": round(total_duration / 3600, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/stream-by-id/{video_id}")
async def stream_by_id(video_id: int, request: Request):
    """Stream video by database ID instead of file path"""
    try:
        # Get file path from database
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM videos WHERE id = ?", (video_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result[0]:
            raise HTTPException(status_code=404, detail="Video not found")
        
        video_path = Path(result[0])
        
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Use the existing streaming logic
        return await stream_video(str(video_path), request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)