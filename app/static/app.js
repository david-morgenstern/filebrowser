// File Browser JavaScript

// Search functionality
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const search = e.target.value.toLowerCase();
            document.querySelectorAll('#fileList li[data-name]').forEach(li => {
                li.style.display = li.dataset.name.includes(search) ? '' : 'none';
            });
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === '/' && e.target.tagName !== 'INPUT') {
            e.preventDefault();
            searchInput?.focus();
        }
        if (e.key === 'Escape') {
            closeModal();
            if (document.activeElement === searchInput) {
                searchInput.blur();
            }
        }
    });

    // Modal click outside to close
    document.getElementById('modal')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });
});

// MIME type detection
function getMimeType(filename) {
    const ext = filename.toLowerCase().split('.').pop();
    const mimeTypes = {
        'mp4': 'video/mp4', 'm4v': 'video/mp4', 'webm': 'video/webm',
        'mkv': 'video/x-matroska', 'avi': 'video/x-msvideo',
        'mov': 'video/quicktime', 'flv': 'video/x-flv', 'wmv': 'video/x-ms-wmv',
        'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
        'wav': 'audio/wav', 'flac': 'audio/flac', 'ogg': 'audio/ogg',
        'oga': 'audio/ogg', 'opus': 'audio/opus'
    };
    return mimeTypes[ext] || '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Video player for transcoded files
function createTranscodedVideoPlayer(encodedPath, name) {
    const content = document.getElementById('modalContent');

    content.innerHTML = `
        <div id="transcodeNotice" style="background: rgba(33, 150, 243, 0.1); padding: 0.5rem; text-align: center; color: #2196F3; font-size: 0.85rem; margin-bottom: 0.5rem;">
            ⚡ Loading video metadata...
        </div>
        <div style="position: relative;">
            <video id="videoPlayer" preload="auto" style="width: 100%; height: auto; background: #000; display: block;">
                <source src="/transcode/${encodedPath}" type="video/mp4">
            </video>
            <div id="customControls" style="background: rgba(0,0,0,0.8); padding: 10px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <button id="playPauseBtn" style="background: #2196F3; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Play</button>
                <span id="currentTime" style="color: white; font-size: 14px; min-width: 45px;">0:00</span>
                <div id="seekBar" style="flex: 1; height: 8px; background: rgba(255,255,255,0.3); border-radius: 4px; cursor: pointer; position: relative; min-width: 100px;">
                    <div id="bufferedProgress" style="position: absolute; top: 0; height: 100%; background: rgba(255,255,255,0.5); border-radius: 4px; width: 0%;"></div>
                    <div id="seekProgress" style="position: relative; height: 100%; background: #2196F3; border-radius: 4px; width: 0%;"></div>
                </div>
                <span id="totalTime" style="color: white; font-size: 14px; min-width: 45px;">0:00</span>
                <select id="audioTrackSelect" style="background: #333; color: white; border: 1px solid #555; padding: 5px; border-radius: 3px; cursor: pointer; display: none;">
                </select>
                <select id="subtitleTrackSelect" style="background: #333; color: white; border: 1px solid #555; padding: 5px; border-radius: 3px; cursor: pointer; display: none;">
                    <option value="-1">CC Off</option>
                </select>
                <button id="fullscreenBtn" style="background: #2196F3; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Fullscreen</button>
            </div>
        </div>
        <div class="media-info">${escapeHtml(name)}</div>
    `;

    const video = document.getElementById('videoPlayer');
    const notice = document.getElementById('transcodeNotice');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const seekBar = document.getElementById('seekBar');
    const seekProgress = document.getElementById('seekProgress');
    const bufferedProgress = document.getElementById('bufferedProgress');
    const currentTimeDisplay = document.getElementById('currentTime');
    const totalTimeDisplay = document.getElementById('totalTime');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const audioTrackSelect = document.getElementById('audioTrackSelect');
    const subtitleTrackSelect = document.getElementById('subtitleTrackSelect');

    let videoDuration = 0;
    let currentStartTime = 0;
    let isSeeking = false;
    let currentAudioTrack = 0;
    let currentSubtitleTrack = -1;

    // Fetch metadata, audio tracks, and subtitle tracks
    Promise.all([
        fetch('/api/video-info/' + encodedPath).then(r => r.json()),
        fetch('/api/audio-tracks/' + encodedPath).then(r => r.json()),
        fetch('/api/subtitle-tracks/' + encodedPath).then(r => r.json())
    ])
        .then(([metadata, audioData, subtitleData]) => {
            videoDuration = metadata.duration;
            totalTimeDisplay.textContent = formatTime(videoDuration);
            notice.textContent = `⚡ Streaming ${metadata.codec.toUpperCase()} (${formatTime(videoDuration)}) - Click timeline to seek`;

            // Populate audio track selector
            if (audioData.tracks && audioData.tracks.length > 1) {
                audioTrackSelect.style.display = 'block';
                audioData.tracks.forEach((track, i) => {
                    const option = document.createElement('option');
                    option.value = track.index;
                    option.textContent = `🔊 ${track.label}`;
                    audioTrackSelect.appendChild(option);
                });
            }

            // Populate subtitle track selector
            if (subtitleData.tracks && subtitleData.tracks.length > 0) {
                subtitleTrackSelect.style.display = 'block';
                subtitleData.tracks.forEach((track, i) => {
                    const option = document.createElement('option');
                    option.value = track.index;
                    option.textContent = `CC ${track.label}`;
                    subtitleTrackSelect.appendChild(option);
                });
            }
        })
        .catch(err => {
            console.error('Failed to get metadata:', err);
            notice.textContent = '⚠️ Could not load metadata';
        });

    // Audio track change handler
    audioTrackSelect.addEventListener('change', () => {
        currentAudioTrack = parseInt(audioTrackSelect.value);
        const wasPlaying = !video.paused;
        const currentTime = currentStartTime + video.currentTime;

        video.pause();
        currentStartTime = currentTime;
        video.src = `/transcode/${encodedPath}?start_time=${currentTime}&audio_track=${currentAudioTrack}&subtitle_track=${currentSubtitleTrack}`;
        video.load();

        if (wasPlaying) {
            video.play().catch(e => console.log('Play prevented after audio change'));
        }
    });

    // Subtitle track change handler
    subtitleTrackSelect.addEventListener('change', () => {
        currentSubtitleTrack = parseInt(subtitleTrackSelect.value);
        const wasPlaying = !video.paused;
        const currentTime = currentStartTime + video.currentTime;

        video.pause();
        currentStartTime = currentTime;
        video.src = `/transcode/${encodedPath}?start_time=${currentTime}&audio_track=${currentAudioTrack}&subtitle_track=${currentSubtitleTrack}`;
        video.load();

        if (wasPlaying) {
            video.play().catch(e => console.log('Play prevented after subtitle change'));
        }
    });

    // Play/Pause
    playPauseBtn.addEventListener('click', () => {
        video.paused ? video.play() : video.pause();
    });

    video.addEventListener('play', () => playPauseBtn.textContent = 'Pause');
    video.addEventListener('pause', () => playPauseBtn.textContent = 'Play');

    // Time update
    video.addEventListener('timeupdate', () => {
        if (!isSeeking && videoDuration > 0) {
            const adjustedTime = currentStartTime + video.currentTime;
            seekProgress.style.width = ((adjustedTime / videoDuration) * 100) + '%';
            currentTimeDisplay.textContent = formatTime(adjustedTime);
        }
    });

    // Buffered progress
    video.addEventListener('progress', () => {
        if (video.buffered.length > 0 && videoDuration > 0) {
            const bufferedEnd = video.buffered.end(video.buffered.length - 1);
            const adjustedBuffered = currentStartTime + bufferedEnd;
            bufferedProgress.style.width = ((adjustedBuffered / videoDuration) * 100) + '%';
        }
    });

    // Seeking
    seekBar.addEventListener('click', (e) => {
        if (videoDuration === 0) return;

        const rect = seekBar.getBoundingClientRect();
        const percentage = (e.clientX - rect.left) / rect.width;
        const seekToTime = percentage * videoDuration;

        const wasPlaying = !video.paused;
        isSeeking = true;
        video.pause();

        currentStartTime = seekToTime;
        video.src = `/transcode/${encodedPath}?start_time=${seekToTime}&audio_track=${currentAudioTrack}&subtitle_track=${currentSubtitleTrack}`;
        video.load();

        seekProgress.style.width = (percentage * 100) + '%';
        currentTimeDisplay.textContent = formatTime(seekToTime);

        if (wasPlaying) {
            video.play().then(() => isSeeking = false).catch(() => isSeeking = false);
        } else {
            isSeeking = false;
        }
    });

    // Fullscreen
    fullscreenBtn.addEventListener('click', () => {
        const container = video.parentElement;
        document.fullscreenElement ? document.exitFullscreen() : container.requestFullscreen();
    });

    // Auto-play
    video.addEventListener('loadeddata', () => {
        if (currentStartTime === 0) video.play().catch(e => console.log('Auto-play prevented'));
    });

    video.addEventListener('error', (e) => console.error('Video error:', e, video.error));
}

// Standard video player
function createStandardVideoPlayer(streamUrl, mimeType, name) {
    const content = document.getElementById('modalContent');
    content.innerHTML = `
        <video id="videoPlayer" controls preload="auto" style="width: 100%; height: auto; background: #000;">
            <source src="${streamUrl}" type="${mimeType}">
        </video>
        <div class="media-info">${escapeHtml(name)}</div>
    `;

    const video = document.getElementById('videoPlayer');
    video.addEventListener('loadedmetadata', () => console.log('Duration:', video.duration));
    video.addEventListener('error', (e) => console.error('Video error:', e, video.error));
}

// View file
function viewFile(path, type, name) {
    const modal = document.getElementById('modal');
    const content = document.getElementById('modalContent');
    const encodedPath = path.split('/').map(p => encodeURIComponent(p)).join('/');
    const streamUrl = '/stream/' + encodedPath;
    const mimeType = getMimeType(name);

    if (type === 'image') {
        content.innerHTML = `<img src="${streamUrl}" alt="${escapeHtml(name)}">`;
    } else if (type === 'video') {
        const ext = name.toLowerCase().split('.').pop();
        const needsTranscode = ['avi', 'mkv', 'wmv', 'flv'].includes(ext);

        needsTranscode
            ? createTranscodedVideoPlayer(encodedPath, name)
            : createStandardVideoPlayer(streamUrl, mimeType, name);
    } else if (type === 'audio') {
        content.innerHTML = `
            <audio id="audioPlayer" controls preload="auto" style="width: 100%;">
                <source src="${streamUrl}" type="${mimeType}">
            </audio>
            <div class="media-info">${escapeHtml(name)}</div>
        `;
        document.getElementById('audioPlayer').addEventListener('error', (e) => console.error('Audio error:', e));
    } else if (type === 'text') {
        fetch('/preview/' + encodedPath)
            .then(r => r.ok ? r.text() : Promise.reject(`HTTP ${r.status}`))
            .then(text => {
                content.innerHTML = `
                    <div class="text-preview">
                        <div class="text-preview-header">${escapeHtml(name)}</div>
                        <div class="text-preview-content">${escapeHtml(text)}</div>
                    </div>
                `;
            })
            .catch(err => {
                content.innerHTML = `<div style="color: white; padding: 2rem;">Error: ${err}</div>`;
            });
    }

    modal.classList.add('active');
}

// Close modal
function closeModal() {
    const modal = document.getElementById('modal');
    const content = document.getElementById('modalContent');

    // Stop any playing media
    const video = document.getElementById('videoPlayer');
    const audio = document.getElementById('audioPlayer');

    if (video) {
        video.pause();
        video.src = '';
    }
    if (audio) {
        audio.pause();
        audio.src = '';
    }

    modal.classList.remove('active');
    content.innerHTML = '';
}

// Watch history
async function showHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        const modal = document.getElementById('modal');
        const content = document.getElementById('modalContent');

        if (data.count === 0) {
            content.innerHTML = `
                <div class="text-preview">
                    <div class="text-preview-header">Watch History</div>
                    <div style="padding: 2rem; text-align: center; color: #666;">No history yet</div>
                </div>
            `;
        } else {
            let html = `
                <div class="text-preview">
                    <div class="text-preview-header">Watch History (${data.count} items)</div>
                    <div style="padding: 1rem;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="border-bottom: 2px solid #e0e0e0;">
                                    <th style="padding: 0.5rem; text-align: left;">File</th>
                                    <th style="padding: 0.5rem; text-align: left;">Type</th>
                                    <th style="padding: 0.5rem; text-align: right;">Views</th>
                                    <th style="padding: 0.5rem; text-align: right;">Last Watched</th>
                                </tr>
                            </thead>
                            <tbody>
            `;

            data.history.forEach(item => {
                const lastWatched = new Date(item.last_watched).toLocaleString();
                const fileType = item.file_type.charAt(0).toUpperCase() + item.file_type.slice(1);
                html += `
                    <tr style="border-bottom: 1px solid #f0f0f0; cursor: pointer;"
                        onclick='viewFile("${item.file_path}", "${item.file_type}", "${escapeHtml(item.file_name).replace(/'/g, "\\'")}")'>
                        <td style="padding: 0.75rem;">${escapeHtml(item.file_name)}</td>
                        <td style="padding: 0.75rem;">${fileType}</td>
                        <td style="padding: 0.75rem; text-align: right;">${item.view_count}</td>
                        <td style="padding: 0.75rem; text-align: right; font-size: 0.85rem; color: #666;">${lastWatched}</td>
                    </tr>
                `;
            });

            html += `</tbody></table></div></div>`;
            content.innerHTML = html;
        }

        modal.classList.add('active');
    } catch (error) {
        console.error('Failed to load history:', error);
        alert('Failed to load watch history');
    }
}
