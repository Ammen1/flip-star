// ─── TikTok-grade Create Page ──────────────────────────────────────────────
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { 
  Home, Film, Plus, PlusSquare, MessageCircle, User, Search, Settings, X, 
  Image as ImageIcon, Video, Hash, Type, Upload, Music, Volume2, VolumeX, 
  Play, Pause, RotateCw, RefreshCw, Camera, Mic, MicOff, Sparkles, Palette, 
  ChevronDown, ChevronLeft, ChevronRight, Check, AlertCircle, Trash2,
  Zap, ZapOff, Square, FileText, Eye, Bookmark, Share2, ArrowLeft, Heart, Coins
} from 'lucide-react';
import api from '../api';
import { useTheme } from '../contexts/ThemeContext';
import realtimeService from '../services/RealtimeService';

const FILTERS = [
  { id:'none',      name:'Original', css:'none' },
  { id:'grayscale', name:'B&W',      css:'grayscale(100%)' },
  { id:'sepia',     name:'Vintage',  css:'sepia(70%)' },
  { id:'warm',      name:'Warm',     css:'saturate(1.5) hue-rotate(-15deg)' },
  { id:'cool',      name:'Cool',     css:'saturate(1.3) hue-rotate(20deg)' },
  { id:'vibrant',   name:'Vibrant',  css:'saturate(2) contrast(1.1)' },
  { id:'fade',      name:'Fade',     css:'brightness(1.15) contrast(0.82) saturate(0.7)' },
  { id:'drama',     name:'Drama',    css:'contrast(1.5) brightness(0.85)' },
  { id:'neon',      name:'Neon',     css:'saturate(2.2) hue-rotate(280deg) brightness(1.15)' },
  { id:'golden',    name:'Golden',   css:'sepia(55%) saturate(1.4) hue-rotate(-10deg)' },
];

const SPEEDS = ['0.3x', '0.5x', '1x', '2x', '3x'];
const MAX_REC = 480;

const TEXT_COLORS = [
  '#FFFFFF', '#000000', '#FF3B57', '#DA9B2A', 
  '#3B82F6', '#10B981', '#8B5CF6', '#F97316',
  '#EC4899', '#14B8A6', '#EAB308', '#6366F1'
];

// ── SVG Progress Ring ────────────────────────────────────────────────────────
function ProgressRing({ radius, stroke, progress, color }) {
  const r = radius - stroke / 2;
  const circ = r * 2 * Math.PI;
  const offset = circ - (progress / 100) * circ;
  return (
    <svg width={radius*2} height={radius*2}
      style={{ position:'absolute', top:0, left:0, transform:'rotate(-90deg)', pointerEvents:'none' }}>
      <circle stroke={color} fill="none" strokeWidth={stroke} r={r} cx={radius} cy={radius}
        strokeDasharray={`${circ} ${circ}`} strokeDashoffset={offset}
        strokeLinecap="round" style={{ transition:'stroke-dashoffset 0.5s linear' }} />
    </svg>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export function EnhancedPostPage({ user, onBack, onPostSuccess, onNavHome, onNavReels, onNavMessages, onNavProfile, unreadDmCount = 0, onShowCoinPurchase }) {
  const { colors: T } = useTheme();
  // Stage
  const [stage, setStage] = useState('capture'); // 'capture' | 'details'
  const [captureMode, setCaptureMode] = useState('upload'); // 'upload' | 'camera'
  const [camMode, setCamMode] = useState('photo'); // 'video' | 'photo'

  // File
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [isVideoFile, setIsVideoFile] = useState(false);

  // Camera
  const [facingMode, setFacingMode] = useState('user');
  const [flashOn, setFlashOn] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recTime, setRecTime] = useState(0);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [recProgress, setRecProgress] = useState(0);
  const [selectedFilter, setSelectedFilter] = useState('none');
  const [selectedSpeed, setSelectedSpeed] = useState('1x');
  const [showFilters, setShowFilters] = useState(false);
  const [showSpeeds, setShowSpeeds] = useState(false);

  // Text overlays
  const [textOverlays, setTextOverlays] = useState([]);
  const [showTextInput, setShowTextInput] = useState(false);
  const [currentText, setCurrentText] = useState('');
  const [textColor, setTextColor] = useState('#ffffff');
  const [textStyle, setTextStyle] = useState('bold');   // bold|plain|outline|neon|highlight
  const [textAlign, setTextAlign] = useState('center'); // left|center|right
  const [textFontSize, setTextFontSize] = useState(22);
  const [dragging, setDragging] = useState(null); // { id, startX, startY, origX, origY }

  // Toast
  const [successMsg, setSuccessMsg] = useState('');

  // Sound
  const [backgroundSound, setBackgroundSound] = useState(null);
  const [showSoundSheet, setShowSoundSheet] = useState(false);
  const [isPlayingSound, setIsPlayingSound] = useState(false);
  const [origVol, setOrigVol] = useState(100);
  const [addedVol, setAddedVol] = useState(80);
  const [showVolMixer, setShowVolMixer] = useState(false);
  const [customAudioFile, setCustomAudioFile] = useState(null);

  // Post
  const [caption, setCaption] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [showSuccess, setShowSuccess] = useState(false);
  const [showInsufficientCoins, setShowInsufficientCoins] = useState(false);
  const [postCost, setPostCost] = useState(0);

  // Debug modal state changes
  useEffect(() => {
    console.log('[INSUFFICIENT_COINS] Modal state changed:', showInsufficientCoins);
  }, [showInsufficientCoins]);

  // Refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const timerRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);
  const streamRef = useRef(null);
  const cameraGenRef = useRef(0);        // incremented on every startCamera/stopCamera to cancel in-flight getUserMedia
  const liveRef = useRef({ filter: 'none', overlays: [] });
  const isRecordingRef = useRef(false); // sync ref so onMouseDown guard doesn't rely on stale state
  const recordingStartRef = useRef(0);  // timestamp when recording began (for ghost-click guard)
  const audioCtxRef = useRef(null);     // Web Audio context for mic+bg mixing into recorder
  const monitorAudioRef = useRef(null); // separate Audio element so user hears bg WITHOUT routing through mic
  const fileInputRef = useRef(null);
  const audioFileInputRef = useRef(null);
  const previewContainerRef = useRef(null);
  const previewVideoRef = useRef(null);

  // ── Drafts state ─────────────────────────────────────────────────────────
  const [drafts, setDrafts] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ep_drafts') || '[]'); } catch { return []; }
  });
  const [showDrafts, setShowDrafts] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewMuted, setPreviewMuted] = useState(false);

  // ── Keep liveRef synced ──────────────────────────────────────────────────
  useEffect(() => { liveRef.current.filter = selectedFilter; }, [selectedFilter]);
  useEffect(() => { liveRef.current.overlays = textOverlays; }, [textOverlays]);

  // ── Canvas draw loop ─────────────────────────────────────────────────────
  const startDrawLoop = useCallback(() => {
    const draw = () => {
      const vid = videoRef.current;
      const cvs = canvasRef.current;
      if (!vid || !cvs) return;
      const ctx = cvs.getContext('2d');
      cvs.width = vid.videoWidth || 360;
      cvs.height = vid.videoHeight || 640;
      const f = liveRef.current.filter;
      ctx.filter = f === 'none' ? 'none' : (FILTERS.find(x => x.id === f)?.css || 'none');
      ctx.drawImage(vid, 0, 0, cvs.width, cvs.height);
      // ── Bake text overlays into the canvas frame ──
      ctx.filter = 'none';
      (liveRef.current.overlays || []).forEach(ov => {
        const px = ov.x / 100 * cvs.width;
        const py = ov.y / 100 * cvs.height;
        const fs = ov.fontSize * (cvs.width / 360);
        ctx.save();
        ctx.font = `800 ${fs}px system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const tw = ctx.measureText(ov.text).width;
        const pad = fs * 0.35;
        ctx.fillStyle = 'rgba(0,0,0,0.28)';
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(px - tw/2 - pad, py - fs/2 - pad*0.5, tw + pad*2, fs + pad, fs*0.3);
        else ctx.rect(px - tw/2 - pad, py - fs/2 - pad*0.5, tw + pad*2, fs + pad);
        ctx.fill();
        ctx.shadowColor = 'rgba(0,0,0,0.6)';
        ctx.shadowBlur = 8;
        ctx.shadowOffsetY = 2;
        ctx.fillStyle = ov.color;
        ctx.fillText(ov.text, px, py);
        ctx.restore();
      });
      animFrameRef.current = requestAnimationFrame(draw);
    };
    draw();
  }, []);

  const stopDrawLoop = useCallback(() => {
    if (animFrameRef.current) { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null; }
  }, []);

  // ── Cleanup helper (defined early so useEffects below can reference it) ──
  const _cleanupAudio = () => {
    // Stop preview audio (sound selection preview)
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setIsPlayingSound(false);
    // Stop monitor audio (bg music during recording)
    if (monitorAudioRef.current) {
      monitorAudioRef.current.pause();
      monitorAudioRef.current.src = '';
      monitorAudioRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch (_) {}
      audioCtxRef.current = null;
    }
  };

  // ── Camera start/stop ───────────────────────────────────────────────────
  const startCamera = useCallback(async () => {
    const gen = ++cameraGenRef.current;  // capture generation token
    try {
      setCameraLoading(true);
      if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }

      console.log('Starting camera with facingMode:', facingMode);

      // Check if mediaDevices is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Your browser does not support camera access. Please use Chrome, Firefox, or Edge.');
        return;
      }

      // First, try to enumerate devices to check if cameras are available
      let devices = [];
      try {
        devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(d => d.kind === 'videoinput');
        console.log('Available video devices:', videoDevices);
        if (videoDevices.length === 0) {
          throw new Error('No camera devices found on this system');
        }
      } catch (enumError) {
        console.warn('Could not enumerate devices:', enumError);
        // Continue anyway - this might be a permission issue that will be resolved by getUserMedia
      }

      let s;
      let lastError = null;

      // Strategy: Start with the most flexible constraints first, then get stricter
      const constraintAttempts = [
        // Attempt 1: Most flexible - just request video and audio
        {
          name: 'Basic video/audio',
          constraints: { video: true, audio: true }
        },
        // Attempt 2: With facingMode
        {
          name: 'With facingMode',
          constraints: { video: { facingMode: facingMode }, audio: true }
        },
        // Attempt 3: With basic resolution
        {
          name: 'With basic resolution',
          constraints: { video: { facingMode: facingMode, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: true }
        },
        // Attempt 4: Full iPhone-compatible constraints
        {
          name: 'Full constraints',
          constraints: {
            video: {
              facingMode: facingMode,
              width: { ideal: 1280, max: 1920 },
              height: { ideal: 720, max: 1080 },
              aspectRatio: { ideal: 16/9 },
              frameRate: { ideal: 30, max: 60 },
            },
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          }
        }
      ];

      for (const attempt of constraintAttempts) {
        try {
          console.log(`Attempting camera with: ${attempt.name}`, attempt.constraints);
          s = await navigator.mediaDevices.getUserMedia(attempt.constraints);
          console.log(`Camera access successful with: ${attempt.name}`);
          break; // Success! Exit the loop
        } catch (error) {
          lastError = error;
          console.warn(`Camera attempt failed (${attempt.name}):`, error.name, error.message);
          // Continue to next attempt
        }
      }

      if (!s) {
        throw lastError || new Error('Camera access failed after all attempts');
      }

      // If stopCamera was called while we were waiting, discard the stream immediately
      if (gen !== cameraGenRef.current) { s.getTracks().forEach(t => t.stop()); return; }
      streamRef.current = s;
      if (videoRef.current) { videoRef.current.srcObject = s; await videoRef.current.play(); }
      startDrawLoop();
    } catch (e) {
      console.error('Camera error - all attempts failed:', e);
      console.error('Error details:', e.name, e.message);

      // Show user-friendly error message based on error type
      let errorMessage = 'Camera access failed. ';
      switch (e.name) {
        case 'NotAllowedError':
        case 'PermissionDeniedError':
          errorMessage += 'Camera permission was denied. Please:\n\n1. Click the lock/info icon in your browser address bar\n2. Allow camera access\n3. Refresh the page and try again';
          break;
        case 'NotFoundError':
          errorMessage += 'No camera found on this device. Please:\n\n1. Ensure your camera is connected and not in use by another app\n2. Check if your camera is enabled in system settings\n3. Try refreshing the page and allowing camera permissions when prompted\n4. If using a laptop, make sure the camera is not covered or disabled';
          break;
        case 'NotReadableError':
          errorMessage += 'Camera is already in use by another application (Zoom, Teams, another browser tab, etc.).\n\nPlease close other apps using the camera and try again.';
          break;
        case 'OverconstrainedError':
          errorMessage += 'Your camera does not support the requested resolution. The app will try with lower quality automatically.';
          break;
        case 'TypeError':
          errorMessage += 'Camera not supported in this browser. Please use Chrome, Firefox, or Edge.';
          break;
        default:
          errorMessage += `Please check your permissions and try again.\n\nError: ${e.message}`;
      }
      alert(errorMessage);
    } finally {
      setCameraLoading(false);
    }
  }, [facingMode, startDrawLoop]);

  const stopCamera = useCallback(() => {
    cameraGenRef.current++;              // invalidate any in-flight startCamera
    stopDrawLoop();
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (videoRef.current) { videoRef.current.srcObject = null; }
    clearInterval(timerRef.current);
  }, [stopDrawLoop]);

  // Stop camera when captureMode or facingMode changes
  useEffect(() => {
    if (captureMode === 'camera') { startCamera(); }
    else { stopCamera(); }
    return () => stopCamera();
  }, [captureMode, facingMode]); // eslint-disable-line

  // Hard-stop camera+audio the moment we leave the capture stage
  useEffect(() => {
    if (stage !== 'capture') {
      stopCamera();
      _cleanupAudio();
    }
  }, [stage]); // eslint-disable-line

  // Release camera+audio on component unmount (e.g. user navigates away)
  useEffect(() => {
    return () => {
      stopCamera();
      _cleanupAudio();
    };
  }, []); // eslint-disable-line

  // ── Recording ───────────────────────────────────────────────────────────
  const startRecording = async () => {
    // ── LOCK IMMEDIATELY before any async work so no re-entrant calls slip through ──
    if (isRecordingRef.current) return;
    if (!streamRef.current) {
      alert('Camera not ready. Please wait a moment and try again.');
      return;
    }
    isRecordingRef.current = true;   // set lock NOW — before awaits
    recordingStartRef.current = Date.now();

    // Kill any stale timer / audio from a previous session
    clearInterval(timerRef.current);
    _cleanupAudio();
    chunksRef.current = [];
    setRecTime(0);
    setRecProgress(0);

    // ── Step 1: canvas video track ───────────────────────────────────────
    let videoTrack = null;
    try {
      const cvs = canvasRef.current;
      if (cvs && cvs.captureStream) {
        videoTrack = cvs.captureStream(30).getVideoTracks()[0] || null;
      }
    } catch (_) {}

    // ── Step 2: audio track ──────────────────────────────────────────────
    // Strategy: mix mic (origVol%) + bg audio (addedVol%) into recorder.
    // ECHO FIX: bg audio goes ONLY into the recorder (dest), NOT ctx.destination.
    // A separate Audio element is used for monitoring so the user hears the music
    // without routing it through ctx.destination → speaker → mic → echo loop.
    let audioTracks = streamRef.current.getAudioTracks();
    if (customAudioFile) {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        audioCtxRef.current = ctx;
        const dest = ctx.createMediaStreamDestination();

        // Mic at origVol (0 = full lipsync, 100 = full voice)
        if (audioTracks.length > 0) {
          const micSrc  = ctx.createMediaStreamSource(new MediaStream(audioTracks));
          const micGain = ctx.createGain();
          micGain.gain.value = origVol / 100;
          micSrc.connect(micGain);
          micGain.connect(dest);
        }

        // Decode bg file into AudioBuffer — loop it, feed ONLY into recorder (not speakers)
        const arrayBuf = await customAudioFile.arrayBuffer();
        const audioBuf = await ctx.decodeAudioData(arrayBuf);
        const bgSrc = ctx.createBufferSource();
        bgSrc.buffer = audioBuf;
        bgSrc.loop = true;
        const bgGain = ctx.createGain();
        bgGain.gain.value = addedVol / 100;
        bgSrc.connect(bgGain);
        bgGain.connect(dest); // recorder only — no ctx.destination → no mic echo
        bgSrc.start(0);

        audioTracks = dest.stream.getAudioTracks();

        // Separate Audio element for monitoring (user hears music but mic doesn't double-pick it up)
        const monitor = new Audio();
        monitor.src = URL.createObjectURL(customAudioFile);
        monitor.volume = addedVol / 100;
        monitor.loop = true;
        monitor.play().catch(() => {});
        monitorAudioRef.current = monitor;

        console.log('[RECORDER] mix: mic', origVol + '%, bg', addedVol + '%');
      } catch (mixErr) {
        console.warn('[RECORDER] Web Audio mix failed, raw mic fallback:', mixErr);
        _cleanupAudio();
        audioTracks = streamRef.current.getAudioTracks();
      }
    }

    // ── Step 3: assemble MediaStream ─────────────────────────────────────
    const tracks = [
      ...(videoTrack ? [videoTrack] : []),
      ...audioTracks,
    ];
    const recordStream = tracks.length > 0 ? new MediaStream(tracks) : streamRef.current;

    // ── Step 4: pick best mimeType ───────────────────────────────────────
    const MIME_CANDIDATES = [
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
      'video/mp4',
    ];
    const mimeType = MIME_CANDIDATES.find(m => MediaRecorder.isTypeSupported(m)) || '';
    let mr;
    try {
      mr = new MediaRecorder(recordStream, mimeType ? { mimeType } : {});
    } catch (_) {
      try { mr = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : {}); }
      catch (e2) {
        _cleanupAudio();
        isRecordingRef.current = false;
        alert('Recording not supported on this browser: ' + e2.message);
        return;
      }
    }

    const actualMime = mr.mimeType || mimeType || 'video/webm';
    const ext = actualMime.includes('mp4') ? 'mp4' : 'webm';

    // ── Step 5: wire events ──────────────────────────────────────────────
    mr.ondataavailable = e => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };

    mr.onstop = () => {
      const chunks = chunksRef.current;
      if (!chunks.length) {
        alert('Recording produced no data. Please try again.');
        isRecordingRef.current = false;
        setIsRecording(false);
        return;
      }
      const blob = new Blob(chunks, { type: actualMime });
      if (blob.size === 0) {
        alert('Recorded file is empty. Please try again.');
        isRecordingRef.current = false;
        setIsRecording(false);
        return;
      }
      const file = new File([blob], `rec_${Date.now()}.${ext}`, { type: actualMime });
      const url  = URL.createObjectURL(blob);
      stopCamera();
      setSelectedFile(file);
      setPreview(url);
      setIsVideoFile(true);
      setCaptureMode('upload');
      setStage('details');
      isRecordingRef.current = false;
      setIsRecording(false);
    };

    mr.onerror = e => {
      console.error('[RECORDER] error', e);
      _cleanupAudio();
      isRecordingRef.current = false;
      setIsRecording(false);
      alert('Recording error: ' + (e.error?.message || 'unknown'));
    };

    // ── Step 6: go ───────────────────────────────────────────────────────
    mediaRecorderRef.current = mr;
    mr.start(250);
    setIsRecording(true);

    timerRef.current = setInterval(() => {
      setRecTime(t => {
        const next = t + 1;
        setRecProgress((next / MAX_REC) * 100);
        if (next >= MAX_REC) stopRecording();
        return next;
      });
    }, 1000);
  };

  const stopRecording = () => {
    if (!isRecordingRef.current) return;
    // Ghost-click guard: ignore stop calls within 1s of start
    if (Date.now() - recordingStartRef.current < 1000) return;

    clearInterval(timerRef.current);
    _cleanupAudio(); // stop monitor + AudioContext immediately (no music after stop)

    const mr = mediaRecorderRef.current;
    if (mr && mr.state === 'recording') {
      try { mr.requestData(); } catch (_) {}
      mr.stop(); // triggers onstop asynchronously
    } else {
      isRecordingRef.current = false;
      setIsRecording(false);
    }
  };

  // ── Photo capture ───────────────────────────────────────────────────────
  const takePhoto = () => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    cvs.toBlob(blob => {
      const file = new File([blob], `photo_${Date.now()}.jpg`, { type: 'image/jpeg' });
      const url = URL.createObjectURL(blob);
      setSelectedFile(file);
      setPreview(url);
      setIsVideoFile(false);
      stopCamera();
      setCaptureMode('upload');
      setStage('details');
    }, 'image/jpeg', 0.92);
  };

  // ── File upload from device ─────────────────────────────────────────────
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setIsVideoFile(file.type.startsWith('video/'));

    // Handle different file types
    if (file.type.startsWith('video/')) {
      // For videos, create a thumbnail
      createVideoThumbnail(file);
    } else {
      // For images, use object URL as before
      const url = URL.createObjectURL(file);
      setPreview(url);
    }
    setStage('details');
  };

  const createVideoThumbnail = (file) => {
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    video.preload = 'metadata';
    video.src = URL.createObjectURL(file);

    video.onloadedmetadata = () => {
      // Set canvas dimensions to match video
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      // Seek to 1 second (or first frame if video is shorter)
      const seekTime = Math.min(1, video.duration);
      video.currentTime = seekTime;
    };

    video.onseeked = () => {
      // Draw the video frame to canvas
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Convert canvas to blob and then to data URL
      canvas.toBlob((blob) => {
        const url = URL.createObjectURL(blob);
        setPreview(url);
      }, 'image/jpeg', 0.8);

      // Clean up the video object URL
      URL.revokeObjectURL(video.src);
    };

    video.onerror = () => {
      console.error('Error loading video for thumbnail generation');
      // Fallback: use the original video URL
      const url = URL.createObjectURL(file);
      setPreview(url);
    };
  };

  // ── Overlay drag helpers ─────────────────────────────────────────────────
  // Note: React synthetic onTouch* handlers are passive by default in React 17+,
  // so preventDefault is a no-op. We guard with e.cancelable to avoid warnings,
  // and rely on `touch-action: none` CSS on the drag elements to suppress scroll.
  const startOverlayDrag = (e, id) => {
    e.stopPropagation();
    if (e.cancelable && e.preventDefault) e.preventDefault();
    const pt = e.touches?.[0] || e;
    const ov = textOverlays.find(o => o.id === id);
    if (!ov || dragging) return; // Prevent starting new drag if already dragging
    setDragging({ id, sx: pt.clientX, sy: pt.clientY, ox: ov.x, oy: ov.y });
  };
  const moveOverlayDrag = (e) => {
    if (!dragging) return;
    if (e.cancelable && e.preventDefault) e.preventDefault();
    const pt = e.touches?.[0] || e;
    const el = previewContainerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const dx = ((pt.clientX - dragging.sx) / r.width) * 100;
    const dy = ((pt.clientY - dragging.sy) / r.height) * 100;
    // Update only the dragged overlay position
    setTextOverlays(prev => prev.map(o => o.id === dragging.id
      ? { ...o, x: Math.max(5, Math.min(95, dragging.ox + dx)), y: Math.max(5, Math.min(95, dragging.oy + dy)) }
      : o));
  };
  const endOverlayDrag = (e) => {
    if (e && e.cancelable && e.preventDefault) e.preventDefault();
    setDragging(null);
  };

  // Attach native non-passive touch listeners on the drag container so we can
  // actually call preventDefault during overlay drags (React listeners are
  // registered as passive in React 17+, which makes preventDefault a no-op
  // and prints "Unable to preventDefault inside passive event listener").
  useEffect(() => {
    const el = previewContainerRef.current;
    if (!el) return;
    const onMove = (ev) => {
      if (!dragging) return;
      if (ev.cancelable) ev.preventDefault();
      moveOverlayDrag(ev);
    };
    const onEnd = (ev) => {
      if (!dragging) return;
      if (ev.cancelable) ev.preventDefault();
      setDragging(null);
    };
    el.addEventListener('touchmove', onMove, { passive: false });
    el.addEventListener('touchend', onEnd, { passive: false });
    el.addEventListener('touchcancel', onEnd, { passive: false });
    return () => {
      el.removeEventListener('touchmove', onMove);
      el.removeEventListener('touchend', onEnd);
      el.removeEventListener('touchcancel', onEnd);
    };
  }, [dragging]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Overlay CSS helper ────────────────────────────────────────────────────
  const overlayCSS = (ov) => {
    const base = { 
      fontWeight: 800, 
      fontSize: `${ov.fontSize || 22}px`, 
      color: ov.color, 
      textAlign: ov.align || 'center', 
      userSelect: 'none', 
      cursor: 'move', 
      whiteSpace: 'pre-wrap', 
      maxWidth: '260px',
      lineHeight: 1.2,
      display: 'inline-block'
    };
    switch (ov.style) {
      case 'plain':     return { ...base, textShadow: '0 2px 8px rgba(0,0,0,0.9)', background: 'transparent', padding: '4px 6px', borderRadius: 0 };
      case 'outline':   return { ...base, textShadow: 'none', WebkitTextStroke: `2px ${ov.color}`, color: 'transparent', background: 'transparent', padding: '4px 6px' };
      case 'neon':      return { ...base, textShadow: `0 0 8px ${ov.color}, 0 0 20px ${ov.color}, 0 0 40px ${ov.color}`, background: 'transparent', padding: '4px 6px' };
      case 'highlight': return { ...base, background: ov.color, color: ov.color === '#fff' || ov.color === '#ffffff' ? '#000' : '#fff', padding: '4px 12px', borderRadius: 6 };
      default:          return { ...base, background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)', padding: '4px 10px', borderRadius: 8, textShadow: '0 1px 4px rgba(0,0,0,0.6)' };
    }
  };

  // ── Draft helpers ─────────────────────────────────────────────────────
  const saveDraft = async () => {
    const draftId = Date.now();
    let thumbData = null;
    if (preview && !isVideoFile) {
      try {
        const resp = await fetch(preview);
        const blob = await resp.blob();
        thumbData = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob); });
      } catch {}
    }
    const draft = { id: draftId, thumbData, isVideo: isVideoFile, caption, hashtags, selectedFilter, textOverlays, createdAt: new Date().toISOString() };
    const updated = [draft, ...drafts].slice(0, 10);
    setDrafts(updated);
    try {
      localStorage.setItem('ep_drafts', JSON.stringify(updated.map(d => ({ ...d, thumbData: d.isVideo ? null : d.thumbData }))));
    } catch { try { localStorage.setItem('ep_drafts', JSON.stringify(updated.map(d => ({ ...d, thumbData: null })))); } catch {} }
    setSuccessMsg('Draft saved!');
    setTimeout(() => { setSuccessMsg(''); onBack?.(); }, 1200);
  };

  const loadDraft = (draft) => {
    setCaption(draft.caption || '');
    setHashtags(draft.hashtags || '');
    setSelectedFilter(draft.selectedFilter || 'none');
    setTextOverlays(draft.textOverlays || []);
    setIsVideoFile(draft.isVideo || false);
    // For videos, thumbData might be null - still proceed to capture stage to re-record
    if (draft.thumbData) {
      setPreview(draft.thumbData);
      setStage('details');
    } else {
      // Video draft without preview - go to capture to re-record
      setPreview(null);
      setSelectedFile(null);
      setCaptureMode('camera');
      setStage('capture');
    }
    setShowDrafts(false);
  };

  const deleteDraft = (id) => {
    const updated = drafts.filter(d => d.id !== id);
    setDrafts(updated);
    try { localStorage.setItem('ep_drafts', JSON.stringify(updated)); } catch {}
  };

  // ── Text overlay ────────────────────────────────────────────────────────
  const addTextOverlay = () => {
    if (!currentText.trim()) return;
    setTextOverlays(prev => [...prev, {
      id: Date.now(), text: currentText, color: textColor,
      style: textStyle, align: textAlign, fontSize: textFontSize,
      x: 50, y: 50,
    }]);
    setCurrentText('');
    setShowTextInput(false);
  };

  const removeOverlay = (id) => setTextOverlays(prev => prev.filter(o => o.id !== id));

  // ── Sound ───────────────────────────────────────────────────────────────
  const selectSound = (s) => {
    setBackgroundSound(s);
    setShowSoundSheet(false);
    if (audioRef.current && s.url) {
      audioRef.current.src = s.url;
      audioRef.current.volume = addedVol / 100;
    }
  };

  const toggleSoundPlay = () => {
    if (!audioRef.current) return;
    if (isPlayingSound) { audioRef.current.pause(); setIsPlayingSound(false); }
    else { 
      audioRef.current.play().catch((err) => {
        if (err.name !== 'AbortError') console.log('Play error:', err);
      }); 
      setIsPlayingSound(true); 
    }
  };

  const handleCustomAudio = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const sound = { id: 'custom', name: file.name, artist: 'Your audio', dur: '?', url: URL.createObjectURL(file) };
    setCustomAudioFile(file);
    selectSound(sound);
  };

  // ── Post / upload ───────────────────────────────────────────────────────
  const handlePost = async () => {
    if (!selectedFile || isUploading) return;
    // Guard: file must have actual content
    if (selectedFile.size === 0) {
      alert('The recorded file is empty. Please record again.');
      return;
    }
    console.log('[POST] file:', selectedFile.name, selectedFile.type, selectedFile.size, 'bytes');
    
    // Check coin balance before posting
    try {
      const walletConfig = await api.request('/wallet/config/').catch(err => {
        console.error('Wallet config error:', err);
        return { cost_post_create_non_campaign: 0 };
      });
      
      const coinBalance = await api.request('/coins/balance/').catch(err => {
        console.error('Coin balance error:', err);
        return { balance: 0 };
      });
      
      const cost = walletConfig.cost_post_create_non_campaign || 0;
      const balance = coinBalance.balance || 0;
      
      console.log('[POST] Coin check:', { cost, balance, sufficient: balance >= cost });
      
      if (cost > 0 && balance < cost) {
        console.log('[POST] Showing insufficient coins modal', { cost, balance });
        setPostCost(cost);
        setShowInsufficientCoins(true);
        // Force a re-render by using a small timeout
        setTimeout(() => console.log('[POST] Modal state set:', showInsufficientCoins), 100);
        return;
      }
    } catch (error) {
      console.error('Error checking coin balance:', error);
      // Continue with posting if balance check fails
    }
    
    setIsUploading(true);
    setUploadProgress(0);
    try {
      const fd = new FormData();
      fd.append('file', selectedFile, selectedFile.name);
      fd.append('caption', caption);
      if (hashtags) fd.append('hashtags', hashtags);
      if (customAudioFile) {
        fd.append('audio_file', customAudioFile);
        fd.append('audio_volume_level', addedVol);
        fd.append('original_volume_level', origVol);
      }
      if (textOverlays.length) {
        fd.append('overlay_text', JSON.stringify(textOverlays));
      }
      // Real upload progress from XHR.  While the server is still
      // processing after the bytes are uploaded, cap at 97% so the bar
      // doesn't appear frozen — the final 100% fires on successful response.
      let lastReported = 0;
      const newReel = await api.createPost(fd, {
        onProgress: (pct) => {
          lastReported = pct;
          setUploadProgress(Math.min(pct, 97));
        },
      }).catch(err => {
        console.error('[POST] Upload error:', err);
        setIsUploading(false);
        
        // Check if error is due to insufficient coins
        if (err?.error && err.error.includes('Insufficient') || err?.required_coins) {
          const requiredCoins = err.required_coins || postCost || 2;
          console.log('[POST] Backend returned insufficient coins error, showing modal');
          setPostCost(requiredCoins);
          setShowInsufficientCoins(true);
          return;
        }
        
        // Only show alert for other errors (not insufficient coins)
        alert(`Upload failed: ${err?.error || err?.message || 'Server error'}\n\nSee console for details`);
      });
      
      // Broadcast new post to all users for real-time updates
      if (newReel && newReel.id) {
        realtimeService.broadcastNewPost({
          id: newReel.id,
          user: user,
          caption: caption,
          media: newReel.media || newReel.image,
          created_at: newReel.created_at || new Date().toISOString()
        });
        
        // Also broadcast feed refresh to ensure all tabs update
        realtimeService.broadcastFeedRefresh();
      }
      
      setUploadProgress(100);
      setShowSuccess(true);
      setTimeout(() => {
        setShowSuccess(false);
        if (newReel?.id && onPostSuccess) {
          onPostSuccess(newReel.id);
        } else {
          onBack?.();
        }
      }, 2000);
    } catch (e) {
      console.error('Upload failed', e);
      const detail = e?.traceback || e?.error || e?.message || String(e);
      alert(`Upload failed: ${e?.error || e?.message || 'Server error'}\n\nSee console for details.`);
      console.error('[UPLOAD TRACEBACK]', detail);
    } finally {
      setIsUploading(false);
    }
  };

  const fmtTime = (s) => `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
  const activeFilter = FILTERS.find(f => f.id === selectedFilter);

  const bottomNavItems = [
    { id: 'home',     label: 'Home',     Icon: Home,       action: onNavHome },
    { id: 'reels',    label: 'Reels',    Icon: Film,       action: onNavReels },
    { id: 'create',   label: 'New',      Icon: PlusSquare, action: null, isCreate: true },
    { id: 'messages', label: 'Messages', Icon: MessageCircle, action: onNavMessages, badge: unreadDmCount },
    { id: 'profile',  label: 'Profile',  Icon: User,       action: onNavProfile },
  ];

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: 'fixed', inset: 0, background: T.bg, zIndex: 4000,
      display: 'flex', flexDirection: 'column', color: T.txt, fontFamily: 'system-ui, sans-serif',
      paddingBottom: 64,
    }}>
      <style>{`
        @keyframes ep-pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.05)} }
        @keyframes ep-fade-in { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:translateY(0)} }
        @keyframes ep-spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes ep-success { 0%{transform:scale(0.7);opacity:0} 60%{transform:scale(1.1)} 100%{transform:scale(1);opacity:1} }
        .ep-btn { border:none; cursor:pointer; transition:all 0.15s; touch-action:manipulation; -webkit-tap-highlight-color:transparent; }
        .ep-btn:active { transform:scale(0.94); }
        .ep-filter-scroll::-webkit-scrollbar { display:none; }
        .ep-hash { color:${T.pri}; font-weight:700; }
      `}</style>

      {/* ── BOTTOM NAV BAR ──────────────────────────────────────────────── */}
      {window.innerWidth <= 768 ? (
      <nav style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: 60,
        background: T.bg,
        borderTop: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-around',
        zIndex: 5000,
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        boxShadow: 'none',
        overflow: 'visible',
      }}>
        <style>{`
          .ep-nav-btn { transition: transform 0.15s cubic-bezier(0.34,1.56,0.64,1); border: none; background: transparent; cursor: pointer; }
          .ep-nav-btn:active { transform: scale(0.82) !important; }
          .ep-nav-btn:active svg { fill: #000 !important; }
        `}</style>
        {bottomNavItems.map(({ id, label, Icon, action, isCreate, badge }) => {
          if (isCreate) return (
            <button key={id} className="ep-nav-btn"
              onClick={() => action?.()}
              style={{ 
                flex: 1,
                height: '100%',
                background: 'none', 
                border: 'none', 
                cursor: 'pointer', 
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'flex-start',
                position: 'relative',
                padding: '0 8px',
                overflow: 'visible',
                WebkitTapHighlightColor: 'transparent',
                outline: 'none',
              }}>
              <div style={{
                position: 'absolute',
                top: -18,
                left: '50%',
                transform: 'translateX(-50%)',
                width: 54,
                height: 54,
                borderRadius: '50%',
                background: 'linear-gradient(145deg, #8fc441 0%, #6ba835 100%)',
                boxShadow: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                border: '3px solid rgba(255,255,255,0.15)',
              }}>
                <Plus size={26} strokeWidth={2.8} color='#1A0A00' />
              </div>
            <span style={{ fontSize: 10, fontWeight: 500, color: '#8fc441', lineHeight: 1, marginTop: 'auto', paddingBottom: 4 }}>Create</span>
          </button>
        );
        return (
          <button key={id} className="ep-nav-btn"
              onClick={() => action?.()}
              style={{ 
                flex: 1,
                height: '100%',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 2,
                padding: '4px 8px',
                position: 'relative',
                WebkitTapHighlightColor: 'transparent !important',
                outline: 'none',
              }}>
              <div style={{
                position: 'relative',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Icon
                  size={24}
                  strokeWidth={1.8}
                  color={'#8fc441'}
                  fill={'none'}
                />
                {badge > 0 && (
                  <div style={{
                    position: 'absolute', top: -4, right: -6,
                    minWidth: 15, height: 15, borderRadius: 8,
                    background: '#EF4444', color: '#fff',
                    fontSize: 8, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: '0 3px', boxSizing: 'border-box',
                    border: '1.5px solid #fff', lineHeight: 1,
                  }}>
                    {badge > 99 ? '99+' : badge}
                  </div>
                )}
              </div>
              <span style={{ fontSize: 10, fontWeight: 500, color: '#8fc441', lineHeight: 1 }}>{label}</span>
            </button>
          );
        })}
      </nav>
      ) : null}

      {/* ── CAPTURE STAGE ─────────────────────────────────────────────── */}
      {stage === 'capture' && (
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>

          {captureMode === 'camera' ? (
            /* ── CAMERA VIEW (fullscreen 9:16) ── */
            <div ref={previewContainerRef} style={{ position: 'absolute', inset: 0, touchAction: dragging ? 'none' : 'auto' }}
              onMouseMove={moveOverlayDrag} onMouseUp={endOverlayDrag} onMouseLeave={endOverlayDrag}>
              {/* Camera loading indicator */}
              {cameraLoading && (
                <div style={{
                  position: 'absolute', inset: 0, background: T.bg,
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  zIndex: 1000,
                }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: '50%', background: T.pri,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    animation: 'spin 1s linear infinite',
                  }}>
                    <RefreshCw size={24} color="#8fc441" />
                  </div>
                  <div style={{ marginTop: 16, fontSize: 14, color: '#8fc441', fontWeight: 600 }}>
                    Starting camera...
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, color: '#8fc441' }}>
                    Please allow camera permissions if prompted
                  </div>
                  <style>{`
                    @keyframes spin {
                      from { transform: rotate(0deg); }
                      to { transform: rotate(360deg); }
                    }
                  `}</style>
                </div>
              )}
              {/* Hidden video source */}
              <video 
                ref={videoRef} 
                playsInline 
                muted 
                autoPlay
                playsinline
                webkit-playsinline
                style={{ position: 'absolute', opacity: 0, width: 1, height: 1 }} 
              />
              {/* Filtered canvas - contain to show full camera view without zoom, mirror for selfie */}
              <canvas ref={canvasRef}
                style={{ 
                  width: '100%', height: '100%', objectFit: 'contain', background: '#000', display: 'block',
                  transform: facingMode === 'user' ? 'scaleX(-1)' : 'none',
                  pointerEvents: 'none', // Don't capture touch events - let them pass to controls
                }} />

              {/* Text overlays ON camera preview — draggable */}
              {textOverlays.map(ov => (
                <div key={ov.id}
                  style={{ position: 'absolute', left: `${ov.x}%`, top: `${ov.y}%`, transform: 'translate(-50%,-50%)', zIndex: 20, touchAction: 'none' }}
                  onMouseDown={e => startOverlayDrag(e, ov.id)}
                  onTouchStart={e => startOverlayDrag(e, ov.id)}
                >
                  <div style={{ position: 'relative', ...overlayCSS(ov) }}>
                    {ov.text}
                    <div style={{ position: 'absolute', top: -10, right: -10, width: 20, height: 20, borderRadius: '50%', background: T.red, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: 11, zIndex: 21 }}
                      onMouseDown={e => e.stopPropagation()}
                      onTouchStart={e => e.stopPropagation()}
                      onClick={() => removeOverlay(ov.id)}>×</div>
                  </div>
                </div>
              ))}

              {/* Top bar */}
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, zIndex: 30,
                padding: 'max(12px, env(safe-area-inset-top)) 16px 12px',
                background: 'linear-gradient(to bottom, rgba(0,0,0,0.6) 0%, transparent 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              }}>
                <button className="ep-btn" 
                  onClick={() => { stopCamera(); setCaptureMode('upload'); }}
                  onTouchEnd={(e) => { e.preventDefault(); stopCamera(); setCaptureMode('upload'); }}
                  style={{ background: 'rgba(0,0,0,0.4)', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <X size={20} color="#8fc441" />
                </button>

                {/* Mode tabs — force light text on dark overlay so the Photo/
                    Video labels are readable regardless of theme. */}
                <div style={{ display: 'flex', gap: 6, background: 'rgba(0,0,0,0.4)', borderRadius: 24, padding: '4px 6px' }}>
                  {['photo','video'].map(m => (
                    <button key={m} className="ep-btn" 
                      onClick={() => setCamMode(m)}
                      onTouchEnd={(e) => { e.preventDefault(); setCamMode(m); }}
                      style={{
                        padding: '6px 14px', borderRadius: 20,
                        background: camMode === m ? T.pri : 'transparent',
                        color: '#8fc441',
                        fontSize: 13, fontWeight: 700,
                        textShadow: camMode === m ? 'none' : '0 1px 2px rgba(0,0,0,0.8)',
                      }}>
                      {m.charAt(0).toUpperCase() + m.slice(1)}
                    </button>
                  ))}
                </div>

                {/* Flash */}
                <button className="ep-btn" 
                  onClick={() => setFlashOn(f => !f)}
                  onTouchEnd={(e) => { e.preventDefault(); setFlashOn(f => !f); }}
                  style={{ background: 'rgba(0,0,0,0.4)', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {flashOn ? <Zap size={18} color="#8fc441" fill="#8fc441" /> : <ZapOff size={18} color="#8fc441" />}
                </button>
              </div>

              {/* Recording timer */}
              {isRecording && (
                <div style={{
                  position: 'absolute', top: 70, left: 0, right: 0, textAlign: 'center', zIndex: 25,
                }}>
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: 8,
                    background: 'rgba(0,0,0,0.5)', borderRadius: 20, padding: '6px 16px',
                    backdropFilter: 'blur(8px)',
                  }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.red, animation: 'ep-pulse 1s infinite' }} />
                    <span style={{ fontWeight: 700, fontSize: 16, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtTime(recTime)} / {fmtTime(MAX_REC)}
                    </span>
                  </div>
                  {/* Progress bar at top */}
                  <div style={{ position: 'absolute', top: -8, left: 0, right: 0, height: 3, background: 'rgba(255,255,255,0.2)' }}>
                    <div style={{ height: '100%', width: `${recProgress}%`, background: T.red, transition: 'width 0.5s linear' }} />
                  </div>
                </div>
              )}

              {/* Right side toolbar — icons + labels on the dark camera
                  preview.  Force white + drop shadow so they're readable
                  regardless of theme (user's dark-on-dark bug). */}
              <div style={{
                position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)',
                display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center',
                zIndex: 30,
              }}>
                {[
                  { icon: <RefreshCw size={22} color="#8fc441" />, label: 'Flip', action: () => {
                    const newMode = facingMode === 'user' ? 'environment' : 'user';
                    setFacingMode(newMode);
                    // Force camera restart with new facingMode
                    stopCamera();
                    setTimeout(() => startCamera(), 100);
                  } },
                  { icon: <Type size={22} color="#8fc441" />, label: 'Text', action: () => setShowTextInput(true) },
                  { icon: <Music size={22} color={backgroundSound ? '#8fc441' : '#8fc441'} />, label: 'Sound', action: () => setShowSoundSheet(true) },
                  { icon: <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#8fc441" strokeWidth={2}><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></svg>, label: 'Filter', action: () => setShowFilters(f => !f) },
                  { icon: <span style={{ fontSize: 13, fontWeight: 800, color: '#8fc441' }}>{selectedSpeed}</span>, label: 'Speed', action: () => setShowSpeeds(s => !s) },
                ].map((item, i) => (
                  <button key={i} className="ep-btn" onClick={item.action} onTouchEnd={(e) => { e.preventDefault(); item.action(); }}
                    style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, background: 'none', padding: 8, margin: -8 }}>
                    <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(255,255,255,0.15)' }}>
                      {item.icon}
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#8fc441', textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}>{item.label}</span>
                  </button>
                ))}
              </div>

              {/* Speed selector — force light text on dark popover */}
              {showSpeeds && (
                <div style={{
                  position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)',
                  display: 'flex', flexDirection: 'column', gap: 8,
                  background: 'rgba(0,0,0,0.7)', borderRadius: 16, padding: '10px 8px',
                  backdropFilter: 'blur(12px)', zIndex: 35,
                  border: '1px solid rgba(255,255,255,0.15)',
                }}>
                  {SPEEDS.map(sp => (
                    <button key={sp} className="ep-btn" onClick={() => { setSelectedSpeed(sp); setShowSpeeds(false); }}
                      style={{
                        padding: '6px 14px', borderRadius: 12,
                        background: selectedSpeed === sp ? T.pri : 'rgba(255,255,255,0.12)',
                        color: '#8fc441', fontSize: 13, fontWeight: 700,
                      }}>{sp}</button>
                  ))}
                </div>
              )}

              {/* Filter strip — labels above dark preview must be white. */}
              {showFilters && (
                <div style={{
                  position: 'absolute', bottom: 130, left: 0, right: 0, zIndex: 35,
                  overflowX: 'auto', display: 'flex', gap: 12, padding: '8px 16px',
                  scrollbarWidth: 'none',
                }}>
                  {FILTERS.map(f => (
                    <button key={f.id} className="ep-btn" onClick={() => setSelectedFilter(f.id)}
                      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', flexShrink: 0 }}>
                      <div style={{
                        width: 58, height: 58, borderRadius: 12,
                        background: `conic-gradient(${T.pri}, #3B82F6, #10B981, ${T.pri})`,
                        filter: f.css,
                        border: selectedFilter === f.id ? `3px solid ${T.pri}` : '3px solid rgba(255,255,255,0.4)',
                        boxShadow: selectedFilter === f.id ? `0 0 0 2px ${T.pri}` : 'none',
                        transition: 'all 0.2s',
                      }} />
                      <span style={{
                        fontSize: 11,
                        color: '#8fc441',
                        fontWeight: selectedFilter === f.id ? 800 : 600,
                        textShadow: '0 1px 3px rgba(0,0,0,0.9)',
                      }}>{f.name}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Bottom controls */}
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 30,
                background: 'linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%)',
                padding: '0 24px 48px',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
              }}>
                  {/* Upload from gallery shortcut */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                  <button className="ep-btn" 
                    onClick={() => fileInputRef.current?.click()}
                    onTouchEnd={(e) => { e.preventDefault(); fileInputRef.current?.click(); }}
                    style={{ background: 'rgba(0,0,0,0.45)', borderRadius: 12, padding: 6, backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.15)' }}>
                    <div style={{ width: 52, height: 52, borderRadius: 10, background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Upload size={22} color="#8fc441" />
                    </div>
                  </button>

                  {/* Record / Shutter button */}
                  <div style={{ position: 'relative', width: 80, height: 80 }}>
                    {camMode === 'video' && isRecording && (
                      <ProgressRing radius={40} stroke={4} progress={recProgress} color={T.red} />
                    )}
                    <button className="ep-btn"
                      onClick={camMode === 'video'
                        ? () => { isRecording ? stopRecording() : startRecording().catch(console.error); }
                        : takePhoto}
                      onTouchEnd={(e) => {
                        e.preventDefault();
                        if (camMode === 'video') {
                          isRecording ? stopRecording() : startRecording().catch(console.error);
                        } else {
                          takePhoto();
                        }
                      }}
                      style={{
                        width: 80, height: 80, borderRadius: '50%',
                        background: camMode === 'video' ? (isRecording ? '#EF4444' : '#FFFFFF') : '#FFFFFF',
                        border: `4px solid rgba(255,255,255,0.5)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: isRecording ? `0 0 0 6px #EF444455` : 'rgba(0,0,0,0.4)',
                        transition: 'all 0.2s',
                      }}>
                      {camMode === 'video'
                        ? (isRecording
                          ? <Square size={26} color={T.txt} fill={T.txt} />
                          : <div style={{ width: 20, height: 20, borderRadius: '50%', background: '#EF4444' }} />)
                        : <div style={{ width: 56, height: 56, borderRadius: '50%', background: T.cardBg || '#fff', border: `3px solid ${T.border}` }} />
                      }
                    </button>
                    {/* Video icon indicator - only show in video mode */}
                    {camMode === 'video' && (
                      <div style={{
                        position: 'absolute',
                        top: -8,
                        right: -8,
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        background: 'rgba(0,0,0,0.75)',
                        backdropFilter: 'blur(8px)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: '2px solid rgba(255,255,255,0.35)',
                      }}>
                        <Video size={14} color="#8fc441" strokeWidth={2.5} />
                      </div>
                    )}
                  </div>

                  {/* Flip camera shortcut */}
                  <button className="ep-btn" 
                    onClick={() => {
                      const newMode = facingMode === 'user' ? 'environment' : 'user';
                      setFacingMode(newMode);
                      // Force camera restart with new facingMode
                      stopCamera();
                      setTimeout(() => startCamera(), 100);
                    }}
                    onTouchEnd={(e) => { 
                      e.preventDefault(); 
                      const newMode = facingMode === 'user' ? 'environment' : 'user';
                      setFacingMode(newMode);
                      // Force camera restart with new facingMode
                      stopCamera();
                      setTimeout(() => startCamera(), 100);
                    }}
                    style={{ background: 'rgba(0,0,0,0.45)', borderRadius: '50%', width: 52, height: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.15)' }}>
                    <RefreshCw size={22} color="#8fc441" />
                  </button>
                </div>

                {/* Background sound pill */}
                {backgroundSound && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    background: `${T.dark}8C`, borderRadius: 24, padding: '8px 14px',
                    backdropFilter: 'blur(10px)',
                  }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: T.pri, animation: isRecording ? 'ep-pulse 1s infinite' : 'none' }} />
                    <Music size={14} color={T.pri} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{backgroundSound.name}</span>
                    <button className="ep-btn" onClick={() => setBackgroundSound(null)}
                      style={{ background: `${T.pri}20`, borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <X size={11} color={T.txt} />
                    </button>
                  </div>
                )}
              </div>

              {/* Hidden input */}
              <input ref={fileInputRef} type="file" accept="image/*,video/*"
                onChange={handleFileSelect} style={{ display: 'none' }} />
            </div>

          ) : (
            /* ── UPLOAD / PICK MODE ── */
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              height: '100%',
              overflowY: 'auto',
              paddingBottom: 24,
              background: 'linear-gradient(160deg, #0D0A06 0%, #0D0D0D 60%, #0A0806 100%)',
            }}>

              {/* Header */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: 'max(16px, env(safe-area-inset-top)) 16px 12px',
                background: 'transparent',
                position: 'relative', zIndex: 1,
              }}>
                <button className="ep-btn" onClick={onBack}
                  style={{ background: 'rgba(249,224,139,0.15)', border: '1.5px solid #8fc441', borderRadius: 10, width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowLeft size={20} color="#8fc441" />
                </button>
                <span style={{ fontSize: 18, fontWeight: 800, background: 'linear-gradient(to bottom, #8fc441 0%, #D4AF37 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>New Post</span>
                {drafts.length > 0 ? (
                  <button className="ep-btn" onClick={() => setShowDrafts(true)}
                    style={{ background: 'rgba(249,224,139,0.12)', border: '1.5px solid #8fc441', borderRadius: 20, padding: '7px 13px', color: '#8fc441', fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileText size={14} /> Drafts ({drafts.length})
                  </button>
                ) : <div style={{ width: 40 }} />}
              </div>

              {/* Hero icon + title */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 20, paddingBottom: 4, position: 'relative', zIndex: 1 }}>
                <div style={{ position: 'relative', marginBottom: 14 }}>
                  <img
                    src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23D99B2A'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z'/%3E%3C/svg%3E"
                    alt="Create"
                    style={{
                      width: 72,
                      height: 72,
                      borderRadius: '50%',
                      objectFit: 'cover'
                    }} 
                  />
                  <div style={{ position: 'absolute', top: -2, right: -2, width: 22, height: 22, background: '#8fc441', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, border: '2px solid #0D0D0D', boxShadow: '0 2px 6px rgba(249,224,139,0.5)' }}>✨</div>
                </div>
                <div style={{ fontSize: 22, fontWeight: 800, background: 'linear-gradient(to bottom, #8fc441 0%, #D4AF37 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: 4 }}>Create Post</div>
                <div style={{ fontSize: 13, color: '#8fc441', opacity: 0.7, textAlign: 'center' }}>Choose how you want to create content</div>
              </div>

              {/* Cards */}
              <div style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: 14, 
                padding: '16px 20px 24px', 
                position: 'relative', 
                zIndex: 1, 
                alignItems: 'center', 
                justifyContent: 'center', 
                width: '100%',
                maxWidth: '500px',
                margin: '0 auto'
              }}>

                {/* ── Take Photo card ── */}
                <button className="ep-btn" onClick={() => { setCamMode('photo'); setCaptureMode('camera'); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 16,
                    background: '#1a1a1a',
                    border: '1.5px solid #8fc441',
                    borderRadius: 16,
                    padding: '18px 20px',
                    cursor: 'pointer',
                    boxShadow: 'none',
                    transition: 'transform 0.15s',
                    textAlign: 'left',
                    position: 'relative',
                    overflow: 'hidden',
                    width: '100%',
                    height: '88px',
                    minWidth: '280px',
                    maxWidth: '400px',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
                >
                  <div style={{ width: 52, height: 52, borderRadius: 12, background: '#111', border: '1px solid #8fc44144', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <svg width="24" height="24" fill="none" viewBox="0 0 24 24"><path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7z" fill="#8fc441"/><path d="M9 3L7.17 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3.17L15 3H9z" stroke="#8fc441" strokeWidth="1.8" fill="none" strokeLinejoin="round"/></svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#8fc441', marginBottom: 3 }}>Take Photo</div>
                    <div style={{ fontSize: 12.5, color: '#8fc441', opacity: 0.6 }}>Use camera for photos</div>
                  </div>
                </button>

                {/* ── Record Video card ── */}
                <button className="ep-btn" onClick={() => { setCamMode('video'); setCaptureMode('camera'); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 16,
                    background: '#1a1a1a',
                    border: '1.5px solid #8fc441',
                    borderRadius: 16,
                    padding: '18px 20px',
                    cursor: 'pointer',
                    boxShadow: 'none',
                    transition: 'transform 0.15s',
                    textAlign: 'left',
                    position: 'relative',
                    overflow: 'hidden',
                    width: '100%',
                    height: '88px',
                    minWidth: '280px',
                    maxWidth: '400px',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
                >
                  <div style={{ width: 52, height: 52, borderRadius: 12, background: '#111', border: '1px solid #8fc44144', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <svg width="24" height="24" fill="none" viewBox="0 0 24 24"><rect x="2" y="6" width="14" height="12" rx="2" stroke="#8fc441" strokeWidth="1.8" fill="none"/><path d="M22 8l-6 4 6 4V8z" fill="#8fc441"/></svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#8fc441', marginBottom: 3 }}>Record Video</div>
                    <div style={{ fontSize: 12.5, color: '#8fc441', opacity: 0.6 }}>Record up to 60 seconds</div>
                  </div>
                </button>

                {/* ── Upload Photo/Video card ── */}
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 16,
                  background: '#1a1a1a',
                  border: '1.5px solid #8fc441',
                  borderRadius: 16,
                  padding: '18px 20px',
                  cursor: 'pointer',
                  boxShadow: 'none',
                  transition: 'transform 0.15s',
                  textAlign: 'left',
                  position: 'relative',
                  overflow: 'hidden',
                  width: '100%',
                  height: '88px',
                  minWidth: '280px',
                  maxWidth: '400px',
                }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; }}
                >
                  <div style={{ width: 52, height: 52, borderRadius: 12, background: '#111', border: '1px solid #8fc44144', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <svg width="24" height="24" fill="none" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="#8fc441" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><polyline points="17 8 12 3 7 8" stroke="#8fc441" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><line x1="12" y1="3" x2="12" y2="15" stroke="#8fc441" strokeWidth="2.2" strokeLinecap="round"/></svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#8fc441', marginBottom: 3 }}>Upload Photo/Video</div>
                    <div style={{ fontSize: 12.5, color: '#8fc441', opacity: 0.6 }}>From gallery or files</div>
                  </div>
                  <div style={{ color: '#8fc441', fontSize: 22, fontWeight: 300, marginRight: 4 }}>+</div>
                  <input ref={fileInputRef} type="file" accept="image/*,video/*"
                    onChange={handleFileSelect} style={{ display: 'none' }} />
                </label>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── DETAILS STAGE ──────────────────────────────────────────────────── */}
      {stage === 'details' && (
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {/* Top bar */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: 'max(16px, env(safe-area-inset-top)) 16px 12px',
            borderBottom: `1px solid ${T.border}`,
            position: 'sticky', top: 0, background: T.bg, zIndex: 10,
          }}>
            <button className="ep-btn" onClick={() => { setStage('capture'); setPreview(null); setSelectedFile(null); }}
              style={{ background: 'rgba(255,255,255,0.12)', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ArrowLeft size={20} color={T.txt} />
            </button>
            <span style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>Post</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="ep-btn" onClick={() => setShowPreview(true)}
                style={{ background: 'rgba(218,155,42,0.2)', borderRadius: 20, padding: '8px 14px', color: T.txt, fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Eye size={15} /> Preview
              </button>
              <button className="ep-btn" onClick={saveDraft}
                style={{ background: 'rgba(218,155,42,0.2)', borderRadius: 20, padding: '8px', color: T.txt, display: 'flex', alignItems: 'center' }}>
                <Bookmark size={17} />
              </button>
              <button className="ep-btn" onClick={handlePost} disabled={isUploading}
                style={{
                  background: isUploading ? 'rgba(218,155,42,0.4)' : T.pri,
                  borderRadius: 24, padding: '10px 22px',
                  fontSize: 15, fontWeight: 800, color: '#fff',
                  opacity: isUploading ? 0.7 : 1,
                }}>
                {isUploading ? 'Posting...' : 'Post'}
              </button>
            </div>
          </div>

          {/* Upload progress bar */}
          {isUploading && (
            <div style={{ height: 3, background: T.border }}>
              <div style={{ height: '100%', width: `${uploadProgress}%`, background: T.pri, transition: 'width 0.3s' }} />
            </div>
          )}

          <div style={{ padding: '20px 20px 40px', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Preview + caption row */}
            <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
              {/* Media preview */}
              <div style={{
                width: 100, height: 138, borderRadius: 14, overflow: 'hidden',
                background: '#000', flexShrink: 0, position: 'relative',
                border: '1px solid rgba(255,255,255,0.2)',
              }}>
                {preview && (
                  isVideoFile
                    ? <video src={preview} style={{ width: '100%', height: '100%', objectFit: 'cover' }} muted playsInline />
                    : <img src={preview} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                )}
                {/* Text overlays on preview thumbnail */}
                {textOverlays.map(ov => (
                  <div key={ov.id} style={{
                    position: 'absolute',
                    left: `${ov.x}%`, top: `${ov.y}%`,
                    transform: 'translate(-50%,-50%)',
                    color: ov.color, fontSize: ov.fontSize * 0.42,
                    fontWeight: 800, whiteSpace: 'nowrap', pointerEvents: 'none',
                    textShadow: '0 1px 4px rgba(0,0,0,0.7)',
                    background: 'rgba(0,0,0,0.28)', borderRadius: 4, padding: '1px 4px',
                  }}>{ov.text}</div>
                ))}
                {/* Filter label */}
                {selectedFilter !== 'none' && (
                  <div style={{
                    position: 'absolute', inset: 0,
                    background: 'rgba(218,155,42,0.12)',
                    display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                    padding: 6,
                  }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: '#8fc441', background: 'rgba(0,0,0,0.5)', padding: '2px 6px', borderRadius: 8 }}>
                      {activeFilter?.name}
                    </span>
                  </div>
                )}
              </div>

              {/* Caption */}
              <div style={{ flex: 1 }}>
                <textarea
                  value={caption}
                  onChange={e => setCaption(e.target.value)}
                  placeholder="Describe your video..."
                  rows={5}
                  style={{
                    width: '100%', background: 'transparent', border: 'none', outline: 'none',
                    color: '#8fc441', fontSize: 15, lineHeight: 1.5, resize: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* Hashtags */}
            <div style={{
              background: '#000', borderRadius: 16, padding: '14px 16px',
              display: 'flex', alignItems: 'center', gap: 10,
              border: '1px solid rgba(255,255,255,0.2)',
            }}>
              <span style={{ color: T.pri, fontSize: 18, fontWeight: 800 }}>#</span>
              <input
                value={hashtags}
                onChange={e => setHashtags(e.target.value)}
                placeholder="Add hashtags..."
                style={{
                  flex: 1, background: 'transparent', border: 'none', outline: 'none',
                  color: '#8fc441', fontSize: 14,
                }}
              />
            </div>

            {/* Sound section */}
            <div style={{ background: '#000', borderRadius: 16, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.2)' }}>
              <button className="ep-btn" onClick={() => setShowSoundSheet(true)}
                style={{
                  width: '100%', padding: '16px 20px', background: 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'rgba(218,155,42,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Music size={18} color={T.pri} />
                  </div>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#8fc441' }}>
                      {backgroundSound ? backgroundSound.name : 'Add Sound'}
                    </div>
                    <div style={{ fontSize: 12, color: '#8fc441' }}>
                      {backgroundSound ? backgroundSound.artist : 'Pick background music'}
                    </div>
                  </div>
                </div>
                <span style={{ color: T.sub, fontSize: 20 }}>›</span>
              </button>

              {backgroundSound && (
                <div style={{ borderTop: `1px solid ${T.border}`, padding: '12px 20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <button className="ep-btn" onClick={toggleSoundPlay}
                      style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(218,155,42,0.15)', borderRadius: 24, padding: '6px 14px' }}>
                      {isPlayingSound ? <Pause size={14} color={T.pri} /> : <Play size={14} color={T.pri} />}
                      <span style={{ fontSize: 13, fontWeight: 600, color: T.pri }}>Preview</span>
                    </button>
                    <button className="ep-btn" onClick={() => setShowVolMixer(v => !v)}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.07)', borderRadius: 24, padding: '6px 14px' }}>
                      <Sliders size={14} color={'#8fc441'} />
                      <span style={{ fontSize: 13, fontWeight: 600, color: '#8fc441' }}>Mix</span>
                    </button>
                  </div>

                  {showVolMixer && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, animation: 'ep-fade-in 0.2s ease' }}>
                      {[
                        { label: 'Original sound', val: origVol, set: setOrigVol },
                        { label: 'Added sound', val: addedVol, set: setAddedVol },
                      ].map(({ label, val, set }) => (
                        <div key={label}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                            <span style={{ fontSize: 13, color: '#8fc441' }}>{label}</span>
                            <span style={{ fontSize: 13, fontWeight: 700, color: '#8fc441' }}>{val}%</span>
                          </div>
                          <input type="range" min={0} max={100} value={val}
                            onChange={e => set(+e.target.value)}
                            style={{ width: '100%', accentColor: T.pri }} />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Text overlays summary */}
            {textOverlays.length > 0 && (
              <div style={{ background: '#000', borderRadius: 16, padding: '16px 20px', border: '1px solid rgba(255,255,255,0.2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: '#8fc441' }}>Text overlays</span>
                  <button className="ep-btn" onClick={() => setShowTextInput(true)}
                    style={{ background: 'rgba(255,255,255,0.07)', borderRadius: 20, padding: '4px 12px', fontSize: 13, color: '#8fc441' }}>
                    + Add
                  </button>
                </div>
                {textOverlays.map(ov => (
                  <div key={ov.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 14, color: ov.color, fontWeight: 700 }}>{ov.text}</span>
                    <button className="ep-btn" onClick={() => removeOverlay(ov.id)}
                      style={{ background: 'rgba(255,59,87,0.15)', borderRadius: '50%', width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <X size={13} color={T.red} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add text CTA if none yet */}
            {textOverlays.length === 0 && (
              <button className="ep-btn" onClick={() => setShowTextInput(true)}
                style={{
                  padding: '16px', background: '#000', border: '1px dashed rgba(255,255,255,0.2)',
                  borderRadius: 16, display: 'flex', alignItems: 'center', gap: 12,
                  cursor: 'pointer',
                }}>
                <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Type size={18} color={'#8fc441'} />
                </div>
                <span style={{ fontSize: 14, fontWeight: 700, color: '#8fc441' }}>Add text overlay</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── TEXT INPUT MODAL — Professional TikTok-style ─────────────────────── */}
      {showTextInput && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.95)', zIndex: 9000,
          display: 'flex', flexDirection: 'column',
          animation: 'ep-fade-in 0.2s ease',
        }} onClick={() => setShowTextInput(false)}>
          
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: 'max(16px, env(safe-area-inset-top)) 20px 16px',
          }}>
            <button className="ep-btn" onClick={() => setShowTextInput(false)}
              style={{ background: 'rgba(255,255,255,0.1)', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <X size={20} color={'#8fc441'} />
            </button>
            <span style={{ fontSize: 17, fontWeight: 700, color: '#8fc441' }}>Add Text</span>
            <button className="ep-btn" onClick={addTextOverlay}
              style={{ background: T.pri, borderRadius: 20, padding: '10px 20px', fontSize: 14, fontWeight: 700, color: '#000' }}>
              Done
            </button>
          </div>

          {/* Live Preview Area */}
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }} onClick={e => e.stopPropagation()}>
            <div style={{
              minHeight: 120, minWidth: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(255,255,255,0.05)', borderRadius: 16, padding: 24,
            }}>
              {currentText ? (
                <span style={{ ...overlayCSS({ color: textColor, style: textStyle, align: textAlign, fontSize: textFontSize, fontWeight: 800 }), cursor: 'default' }}>
                  {currentText}
                </span>
              ) : <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 16 }}>Your text preview</span>}
            </div>
          </div>

          {/* Bottom Controls */}
          <div style={{
            background: 'rgba(20,20,20,0.98)', borderRadius: '24px 24px 0 0',
            padding: '20px 20px max(20px, env(safe-area-inset-bottom))',
          }} onClick={e => e.stopPropagation()}>
            
            {/* Text Input */}
            <textarea
              autoFocus
              value={currentText}
              onChange={e => setCurrentText(e.target.value)}
              placeholder="Type something..."
              rows={2}
              style={{
                width: '100%', background: 'rgba(255,255,255,0.08)', border: 'none',
                borderRadius: 14, padding: '14px 16px', color: '#8fc441',
                fontSize: 16, fontWeight: 600, outline: 'none', resize: 'none', boxSizing: 'border-box',
              }}
            />

            {/* Style Buttons */}
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'center' }}>
              {[['bold','Aa'],['plain','A'],['outline','Ø'],['neon','✦'],['highlight','▮']].map(([s,lbl]) => (
                <button key={s} className="ep-btn" onClick={() => setTextStyle(s)}
                  style={{
                    width: 48, height: 48, borderRadius: '50%', fontSize: 16, fontWeight: 800,
                    background: textStyle === s ? T.pri : 'rgba(255,255,255,0.1)',
                    color: textStyle === s ? '#000' : '#8fc441',
                    border: 'none',
                    boxShadow: textStyle === s ? '0 4px 12px rgba(218,155,42,0.4)' : 'none',
                  }}>
                  {lbl}
                </button>
              ))}
            </div>

            {/* Alignment + Size */}
            <div style={{ display: 'flex', gap: 10, marginTop: 14, alignItems: 'center', justifyContent: 'center' }}>
              {[['left','◀'],['center','≡'],['right','▶']].map(([a,lbl]) => (
                <button key={a} className="ep-btn" onClick={() => setTextAlign(a)}
                  style={{
                    width: 40, height: 40, borderRadius: '50%', fontSize: 14,
                    background: textAlign === a ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.08)',
                    color: '#8fc441', border: 'none',
                  }}>
                  {lbl}
                </button>
              ))}
              <div style={{ width: 1, height: 24, background: 'rgba(255,255,255,0.15)', margin: '0 8px' }} />
              <span style={{ color: T.sub, fontSize: 12 }}>Size</span>
              <input type="range" min={14} max={56} value={textFontSize}
                onChange={e => setTextFontSize(Number(e.target.value))}
                style={{ width: 100, accentColor: T.pri }} />
              <span style={{ color: '#8fc441', fontSize: 12, fontWeight: 600, minWidth: 24 }}>{textFontSize}</span>
            </div>

            {/* Color Palette - Perfect Circles */}
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: T.sub, marginBottom: 10, textAlign: 'center' }}>Color</div>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                {TEXT_COLORS.map(c => (
                  <button key={c} className="ep-btn" onClick={() => setTextColor(c)}
                    style={{
                      width: 36, height: 36, borderRadius: '50%', background: c,
                      border: textColor === c ? '3px solid #fff' : '2px solid rgba(255,255,255,0.2)',
                      boxShadow: textColor === c ? `0 0 0 3px ${T.pri}, 0 4px 12px rgba(0,0,0,0.4)` : '0 2px 8px rgba(0,0,0,0.3)',
                      transform: textColor === c ? 'scale(1.15)' : 'scale(1)',
                      transition: 'all 0.15s ease',
                    }} />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── SOUND SELECTOR SHEET ─────────────────────────────────────────────── */}
      {showSoundSheet && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 9000,
          display: 'flex', alignItems: 'flex-end', animation: 'ep-fade-in 0.2s ease',
        }} onClick={() => setShowSoundSheet(false)}>
          <div style={{
            width: '100%', maxHeight: '70vh', background: '#111',
            borderRadius: '24px 24px 0 0', overflow: 'hidden', display: 'flex', flexDirection: 'column',
            animation: 'ep-fade-in 0.25s ease',
          }} onClick={e => e.stopPropagation()}>
            {/* Sheet handle */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px 0 4px' }}>
              <div style={{ width: 40, height: 4, borderRadius: 4, background: T.border }} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 16px' }}>
              <span style={{ fontSize: 18, fontWeight: 800, color: '#8fc441' }}>Select Sound</span>
              <button className="ep-btn" onClick={() => setShowSoundSheet(false)}
                style={{ background: 'rgba(255,255,255,0.1)', borderRadius: '50%', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={18} color={'#8fc441'} />
              </button>
            </div>

            <div style={{ overflowY: 'auto', padding: '0 20px 32px', flex: 1 }}>
              {/* Upload custom */}
              <label style={{
                display: 'flex', alignItems: 'center', gap: 14, padding: '14px 0',
                borderBottom: `1px solid ${T.border}`, cursor: 'pointer',
              }}>
                <div style={{ width: 48, height: 48, borderRadius: 12, background: 'rgba(218,155,42,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Upload size={20} color={T.pri} />
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#8fc441' }}>Upload your own</div>
                  <div style={{ fontSize: 12, color: T.sub }}>MP3, AAC, WAV</div>
                </div>
                <input ref={audioFileInputRef} type="file" accept="audio/*"
                  onChange={handleCustomAudio} style={{ display: 'none' }} />
              </label>
            </div>
          </div>
        </div>
      )}

      {/* ── SUCCESS OVERLAY ──────────────────────────────────────────────────── */}
      {showSuccess && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 9999,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: 20, animation: 'ep-fade-in 0.3s ease',
        }}>
          <div style={{
            width: 96, height: 96, borderRadius: '50%',
            background: 'linear-gradient(135deg, #10B981, #059669)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            animation: 'ep-success 0.4s cubic-bezier(0.175,0.885,0.32,1.275)',
          }}>
            <Check size={48} color={T.white} strokeWidth={3} />
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: T.white }}>Video is Live! 🎉</div>
          <div style={{ fontSize: 15, color: T.sub }}>Your post has been uploaded</div>
        </div>
      )}

      {/* ── INSUFFICIENT COINS MODAL ──────────────────────────────────────────── */}
      {showInsufficientCoins && (
        <div 
          onClick={(e) => {
            // Prevent closing when clicking outside the modal content
            e.stopPropagation();
          }}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 9999,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            gap: 20, animation: 'ep-fade-in 0.3s ease',
          }}>
          <div style={{
            width: 96, height: 96, borderRadius: '50%',
            background: 'linear-gradient(135deg, #EF4444, #DC2626)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Coins size={48} color={T.white} strokeWidth={3} />
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: T.white }}>Insufficient Coins</div>
          <div style={{ fontSize: 15, color: T.sub, textAlign: 'center', maxWidth: 300, padding: '0 20px' }}>
            You need {postCost} coins to create a post. Purchase coins to continue.
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
            <button
              onClick={() => setShowInsufficientCoins(false)}
              style={{
                padding: '12px 24px', borderRadius: 24, fontSize: 14, fontWeight: 700,
                background: 'rgba(255,255,255,0.1)', color: T.white, border: 'none', cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={() => {
                console.log('[INSUFFICIENT_COINS] Purchase button clicked', { onShowCoinPurchase: !!onShowCoinPurchase });
                setShowInsufficientCoins(false);
                // Show coin purchase modal
                if (onShowCoinPurchase) {
                  onShowCoinPurchase();
                } else {
                  console.error('[INSUFFICIENT_COINS] onShowCoinPurchase not available');
                  // Fallback: navigate to profile
                  onNavProfile?.();
                }
              }}
              style={{
                padding: '12px 24px', borderRadius: 24, fontSize: 14, fontWeight: 700,
                background: T.pri, color: T.white, border: 'none', cursor: 'pointer',
              }}
            >
              Purchase Coins
            </button>
          </div>
        </div>
      )}

      {/* ── PREVIEW MODAL — exact TikTokLayout feed card UI ─────────────────── */}
      {showPreview && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9000, background: '#000' }}>
          {/* Full-screen card — same dimensions as TikTokLayout mobile card */}
          <div style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>

            {/* 1 ── Background media (contain to show full video without zoom) */}
            {preview && (isVideoFile
              ? <video ref={previewVideoRef} src={preview} autoPlay loop playsInline controls={false} muted={previewMuted}
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', background: '#000', display: 'block' }} />
              : <img src={preview} alt=""
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', background: '#000', display: 'block' }} />
            )}
            {!preview && (
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg,#1a1a1a,#2a2a2a)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 48 }}>🎬</span>
              </div>
            )}

            {/* 2 ── Text overlays */}
            {textOverlays.map(ov => (
              <div key={ov.id} style={{ position: 'absolute', left: `${ov.x}%`, top: `${ov.y}%`, transform: 'translate(-50%,-50%)', pointerEvents: 'none', zIndex: 5 }}>
                <span style={{ ...overlayCSS(ov), cursor: 'default' }}>{ov.text}</span>
              </div>
            ))}

            {/* 3 ── Bottom gradient + creator info (left side, same as feed) */}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 72,
              background: 'linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.5) 55%, transparent 100%)',
              padding: '80px 16px 28px', zIndex: 10, pointerEvents: 'none',
            }}>
              {/* Creator row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div style={{ width: 40, height: 40, borderRadius: '50%', background: T.pri, border: '2px solid rgba(255,255,255,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, overflow: 'hidden' }}>
                  {user?.profile_photo
                    ? <img src={user.profile_photo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : <span style={{ fontSize: 20 }}>👤</span>}
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>{user?.username || 'you'}</div>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.72)', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}>@{user?.username || 'you'}</div>
                </div>
                <div style={{ marginLeft: 'auto', background: T.pri, borderRadius: 20, color: '#fff', padding: '6px 16px', fontSize: 13, fontWeight: 700, border: '1.5px solid rgba(255,255,255,0.25)' }}>Follow</div>
              </div>
              {/* Caption */}
              <div style={{ fontSize: 14, color: '#fff', lineHeight: 1.5, textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>
                {caption || <span style={{ color: 'rgba(255,255,255,0.45)' }}>Your caption will appear here…</span>}
              </div>
              {/* Background sound */}
              {backgroundSound && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                  <Music size={13} color="rgba(255,255,255,0.85)" />
                  <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.85)', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}>{backgroundSound.name}</span>
                </div>
              )}
            </div>

            {/* 4 ── Right action sidebar — exact same layout as TikTokLayout */}
            <div style={{
              position: 'absolute', right: 12, bottom: 28,
              display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center',
              zIndex: 10,
            }}>
              {/* Like */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.38)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.9))' }}>
                  <Heart size={26} color="#fff" strokeWidth={2} />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>0</span>
              </div>
              {/* Comment */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.38)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.9))' }}>
                  <MessageCircle size={26} color="#fff" fill="#fff" />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>0</span>
              </div>
              {/* Share */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.38)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.9))' }}>
                  <Share2 size={26} color="#fff" />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>0</span>
              </div>
              {/* Save */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.38)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.9))' }}>
                  <Bookmark size={26} color="#fff" />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>Save</span>
              </div>
              {/* Volume - clickable */}
              <button 
                onClick={() => setPreviewMuted(!previewMuted)}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(0,0,0,0.38)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.9))' }}>
                  {previewMuted ? <VolumeX size={26} color="#fff" /> : <Volume2 size={26} color="#fff" />}
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>{previewMuted ? 'Off' : 'On'}</span>
              </button>
            </div>

            {/* 5 ── Close button (top-right) */}
            <button className="ep-btn" onClick={() => setShowPreview(false)} style={{
              position: 'absolute', top: 'max(16px, env(safe-area-inset-top))', right: 16, zIndex: 20,
              background: 'rgba(0,0,0,0.55)', borderRadius: '50%', width: 42, height: 42,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.12)',
            }}>
              <X size={20} color="#fff" />
            </button>

            {/* 6 ── Preview badge (top-left) */}
            <div style={{
              position: 'absolute', top: 'max(20px, calc(env(safe-area-inset-top) + 4px))', left: 16, zIndex: 20,
              background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(8px)',
              borderRadius: 20, padding: '6px 14px',
              fontSize: 12, color: T.pri, fontWeight: 800,
              border: '1px solid rgba(218,155,42,0.35)',
            }}>⚡ Preview</div>

          </div>
        </div>
      )}

      {/* ── DRAFTS SHEET ─────────────────────────────────────────────────────── */}
      {showDrafts && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 8500, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'flex-end' }}
          onClick={() => setShowDrafts(false)}>
          <div style={{ width: '100%', background: T.card, borderRadius: '24px 24px 0 0', padding: '20px 20px 40px', maxHeight: '80vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <span style={{ fontSize: 18, fontWeight: 800, color: T.white }}>Drafts ({drafts.length})</span>
              <button className="ep-btn" onClick={() => setShowDrafts(false)}
                style={{ background: 'rgba(255,255,255,0.1)', borderRadius: '50%', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <X size={18} color={T.white} />
              </button>
            </div>
            {drafts.length === 0 && <div style={{ textAlign: 'center', color: T.sub, padding: '32px 0' }}>No drafts saved yet</div>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {drafts.map(d => (
                <div key={d.id} style={{ display: 'flex', gap: 14, alignItems: 'center', background: 'rgba(255,255,255,0.05)', borderRadius: 14, padding: '12px 14px' }}>
                  {/* Thumb */}
                  <div style={{ width: 56, height: 76, borderRadius: 10, overflow: 'hidden', background: T.bg, flexShrink: 0, position: 'relative' }}>
                    {d.thumbData
                      ? <img src={d.thumbData} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>{d.isVideo ? '🎬' : '🖼️'}</div>
                    }
                  </div>
                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: T.white, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.caption || '(no caption)'}
                    </div>
                    <div style={{ fontSize: 12, color: T.sub, marginTop: 2 }}>
                      {d.isVideo ? 'Video' : 'Photo'} · {new Date(d.createdAt).toLocaleDateString()}
                    </div>
                    {d.textOverlays?.length > 0 && <div style={{ fontSize: 11, color: T.pri, marginTop: 2 }}>{d.textOverlays.length} text overlay{d.textOverlays.length > 1 ? 's' : ''}</div>}
                  </div>
                  {/* Actions */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <button className="ep-btn" onClick={() => loadDraft(d)}
                      style={{ background: T.pri, borderRadius: 10, padding: '6px 14px', fontSize: 13, fontWeight: 700, color: '#000' }}>
                      Resume
                    </button>
                    <button className="ep-btn" onClick={() => deleteDraft(d.id)}
                      style={{ background: 'rgba(239,68,68,0.2)', borderRadius: 10, padding: '6px 14px', fontSize: 13, fontWeight: 700, color: '#EF4444' }}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── TOAST ──────────────────────────────────────────────────────────── */}
      {successMsg && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 99999,
          background: 'rgba(30,30,30,0.95)', borderRadius: 24, padding: '10px 22px',
          color: T.white, fontSize: 14, fontWeight: 700, boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          backdropFilter: 'blur(12px)', animation: 'ep-fade-in 0.2s ease' }}>
          {successMsg}
        </div>
      )}

      {/* Hidden audio player */}
      <audio ref={audioRef} onEnded={() => setIsPlayingSound(false)} style={{ display: 'none' }} />
    </div>
  );
}




