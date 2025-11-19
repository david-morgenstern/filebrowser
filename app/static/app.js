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
        <div id="videoContainer" style="position: relative; background: #000;">
            <video id="videoPlayer" preload="auto" crossorigin="anonymous" style="width: 100%; height: auto; background: #000; display: block; margin: auto;">
                <source src="/transcode/${encodedPath}" type="video/mp4">
            </video>
            <div id="customControls" style="background: rgba(0,0,0,0.8); padding: 10px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <button id="prevBtn" style="background: #555; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; display: none;" title="Previous video">⏮</button>
                <button id="skipBackBtn" style="background: #555; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;" title="Back 5s">-5</button>
                <button id="playPauseBtn" style="background: #2196F3; color: white; border: none; padding: 5px 15px; border-radius: 3px; cursor: pointer;">Play</button>
                <button id="skipFwdBtn" style="background: #555; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;" title="Forward 5s">+5</button>
                <button id="nextBtn" style="background: #555; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; display: none;" title="Next video">⏭</button>
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
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const skipBackBtn = document.getElementById('skipBackBtn');
    const skipFwdBtn = document.getElementById('skipFwdBtn');
    const seekBar = document.getElementById('seekBar');

    // Store data on video element for closeModal to access
    video.dataset.encodedPath = encodedPath;
    const seekProgress = document.getElementById('seekProgress');
    const bufferedProgress = document.getElementById('bufferedProgress');
    const currentTimeDisplay = document.getElementById('currentTime');
    const totalTimeDisplay = document.getElementById('totalTime');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const audioTrackSelect = document.getElementById('audioTrackSelect');
    const subtitleTrackSelect = document.getElementById('subtitleTrackSelect');

    let videoDuration = 0;
    let isSeeking = false;
    let currentAudioTrack = 0;
    let currentSeekTime = 0;
    let subtitleTracks = [];
    let selectedSubtitleTrack = -1;
    let adjacentVideos = { prev: null, next: null };

    // Initialize data attributes for closeModal
    video.dataset.seekTime = '0';
    video.dataset.duration = '0';

    // Save playback position (using sendBeacon for reliability)
    function savePosition() {
        const actualTime = currentSeekTime + video.currentTime;
        if (actualTime > 0 && videoDuration > 0) {
            // Use sendBeacon for more reliable saving (doesn't get cancelled on page unload)
            const url = `/api/save-position/${encodedPath}?position=${actualTime}`;
            if (navigator.sendBeacon) {
                navigator.sendBeacon(url);
            } else {
                fetch(url, { method: 'POST', keepalive: true })
                    .catch(err => console.error('Failed to save position:', err));
            }
        }
    }

    // Save position on pause
    video.addEventListener('pause', savePosition);

    // Reset position when video ends (finished watching)
    video.addEventListener('ended', () => {
        fetch(`/api/save-position/${encodedPath}?position=0`, { method: 'POST' });
    });

    // Save position before page unload
    window.addEventListener('beforeunload', savePosition);

    // Save position when tab becomes hidden (switching tabs, minimizing)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) savePosition();
    });


    // Fetch adjacent videos for navigation
    fetch('/api/adjacent-videos/' + encodedPath)
        .then(r => r.json())
        .then(data => {
            adjacentVideos = data;
            if (data.prev) {
                prevBtn.style.display = 'inline-block';
                prevBtn.title = `Previous: ${data.prev.name}`;
            }
            if (data.next) {
                nextBtn.style.display = 'inline-block';
                nextBtn.title = `Next: ${data.next.name}`;
            }
        })
        .catch(err => console.error('Failed to get adjacent videos:', err));

    // Previous/Next navigation
    prevBtn.addEventListener('click', () => {
        if (adjacentVideos.prev) {
            viewFile(adjacentVideos.prev.path, 'video', adjacentVideos.prev.name);
        }
    });

    nextBtn.addEventListener('click', () => {
        if (adjacentVideos.next) {
            viewFile(adjacentVideos.next.path, 'video', adjacentVideos.next.name);
        }
    });

    // Autoplay next video when current ends
    video.addEventListener('ended', () => {
        if (adjacentVideos.next) {
            viewFile(adjacentVideos.next.path, 'video', adjacentVideos.next.name);
        }
    });

    // Function to load/reload subtitle tracks with time offset
    function loadSubtitleTracks(offset) {
        // Remove existing track elements
        video.querySelectorAll('track').forEach(t => t.remove());

        // Add new tracks with offset
        subtitleTracks.forEach((track, i) => {
            const trackEl = document.createElement('track');
            trackEl.kind = 'subtitles';
            trackEl.label = track.label;
            trackEl.srclang = track.language || 'en';
            trackEl.src = `/api/subtitles/${encodedPath}?track=${track.index}&offset=${offset}`;
            video.appendChild(trackEl);
        });

        // Re-enable selected track after tracks are added
        setTimeout(() => {
            // First disable all
            for (let i = 0; i < video.textTracks.length; i++) {
                video.textTracks[i].mode = 'disabled';
            }
            // Then enable selected
            if (selectedSubtitleTrack >= 0 && video.textTracks[selectedSubtitleTrack]) {
                video.textTracks[selectedSubtitleTrack].mode = 'showing';
            }
        }, 200);
    }

    // Fetch metadata, audio tracks, subtitle tracks, and saved position
    Promise.all([
        fetch('/api/video-info/' + encodedPath).then(r => r.json()),
        fetch('/api/audio-tracks/' + encodedPath).then(r => r.json()),
        fetch('/api/subtitle-tracks/' + encodedPath).then(r => r.json()),
        fetch('/api/get-position/' + encodedPath).then(r => r.json())
    ])
        .then(([metadata, audioData, subtitleData, positionData]) => {
            videoDuration = metadata.duration;
            video.dataset.duration = videoDuration;
            totalTimeDisplay.textContent = formatTime(videoDuration);

            const copyOrTranscode = metadata.needs_transcode ? 'Transcoding' : 'Remuxing';
            notice.textContent = `⚡ ${copyOrTranscode} ${metadata.codec.toUpperCase()} (${formatTime(videoDuration)})`;

            // Populate audio track selector
            if (audioData.tracks && audioData.tracks.length > 1) {
                audioTrackSelect.style.display = 'block';
                audioData.tracks.forEach((track) => {
                    const option = document.createElement('option');
                    option.value = track.index;
                    option.textContent = `🔊 ${track.label}`;
                    audioTrackSelect.appendChild(option);
                });
            }

            // Store subtitle tracks for later use
            if (subtitleData.tracks && subtitleData.tracks.length > 0) {
                subtitleTracks = subtitleData.tracks;
                subtitleTrackSelect.style.display = 'block';
                subtitleData.tracks.forEach((track) => {
                    // Add option to dropdown
                    const option = document.createElement('option');
                    option.value = track.index;
                    option.textContent = `CC ${track.label}`;
                    subtitleTrackSelect.appendChild(option);
                });
                // Load initial subtitle tracks
                loadSubtitleTracks(0);
            }

            // Show resume banner (will fetch fresh position when clicked)
            // Create resume banner
            const resumeBanner = document.createElement('div');
            resumeBanner.id = 'resumeBanner';
            resumeBanner.style.cssText = 'background: rgba(33, 150, 243, 0.9); padding: 8px 15px; display: flex; align-items: center; justify-content: space-between; color: white; font-size: 14px;';
            resumeBanner.innerHTML = `
                <span id="resumeText">Resume available</span>
                <div>
                    <button id="resumeBtn" style="background: white; color: #2196F3; border: none; padding: 5px 12px; border-radius: 3px; cursor: pointer; margin-right: 8px; font-weight: bold;">Resume</button>
                    <button id="dismissResume" style="background: transparent; color: white; border: 1px solid white; padding: 5px 12px; border-radius: 3px; cursor: pointer;">Start Over</button>
                </div>
            `;

            // Insert after notice
            notice.parentNode.insertBefore(resumeBanner, notice.nextSibling);

            // Update text with initial position if available
            if (positionData.position > 10) {
                document.getElementById('resumeText').textContent = `Resume from ${formatTime(positionData.position)}`;
            } else {
                resumeBanner.style.display = 'none';
            }

            // Resume button handler - fetches fresh position when clicked
            document.getElementById('resumeBtn').addEventListener('click', async (e) => {
                e.stopPropagation();

                // Fetch fresh position from database
                const freshData = await fetch(`/api/get-position/${encodedPath}?_=${Date.now()}`).then(r => r.json());
                const resumeTime = freshData.position;

                if (resumeTime > 0) {
                    currentSeekTime = resumeTime; video.dataset.seekTime = resumeTime;
                    video.src = `/transcode/${encodedPath}?start_time=${resumeTime}&audio_track=${currentAudioTrack}`;
                    video.load();
                    if (subtitleTracks.length > 0) {
                        loadSubtitleTracks(resumeTime);
                    }
                    seekProgress.style.width = ((resumeTime / videoDuration) * 100) + '%';
                    currentTimeDisplay.textContent = formatTime(resumeTime);
                    video.play().catch(() => {});
                }
                resumeBanner.remove();
            });

            // Dismiss button handler
            document.getElementById('dismissResume').addEventListener('click', (e) => {
                e.stopPropagation();
                resumeBanner.remove();
            });
        })
        .catch(err => {
            console.error('Failed to get metadata:', err);
            notice.textContent = '⚠️ Could not load metadata';
        });

    // Audio track change handler - requires reload
    audioTrackSelect.addEventListener('change', () => {
        currentAudioTrack = parseInt(audioTrackSelect.value);
        const wasPlaying = !video.paused;
        const currentTime = currentSeekTime + video.currentTime;

        video.pause();
        currentSeekTime = currentTime; video.dataset.seekTime = currentTime;
        video.src = `/transcode/${encodedPath}?start_time=${currentTime}&audio_track=${currentAudioTrack}`;
        video.load();

        // Reload subtitles with current offset
        if (subtitleTracks.length > 0) {
            loadSubtitleTracks(currentTime);
        }

        if (wasPlaying) {
            video.play().catch(e => console.log('Play prevented after audio change'));
        }
    });

    // Subtitle track change handler - instant, no reload needed
    subtitleTrackSelect.addEventListener('change', () => {
        selectedSubtitleTrack = parseInt(subtitleTrackSelect.value);

        // Disable all tracks first
        for (let i = 0; i < video.textTracks.length; i++) {
            video.textTracks[i].mode = 'disabled';
        }

        // Enable selected track
        if (selectedSubtitleTrack >= 0 && video.textTracks[selectedSubtitleTrack]) {
            video.textTracks[selectedSubtitleTrack].mode = 'showing';
        }
    });

    // Play/Pause
    playPauseBtn.addEventListener('click', () => {
        video.paused ? video.play() : video.pause();
    });

    video.addEventListener('play', () => playPauseBtn.textContent = 'Pause');
    video.addEventListener('pause', () => playPauseBtn.textContent = 'Play');

    // Skip function
    function skip(seconds) {
        if (videoDuration === 0) return;

        const currentActualTime = currentSeekTime + video.currentTime;
        const newTime = Math.max(0, Math.min(videoDuration, currentActualTime + seconds));

        const wasPlaying = !video.paused;
        isSeeking = true;
        video.pause();

        currentSeekTime = newTime; video.dataset.seekTime = newTime;
        video.src = `/transcode/${encodedPath}?start_time=${newTime}&audio_track=${currentAudioTrack}`;
        video.load();

        if (subtitleTracks.length > 0) {
            loadSubtitleTracks(newTime);
        }

        const percentage = newTime / videoDuration;
        seekProgress.style.width = (percentage * 100) + '%';
        currentTimeDisplay.textContent = formatTime(newTime);

        if (wasPlaying) {
            video.play().then(() => isSeeking = false).catch(() => isSeeking = false);
        } else {
            isSeeking = false;
        }
    }

    // Skip buttons
    skipBackBtn.addEventListener('click', () => skip(-5));
    skipFwdBtn.addEventListener('click', () => skip(5));

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Only handle if video player is active (modal is open)
        if (!document.getElementById('modal').classList.contains('active')) return;
        // Don't handle if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

        switch (e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                skip(-5);
                break;
            case 'ArrowRight':
                e.preventDefault();
                skip(5);
                break;
            case ' ':
                e.preventDefault();
                video.paused ? video.play() : video.pause();
                break;
        }
    });

    // Time update
    video.addEventListener('timeupdate', () => {
        if (!isSeeking && videoDuration > 0) {
            const actualTime = currentSeekTime + video.currentTime;
            seekProgress.style.width = ((actualTime / videoDuration) * 100) + '%';
            currentTimeDisplay.textContent = formatTime(actualTime);
        }
    });

    // Buffered progress
    video.addEventListener('progress', () => {
        if (video.buffered.length > 0 && videoDuration > 0) {
            const bufferedEnd = video.buffered.end(video.buffered.length - 1);
            const actualBuffered = currentSeekTime + bufferedEnd;
            bufferedProgress.style.width = ((actualBuffered / videoDuration) * 100) + '%';
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

        currentSeekTime = seekToTime; video.dataset.seekTime = seekToTime;
        video.src = `/transcode/${encodedPath}?start_time=${seekToTime}&audio_track=${currentAudioTrack}`;
        video.load();

        // Reload subtitles with new offset
        if (subtitleTracks.length > 0) {
            loadSubtitleTracks(seekToTime);
        }

        seekProgress.style.width = (percentage * 100) + '%';
        currentTimeDisplay.textContent = formatTime(seekToTime);

        if (wasPlaying) {
            video.play().then(() => isSeeking = false).catch(() => isSeeking = false);
        } else {
            isSeeking = false;
        }
    });

    // Fullscreen
    const videoContainer = document.getElementById('videoContainer');

    fullscreenBtn.addEventListener('click', () => {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            videoContainer.requestFullscreen();
        }
    });

    // Handle fullscreen style changes
    const customControls = document.getElementById('customControls');
    let hideControlsTimeout = null;

    function showControls() {
        customControls.style.opacity = '1';
        customControls.style.pointerEvents = 'auto';
        videoContainer.style.cursor = 'default';
    }

    function hideControls() {
        if (document.fullscreenElement === videoContainer) {
            customControls.style.opacity = '0';
            customControls.style.pointerEvents = 'none';
            videoContainer.style.cursor = 'none';
        }
    }

    function resetHideTimer() {
        showControls();
        if (hideControlsTimeout) clearTimeout(hideControlsTimeout);
        if (document.fullscreenElement === videoContainer) {
            hideControlsTimeout = setTimeout(hideControls, 3000);
        }
    }

    videoContainer.addEventListener('mousemove', resetHideTimer);
    videoContainer.addEventListener('click', resetHideTimer);

    document.addEventListener('fullscreenchange', () => {
        if (document.fullscreenElement === videoContainer) {
            videoContainer.style.display = 'flex';
            videoContainer.style.flexDirection = 'column';
            videoContainer.style.justifyContent = 'center';
            videoContainer.style.alignItems = 'center';
            videoContainer.style.height = '100vh';
            videoContainer.style.width = '100vw';
            video.style.width = '100%';
            video.style.height = '100%';
            video.style.maxHeight = 'calc(100vh - 50px)';
            video.style.objectFit = 'contain';
            customControls.style.transition = 'opacity 0.3s';
            customControls.style.position = 'absolute';
            customControls.style.bottom = '0';
            customControls.style.left = '0';
            customControls.style.right = '0';
            resetHideTimer();
        } else {
            videoContainer.style.display = '';
            videoContainer.style.flexDirection = '';
            videoContainer.style.justifyContent = '';
            videoContainer.style.alignItems = '';
            videoContainer.style.height = '';
            videoContainer.style.width = '';
            video.style.width = '100%';
            video.style.height = 'auto';
            video.style.maxHeight = '';
            video.style.objectFit = '';
            customControls.style.transition = '';
            customControls.style.position = '';
            customControls.style.bottom = '';
            customControls.style.left = '';
            customControls.style.right = '';
            showControls();
            if (hideControlsTimeout) clearTimeout(hideControlsTimeout);
        }
    });

    // Auto-play
    video.addEventListener('loadeddata', () => {
        if (currentSeekTime === 0) video.play().catch(e => console.log('Auto-play prevented'));
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
        // Save position before clearing (video stores these as data attributes)
        if (video.dataset.encodedPath && video.dataset.seekTime !== undefined) {
            const actualTime = parseFloat(video.dataset.seekTime) + video.currentTime;
            const duration = parseFloat(video.dataset.duration) || 0;
            if (actualTime > 0 && duration > 0) {
                const url = `/api/save-position/${video.dataset.encodedPath}?position=${actualTime}`;
                if (navigator.sendBeacon) {
                    navigator.sendBeacon(url);
                } else {
                    fetch(url, { method: 'POST', keepalive: true });
                }
            }
        }
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

// Continue watching - resume last video
async function continueWatching() {
    try {
        // Small delay to ensure any pending saves complete
        await new Promise(resolve => setTimeout(resolve, 200));

        const response = await fetch('/api/continue-watching');
        const data = await response.json();

        if (data.file_path) {
            viewFile(data.file_path, data.file_type, data.file_name);
        } else {
            alert('No video to continue. Start watching something first!');
        }
    } catch (error) {
        console.error('Failed to get continue watching:', error);
        alert('Failed to get continue watching data');
    }
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
