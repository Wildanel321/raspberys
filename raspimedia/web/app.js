/**
 * RaspiMedia - Reactive Web UI & Remote Controller
 */

// Application State
const state = {
  currentTab: 'videos',      // 'videos', 'music', 'favorites', 'directories'
  currentFilter: 'all',      // 'all', 'movie', 'series', 'other_video', etc.
  currentSort: 'title',
  searchQuery: '',
  mediaItems: [],
  totalItems: 0,
  stats: {},
  directories: [],
  playerState: {
    is_playing: false,
    is_paused: false,
    current_title: '',
    time_pos: 0,
    duration: 0,
    volume: 100,
  },
  isScanning: false,
};

// Utilities
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '00:00';
  const sec = Math.floor(seconds);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast';
  if (type === 'warning') toast.style.borderLeftColor = 'var(--accent-amber)';
  if (type === 'error') toast.style.borderLeftColor = 'var(--accent-rose)';
  if (type === 'success') toast.style.borderLeftColor = 'var(--accent-emerald)';
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// API Calls
async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    if (res.ok) {
      state.stats = await res.json();
      updateStatsUI();
    }
  } catch (err) {
    console.error('Failed to fetch stats:', err);
  }
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      state.directories = data.directories || [];
      updateStorageStatusBadge();
    }
  } catch (err) {
    console.error('Failed to fetch status:', err);
  }
}

async function fetchMedia() {
  const container = document.getElementById('content-container');
  
  if (state.currentTab === 'directories') {
    renderDirectoriesView();
    return;
  }

  let url = `/api/media?order_by=${state.currentSort}`;
  
  if (state.currentTab === 'videos') {
    url += '&media_type=video';
    if (state.currentFilter !== 'all') {
      url += `&category=${state.currentFilter}`;
    }
  } else if (state.currentTab === 'music') {
    url += '&media_type=audio';
  } else if (state.currentTab === 'favorites') {
    url += '&favorite=true';
  }

  if (state.searchQuery) {
    url += `&q=${encodeURIComponent(state.searchQuery)}`;
  }

  try {
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      state.mediaItems = data.items || [];
      state.totalItems = data.total || 0;
      renderMediaGrid();
    }
  } catch (err) {
    console.error('Failed to fetch media:', err);
  }
}

async function playMedia(mediaId) {
  try {
    const res = await fetch(`/api/play/${mediaId}`, { method: 'POST' });
    if (res.ok) {
      showToast('▶ Playing on HDMI / MPV Output', 'success');
      pollPlayback();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to play media', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to player', 'error');
  }
}

async function toggleFavorite(mediaId, event) {
  if (event) event.stopPropagation();
  try {
    const res = await fetch(`/api/media/${mediaId}/favorite`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      // Update local state item
      const item = state.mediaItems.find(m => m.id === mediaId);
      if (item) item.favorite = data.favorite ? 1 : 0;
      fetchStats();
      if (state.currentTab === 'favorites') {
        fetchMedia();
      } else {
        renderMediaGrid();
      }
    }
  } catch (err) {
    console.error('Failed to toggle favorite:', err);
  }
}

async function triggerScan(force = false) {
  if (state.isScanning) return;
  state.isScanning = true;
  const icon = document.getElementById('rescan-icon');
  icon.classList.add('spin');
  showToast('🔍 Scanning configured media directories...', 'info');

  try {
    const res = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    });
    if (res.ok) {
      const result = await res.json();
      showToast(`Scan complete: ${result.added} added, ${result.updated} updated, ${result.removed} removed.`, 'success');
      fetchStats();
      fetchStatus();
      fetchMedia();
    }
  } catch (err) {
    showToast('Media scan failed', 'error');
  } finally {
    state.isScanning = false;
    icon.classList.remove('spin');
  }
}

async function controlPlayback(action, value = null) {
  try {
    await fetch('/api/playback/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, value }),
    });
    pollPlayback();
  } catch (err) {
    console.error('Failed to control playback:', err);
  }
}

async function pollPlayback() {
  try {
    const res = await fetch('/api/playback/status');
    if (res.ok) {
      state.playerState = await res.json();
      updatePlayerUI();
    }
  } catch (err) {
    // Ignore polling errors
  }
}

// UI Update Functions
function updateStatsUI() {
  const s = state.stats;
  document.getElementById('stat-videos-count').textContent = s.video_count || 0;
  document.getElementById('stat-videos-sub').textContent = `${s.movies_count || 0} Movies, ${s.series_count || 0} Series`;
  
  document.getElementById('stat-music-count').textContent = s.audio_count || 0;
  document.getElementById('stat-music-sub').textContent = `${s.artists_count || 0} Artists, ${s.albums_count || 0} Albums`;
  
  document.getElementById('stat-total-count').textContent = s.total_media || 0;
  document.getElementById('stat-total-sub').textContent = `${formatBytes(s.total_size_bytes)} total`;
  
  document.getElementById('stat-fav-count').textContent = s.favorite_count || 0;

  // Badges
  document.getElementById('badge-tab-videos').textContent = s.video_count || 0;
  document.getElementById('badge-tab-music').textContent = s.audio_count || 0;
  document.getElementById('badge-tab-fav').textContent = s.favorite_count || 0;
  document.getElementById('badge-tab-dirs').textContent = state.directories.length || 0;
}

function updateStorageStatusBadge() {
  const badge = document.getElementById('storage-status-badge');
  const text = document.getElementById('storage-status-text');
  
  const hasMissing = state.directories.some(d => !d.exists);
  const hasError = state.directories.some(d => d.exists && !d.readable);

  if (state.directories.length === 0) {
    badge.className = 'status-pill warning';
    text.textContent = 'No Dirs Configured';
  } else if (hasMissing || hasError) {
    badge.className = 'status-pill warning';
    text.textContent = 'Storage Warning';
  } else {
    badge.className = 'status-pill';
    text.textContent = 'Storage Ready';
  }
}

function updatePlayerUI() {
  const p = state.playerState;
  const titleEl = document.getElementById('player-track-title');
  const subEl = document.getElementById('player-track-subtitle');
  const playBtn = document.getElementById('btn-play-pause');
  const timeCur = document.getElementById('player-time-current');
  const timeTot = document.getElementById('player-time-total');
  const fill = document.getElementById('progress-fill');
  const cover = document.getElementById('player-cover');

  if (p.is_playing) {
    titleEl.textContent = p.current_title || 'Playing Media';
    subEl.textContent = p.is_paused ? 'Paused' : 'Playing on HDMI';
    playBtn.textContent = p.is_paused ? '▶' : '⏸';
    timeCur.textContent = formatDuration(p.time_pos);
    timeTot.textContent = formatDuration(p.duration);
    
    const pct = p.duration > 0 ? (p.time_pos / p.duration) * 100 : 0;
    fill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    
    cover.textContent = p.media_type === 'audio' ? '🎵' : '🎬';
  } else {
    titleEl.textContent = 'RaspiMedia Ready';
    subEl.textContent = 'Select media to play on HDMI';
    playBtn.textContent = '▶';
    timeCur.textContent = '00:00';
    timeTot.textContent = '00:00';
    fill.style.width = '0%';
    cover.textContent = '🍓';
  }
}

function renderMediaGrid() {
  const container = document.getElementById('content-container');
  
  if (state.mediaItems.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${state.searchQuery ? '🔍' : '📁'}</div>
        <div class="empty-title">${state.searchQuery ? 'No matching media found' : 'No media found in library'}</div>
        <div class="empty-desc">
          ${state.searchQuery 
            ? 'Try adjusting your search keywords.' 
            : 'Configure your real media folders in Storage Settings and click Rescan Library.'}
        </div>
        ${!state.searchQuery ? '<button class="btn btn-primary" onclick="switchTab(\'directories\')">Configure Media Directories</button>' : ''}
      </div>
    `;
    return;
  }

  let html = '<div class="media-grid">';
  for (const item of state.mediaItems) {
    const isAudio = item.media_type === 'audio';
    const isFav = item.favorite === 1;
    const durationStr = formatDuration(item.duration);
    const subtitle = isAudio 
      ? (item.artist || item.album || 'Audio Track')
      : (item.series_name ? `S${item.season_number || 1}E${item.episode_number || 1}` : (item.year ? `${item.year}` : 'Video'));

    const badgeInfo = item.resolution || (item.codec ? item.codec.toUpperCase() : (isAudio ? 'AUDIO' : 'VIDEO'));

    html += `
      <div class="media-card" onclick="playMedia(${item.id})">
        <div class="card-poster ${isAudio ? 'audio-poster' : ''}">
          ${item.thumbnail_path 
            ? `<img src="/api/thumbnail/${item.id}" alt="${item.title}" loading="lazy">` 
            : `<div class="card-poster-fallback">${isAudio ? '🎵' : '🎬'}</div>`}
          <div class="poster-overlay">
            <button class="play-action-btn" title="Play on MPV">▶</button>
          </div>
          <div class="poster-badge">${badgeInfo}</div>
        </div>
        <div class="card-content">
          <div class="card-title" title="${item.title}">${item.title}</div>
          <div class="card-subtitle" title="${subtitle}">${subtitle}</div>
          <div class="card-meta-row">
            <span>⏱ ${durationStr}</span>
            <button class="fav-btn ${isFav ? 'active' : ''}" onclick="toggleFavorite(${item.id}, event)" title="${isFav ? 'Unfavorite' : 'Favorite'}">
              ${isFav ? '★' : '☆'}
            </button>
          </div>
        </div>
      </div>
    `;
  }
  html += '</div>';
  container.innerHTML = html;
}

function renderDirectoriesView() {
  const container = document.getElementById('content-container');
  let html = `
    <div class="storage-view">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h2>Configured Media Directories</h2>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem;">
            RaspiMedia operates in <strong>READ-ONLY</strong> mode. Media files are never moved, renamed, or modified.
          </p>
        </div>
      </div>

      <div style="background: var(--bg-card); border: 1px solid var(--border-glass); border-radius: var(--radius-md); padding: 1.25rem; display: flex; gap: 0.75rem;">
        <input type="text" id="input-new-dir" class="search-input" placeholder="Enter absolute folder path (e.g. /mnt/media or /mnt/storage/Music)" style="flex: 1;">
        <button class="btn btn-primary" onclick="handleAddDirectory()">+ Add Directory</button>
      </div>

      <div style="display: flex; flex-direction: column; gap: 1rem;">
  `;

  if (state.directories.length === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">📁</div>
        <div class="empty-title">No media directories configured</div>
        <div class="empty-desc">Add your existing music and movie folder paths above to start building your library.</div>
      </div>
    `;
  } else {
    for (const dir of state.directories) {
      let badgeClass = 'ready';
      let badgeLabel = 'Ready (Readable)';
      if (!dir.exists) {
        badgeClass = 'missing';
        badgeLabel = 'Storage Missing / Unmounted';
      } else if (!dir.readable) {
        badgeClass = 'error';
        badgeLabel = 'Permission Error';
      }

      html += `
        <div class="dir-card">
          <div style="display: flex; flex-direction: column; gap: 0.35rem;">
            <div class="dir-path">${dir.path}</div>
            ${dir.warning ? `<div style="color: #fbbf24; font-size: 0.8rem;">⚠️ ${dir.warning}</div>` : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 1rem;">
            <span class="dir-status-badge ${badgeClass}">${badgeLabel}</span>
            <button class="btn" onclick="handleRemoveDirectory('${dir.path}')" style="color: #fb7185; border-color: rgba(244,63,94,0.3);">Remove</button>
          </div>
        </div>
      `;
    }
  }

  html += `</div></div>`;
  container.innerHTML = html;
}

async function handleAddDirectory() {
  const input = document.getElementById('input-new-dir');
  const path = input.value.trim();
  if (!path) return;

  try {
    const res = await fetch('/api/config/directories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory: path, action: 'add' }),
    });
    if (res.ok) {
      showToast(`Added media directory: ${path}`, 'success');
      input.value = '';
      fetchStatus();
      triggerScan();
    }
  } catch (err) {
    showToast('Failed to add directory', 'error');
  }
}

async function handleRemoveDirectory(path) {
  try {
    const res = await fetch('/api/config/directories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory: path, action: 'remove' }),
    });
    if (res.ok) {
      showToast(`Removed media directory: ${path}`, 'info');
      fetchStatus();
      triggerScan();
    }
  } catch (err) {
    showToast('Failed to remove directory', 'error');
  }
}

function switchTab(tabName) {
  state.currentTab = tabName;
  state.currentFilter = 'all';

  // Update tabs UI
  document.querySelectorAll('#main-tabs .tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabName);
  });

  // Toggle sub-toolbar visibility
  const subToolbar = document.getElementById('sub-toolbar');
  const catPills = document.getElementById('category-pills');
  
  if (tabName === 'directories') {
    subToolbar.style.display = 'none';
  } else {
    subToolbar.style.display = 'flex';
    if (tabName === 'videos') {
      catPills.style.display = 'flex';
      catPills.innerHTML = `
        <button class="pill-btn active" data-filter="all">All</button>
        <button class="pill-btn" data-filter="movie">Movies</button>
        <button class="pill-btn" data-filter="series">Series</button>
        <button class="pill-btn" data-filter="other_video">Other Videos</button>
      `;
      bindFilterPills();
    } else if (tabName === 'music') {
      catPills.style.display = 'none';
    } else {
      catPills.style.display = 'none';
    }
  }

  fetchMedia();
}

function bindFilterPills() {
  document.querySelectorAll('#category-pills .pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#category-pills .pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentFilter = btn.getAttribute('data-filter');
      fetchMedia();
    });
  });
}

// Initialization & Event Listeners
document.addEventListener('DOMContentLoaded', () => {
  // Brand Click
  document.getElementById('brand-home').addEventListener('click', () => switchTab('videos'));

  // Main Tabs
  document.querySelectorAll('#main-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
  });

  // Sort Pills
  document.querySelectorAll('#sort-pills .pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#sort-pills .pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentSort = btn.getAttribute('data-sort');
      fetchMedia();
    });
  });

  // Global Search
  const searchInput = document.getElementById('global-search');
  let searchTimeout = null;
  searchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.searchQuery = e.target.value.trim();
      fetchMedia();
    }, 250);
  });

  // Keyboard shortcut '/' for search
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== searchInput) {
      e.preventDefault();
      searchInput.focus();
    }
  });

  // Rescan Button
  document.getElementById('btn-rescan').addEventListener('click', () => triggerScan(false));

  // Storage Settings Button
  document.getElementById('btn-open-storage').addEventListener('click', () => switchTab('directories'));

  // Playback Controls
  document.getElementById('btn-play-pause').addEventListener('click', () => controlPlayback('toggle'));
  document.getElementById('btn-stop').addEventListener('click', () => controlPlayback('stop'));
  document.getElementById('btn-seek-back').addEventListener('click', () => controlPlayback('seek', -10));
  document.getElementById('btn-seek-fwd').addEventListener('click', () => controlPlayback('seek', 10));

  // Progress Bar Scrubbing
  const progressBar = document.getElementById('progress-bar');
  progressBar.addEventListener('click', (e) => {
    if (state.playerState.duration > 0) {
      const rect = progressBar.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const pct = clickX / rect.width;
      const targetSec = pct * state.playerState.duration;
      controlPlayback('seek', targetSec, 'absolute');
    }
  });

  // Volume Slider
  const volSlider = document.getElementById('volume-slider');
  volSlider.addEventListener('input', (e) => {
    controlPlayback('volume', parseFloat(e.target.value));
  });

  // Initial Data Load
  fetchStatus();
  fetchStats();
  switchTab('videos');

  // Periodic polling for MPV status
  setInterval(pollPlayback, 1500);
});
