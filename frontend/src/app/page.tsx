"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Tv, Sparkles, Settings, AlertCircle, FileText, CheckCircle2,
  Layers, Image as ImageIcon, RefreshCw, Subtitles,
  Trash2, Gauge, Download
} from "lucide-react";

interface StoryboardScene {
  scene: number;
  narration: string;
  image_url: string;
  audio_url: string;
  duration: number;
}

interface BackendConfig {
  voices: string[];
  leonardo_models: string[];
  aspect_ratios: string[];
  music_presets: string[];
  satisfying_presets: string[];
  viral_hooks: string[];
  ollama_models: string[];
  default_model?: string;
  art_styles?: string[];
  visual_modes?: string[];
  quality_presets?: string[];
  visual_source_modes?: string[];
  stock_available?: boolean;
  default_quality?: string;
  motion_styles?: string[];
  duration_presets?: string[];
  default_duration_preset?: string;
  delivery?: {
    fps: number;
    resolution: string;
    target_lufs: number;
  };
}

const COLOR_PRESETS = [
  { name: "Yellow", ass: "&H00FFFF&", hex: "#FFFF00" },
  { name: "Cyan", ass: "&HFFFF00&", hex: "#00FFFF" },
  { name: "Green", ass: "&H00FF00&", hex: "#00FF00" },
  { name: "Red", ass: "&H0000FF&", hex: "#FF0000" },
  { name: "Orange", ass: "&H00A5FF&", hex: "#FFA500" },
  { name: "Pink", ass: "&HFF00FF&", hex: "#FF00FF" },
  { name: "White", ass: "&HFFFFFF&", hex: "#FFFFFF" },
];


export default function Home() {
  const [activeTab, setActiveTab] = useState<"viral" | "library" | "queue">("viral");
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [statusText, setStatusText] = useState("");
  
  // Results
  const [finalVideoUrl, setFinalVideoUrl] = useState<string | null>(null);
  const [presenterImageUrl, setPresenterImageUrl] = useState<string | null>(null);
  const [voiceAudioUrl, setVoiceAudioUrl] = useState<string | null>(null);
  const [storyboard, setStoryboard] = useState<any[]>([]);
  const [generatedTopic, setGeneratedTopic] = useState("");
  const [generationId, setGenerationId] = useState<string | null>(null);

  // Drafting and rendering states
  const [drafting, setDrafting] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [regeneratingSceneIdx, setRegeneratingSceneIdx] = useState<number | null>(null);
  const [regeneratingAssetType, setRegeneratingAssetType] = useState<string | null>(null);

  // History & Queue states
  const [history, setHistory] = useState<any[]>([]);
  const [uploadQueue, setUploadQueue] = useState<any[]>([]);

  // Input states: Viral Shorts Studio
  const [viralPrompt, setViralPrompt] = useState("The giant hidden ocean underneath Jupiter's moon Europa");
  const [viralOllamaModel, setViralOllamaModel] = useState("");
  const [enableSearch, setEnableSearch] = useState(false);
  const [viralVoice, setViralVoice] = useState("Sarah (Female - US - Soft)");
  const [viralVoiceSpeed, setViralVoiceSpeed] = useState(1.0);
  const [visualMode, setVisualMode] = useState("Cinematic Slideshow");
  const [artStyle, setArtStyle] = useState("Photorealistic");
  const [viralLeonardoModel, setViralLeonardoModel] = useState("Lucid Realism (High Quality Face)");
  const [musicStyle, setMusicStyle] = useState("Cinematic");
  const [satisfyingBackground, setSatisfyingBackground] = useState("Slime ASMR");
  const [viralHookStyle, setViralHookStyle] = useState("Did You Know? (Fact Hook)");
  const [durationPreset, setDurationPreset] = useState("Standard (25-35s)");
  const [enableCaptions, setEnableCaptions] = useState(true);
  const [enableTransitionSfx, setEnableTransitionSfx] = useState(false);
  const [captionFont, setCaptionFont] = useState("Arial");
  const [captionSize, setCaptionSize] = useState(72);
  const [captionMarginV, setCaptionMarginV] = useState(150);
  const [captionColor, setCaptionColor] = useState("&H00FFFF&");
  const [captionStyle, setCaptionStyle] = useState("Viral Pop");

  // Delivery quality & retention settings
  const [quality, setQuality] = useState("High (recommended)");
  const [motionStyle, setMotionStyle] = useState("Dynamic");
  const [visualSourceMode, setVisualSourceMode] = useState("Smart Mix");
  const [progressBar, setProgressBar] = useState(true);
  const [normalizeAudio, setNormalizeAudio] = useState(true);
  const [duckMusic, setDuckMusic] = useState(true);
  const [enableThumbnail, setEnableThumbnail] = useState(true);
  const [subscribeOverlay, setSubscribeOverlay] = useState(true);
  const [channelHandle, setChannelHandle] = useState("");
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);

  // Social Media Upload States
  const [isYtAuthenticated, setIsYtAuthenticated] = useState(false);
  const [imageProviderStatus, setImageProviderStatus] = useState<any>(null);
  const [sdModels, setSdModels] = useState<any[]>([]);
  const [sdCurrentModel, setSdCurrentModel] = useState<string>("");
  const [switchingModel, setSwitchingModel] = useState(false);
  const [imageProvider, setImageProvider] = useState("");
  const [isCheckingReadiness, setIsCheckingReadiness] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadPrivacy, setUploadPrivacy] = useState("private");
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  // YouTube specific upload states
  const [ytIsUploading, setYtIsUploading] = useState(false);
  const [ytUploadJobId, setYtUploadJobId] = useState<string | null>(null);
  const [ytUploadLogs, setYtUploadLogs] = useState<string[]>([]);

  const consoleEndRef = useRef<HTMLDivElement>(null);

  const refreshReadiness = async () => {
    setIsCheckingReadiness(true);
    try {
      // Fetch YouTube authentication status
      const ytAuthRes = await fetch("http://localhost:8000/api/youtube/auth-status");
      if (ytAuthRes.ok) {
        const ytAuthData = await ytAuthRes.json();
        setIsYtAuthenticated(ytAuthData.authenticated);
      }
      
      // Fetch active image provider + local SD server status
      const imgRes = await fetch("http://localhost:8000/api/image-provider/status");
      if (imgRes.ok) {
        const data = await imgRes.json();
        setImageProviderStatus(data);
        setImageProvider((prev) => prev || data.provider || "pollinations");
      }
    } catch (err) {
      console.error("Failed to fetch platform readiness status:", err);
    } finally {
      setIsCheckingReadiness(false);
    }
  };

  // Fetch config on load
  const loadConfig = async () => {
    try {
      setBackendError(null);
      const res = await fetch("http://localhost:8000/api/config");
      if (!res.ok) throw new Error("Backend response error");
      const data: BackendConfig = await res.json();
      setConfig(data);
      const defaultModel = data.default_model || data.ollama_models[0];
      if (defaultModel) {
        setViralOllamaModel(defaultModel);
      }

      await refreshReadiness();
    } catch (err) {
      setBackendError("Could not connect to FastAPI backend on http://localhost:8000. Please start the backend server by running `.venv/bin/python backend.py`.");
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const handleChangeImageProvider = async (provider: string) => {
    setImageProvider(provider);
    try {
      const res = await fetch(`http://localhost:8000/api/image-provider/status?provider=${provider}`);
      if (res.ok) setImageProviderStatus(await res.json());
    } catch (err) {
      console.error("Failed to check image provider status:", err);
    }
    // The model choice is the single biggest lever on how realistic the images
    // look, so load the catalog as soon as the local engine is selected.
    if (provider === "local") {
      try {
        const res = await fetch("http://localhost:8000/api/image-provider/models");
        if (res.ok) {
          const data = await res.json();
          setSdModels(data.catalog || []);
          setSdCurrentModel(data.current || "");
        }
      } catch (err) {
        console.error("Failed to load local model catalog:", err);
      }
    }
  };

  const handleSelectSdModel = async (model: string) => {
    setSwitchingModel(true);
    addLog(`Switching local image model to ${model}...`);
    try {
      const res = await fetch("http://localhost:8000/api/image-provider/models/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model })
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setSdCurrentModel(data.model);
      addLog(`Image model set to ${data.model} (${data.steps} steps, guidance ${data.guidance}).`);
      if (data.download_gb) {
        addLog(`First render with this model downloads ~${data.download_gb}GB.`);
      }
      handleChangeImageProvider("local");
    } catch (err: any) {
      addLog(`❌ Could not switch model: ${err.message || err}`);
    } finally {
      setSwitchingModel(false);
    }
  };

  const handleUpdateSceneNarration = (idx: number, val: string) => {
    setStoryboard((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], narration: val };
      return copy;
    });
  };

  const handleUpdateScenePrompt = (idx: number, val: string) => {
    setStoryboard((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], visual_prompt: val };
      return copy;
    });
  };

  const handleUpdateSceneSpeaker = (idx: number, val: string) => {
    setStoryboard((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], speaker: val };
      return copy;
    });
  };


  const handleDraftStoryboard = async () => {
    setDrafting(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setThumbnailUrl(null);
    setStoryboard([]);
    setGenerationId(null);

    addLog("📝 Creating Script & Storyboard Draft...");
    addLog(`Topic: "${viralPrompt}"`);
    addLog(`Hook Style: ${viralHookStyle}`);
    addLog(`Duration: ${durationPreset}`);

    // Drafting runs as a background job on the backend (a multi-minute local
    // LLM call previously held this fetch open with no way to show progress
    // or give up cleanly -- reproduced live as a 280s hang with no response).
    // Poll generation-status instead of awaiting one long request.
    let seenLogCount = 0;
    try {
      const response = await fetch("http://localhost:8000/api/draft-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: viralPrompt,
          model: viralOllamaModel || "qwen2.5:7b-instruct",
          hook_style: viralHookStyle,
          enable_search: enableSearch,
          voice: viralVoice,
          art_style: artStyle,
          duration_preset: durationPreset
        })
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const { generation_id } = await response.json();
      setGenerationId(generation_id);

      await new Promise<void>((resolve, reject) => {
        const interval = setInterval(async () => {
          try {
            const res = await fetch(`http://localhost:8000/api/generation-status/${generation_id}`);
            if (!res.ok) return;
            const status = await res.json();

            const newLogs: string[] = (status.logs || []).slice(seenLogCount);
            newLogs.forEach((line: string) => addLog(line));
            seenLogCount = (status.logs || []).length;

            if (status.status === "draft") {
              clearInterval(interval);
              clearTimeout(timeout);
              setStoryboard(status.storyboard || []);
              setGeneratedTopic(status.topic || "");
              setUploadTitle(status.youtube_metadata?.title || status.topic || "");
              setUploadDescription(status.youtube_metadata?.description || "");
              setUploadTags(status.youtube_metadata?.tags?.join(", ") || "");
              if (status.validation_warnings?.length) {
                addLog(`⚠️ Draft used the least-bad attempt: ${status.validation_warnings.join("; ")}`);
              }
              addLog("✅ Script draft generated! Storyboard scenes are now ready for your edits.");
              resolve();
            } else if (status.status === "failed") {
              clearInterval(interval);
              clearTimeout(timeout);
              reject(new Error(status.error_message || "Draft generation failed"));
            }
          } catch (pollErr) {
            console.error("Error polling draft status:", pollErr);
          }
        }, 2000);

        // Local 7B models can legitimately take several minutes across
        // retries; give up client-side well past that rather than polling
        // forever if the backend itself never reaches a terminal status.
        const timeout = setTimeout(() => {
          clearInterval(interval);
          reject(new Error("Drafting timed out after 8 minutes with no result."));
        }, 8 * 60 * 1000);
      });
    } catch (err: any) {
      addLog(`❌ ERROR drafting script: ${err.message || err}`);
    } finally {
      setDrafting(false);
    }
  };

  const handleRenderStoryboard = async () => {
    if (!generationId) return;
    setRendering(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setThumbnailUrl(null);
    
    addLog("🚀 Compiling & Rendering Final Video...");
    addLog(`Visual Mode: ${visualMode}`);
    addLog(`Music Style: ${musicStyle}`);
    addLog(`Satisfying BG: ${satisfyingBackground}`);
    addLog(`Caption Style: ${captionStyle}`);
    
    try {
      const response = await fetch("http://localhost:8000/api/render-storyboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          generation_id: generationId,
          storyboard: storyboard,
          visual_mode: visualMode,
          image_provider: imageProvider,
          leonardo_model: viralLeonardoModel,
          voice: viralVoice,
          speed: viralVoiceSpeed,
          music_style: musicStyle,
          satisfying_background: satisfyingBackground,
          enable_captions: enableCaptions,
          enable_transition_sfx: enableTransitionSfx,
          caption_font: captionFont,
          caption_size: captionSize,
          caption_margin_v: captionMarginV,
          caption_color: captionColor,
          caption_style: captionStyle,
          quality: quality,
          motion_style: motionStyle,
          visual_source_mode: visualSourceMode,
          progress_bar: progressBar,
          normalize_audio: normalizeAudio,
          duck_music: duckMusic,
          enable_thumbnail: enableThumbnail,
          subscribe_overlay: subscribeOverlay,
          channel_handle: channelHandle
        })
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      addLog("⏳ Video rendering task queued in the background. Polling render status...");
      setStatusText("Rendering...");
      
      // Poll rendering status
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch(`http://localhost:8000/api/generation-status/${generationId}`);
          if (statusRes.ok) {
            const data = await statusRes.json();
            if (data.status === "completed") {
              setFinalVideoUrl(data.video_url);
              setThumbnailUrl(data.thumbnail_url || null);
              setStoryboard(data.storyboard);
              setStatusText("Finished!");
              addLog("🎉 Success! Render complete.");
              clearInterval(interval);
              setRendering(false);
              loadHistory(); // refresh library
            } else if (data.status === "failed") {
              setStatusText("Failed");
              addLog("❌ Video rendering failed on the server.");
              clearInterval(interval);
              setRendering(false);
            } else {
              addLog("Rendering still in progress...");
            }
          }
        } catch (err) {
          console.error("Error polling render status:", err);
        }
      }, 3000);
      
      // Auto-clear after 10 minutes
      setTimeout(() => {
        clearInterval(interval);
        setRendering(false);
      }, 600000);
      
    } catch (err: any) {
      addLog(`❌ ERROR starting render: ${err.message || err}`);
      setRendering(false);
    }
  };

  const handleRegenerateAsset = async (sceneIndex: number, assetType: string) => {
    if (!generationId) return;
    setRegeneratingSceneIdx(sceneIndex);
    setRegeneratingAssetType(assetType);
    addLog(`🔄 Regenerating ${assetType} for Scene ${sceneIndex + 1}...`);
    
    try {
      const scene = storyboard[sceneIndex];
      const payload = {
        generation_id: generationId,
        scene_index: sceneIndex,
        asset_type: assetType,
        prompt: assetType === "image" ? scene.visual_prompt : scene.narration,
        voice: scene.speaker || viralVoice,
        speed: viralVoiceSpeed,
        leonardo_model: viralLeonardoModel
      };
      
      const response = await fetch("http://localhost:8000/api/regenerate-scene-asset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      const updatedStoryboard = [...storyboard];
      updatedStoryboard[sceneIndex] = result.scene;
      setStoryboard(updatedStoryboard);
      addLog(`✅ Scene ${sceneIndex + 1} ${assetType} regenerated successfully.`);
    } catch (err: any) {
      addLog(`❌ ERROR regenerating ${assetType}: ${err.message || err}`);
    } finally {
      setRegeneratingSceneIdx(null);
      setRegeneratingAssetType(null);
    }
  };

  const loadHistory = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/history");
      if (res.ok) {
        setHistory(await res.json());
      }
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  const handleDeleteGeneration = async (genId: string, topic: string) => {
    if (!window.confirm(`Are you sure you want to permanently delete the video "${topic || "Untitled"}" and all its associated assets (images and audio files)? This action cannot be undone.`)) {
      return;
    }
    
    try {
      const res = await fetch(`http://localhost:8000/api/generation/${genId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        addLog(`🗑️ Deleted video generation "${topic || "Untitled"}" and all its assets successfully.`);
        // If the deleted generation is currently loaded in the publisher/editor state, clear it:
        if (generationId === genId) {
          setGenerationId(null);
          setFinalVideoUrl(null);
          setThumbnailUrl(null);
          setStoryboard([]);
          setGeneratedTopic("");
          setUploadTitle("");
          setUploadDescription("");
          setUploadTags("");
          addLog(`🧹 Cleared deleted generation from publisher/editor panel.`);
        }
        // Reload history
        loadHistory();
      } else {
        const errorData = await res.json();
        alert(`Failed to delete generation: ${errorData.detail || res.statusText}`);
      }
    } catch (err: any) {
      console.error("Failed to delete generation:", err);
      alert(`Error deleting generation: ${err.message || err}`);
    }
  };

  const loadUploadQueue = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/upload-queue");
      if (res.ok) {
        setUploadQueue(await res.json());
      }
    } catch (err) {
      console.error("Failed to load upload queue:", err);
    }
  };

  const handleGenerateViralShort = async () => {
    // Wrapper to trigger two-stage flow
    await handleDraftStoryboard();
  };



  const handleInitYoutubeAuth = async () => {
    addLog("🔑 Launching YouTube OAuth Authentication flow...");
    try {
      const res = await fetch("http://localhost:8000/api/youtube/auth-init");
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to start auth flow");
      }
      addLog("👉 Google login browser tab should have opened. Please authenticate there.");
      
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch("http://localhost:8000/api/youtube/auth-status");
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (statusData.authenticated) {
              setIsYtAuthenticated(true);
              addLog("✅ YouTube account authorized successfully!");
              clearInterval(interval);
            }
          }
        } catch (err) {
          console.error("Error checking YouTube auth status:", err);
        }
      }, 3000);
      
      setTimeout(() => clearInterval(interval), 120000);
    } catch (err: any) {
      addLog(`❌ OAuth Error: ${err.message || err}`);
    }
  };

  const handleYoutubeUpload = async () => {
    if (!isYtAuthenticated) {
      alert("YouTube is not authorized. Please authorize your account first.");
      return;
    }

    setYtIsUploading(true);
    setYtUploadLogs(["Initiating YouTube upload request..."]);
    
    try {
      const payload = {
        video_generation_id: generationId || "",
        platforms: ["youtube"],
        youtube_title: uploadTitle,
        youtube_description: uploadDescription,
        youtube_tags: uploadTags.split(",").map(t => t.trim()).filter(Boolean),
        youtube_privacy: uploadPrivacy,
      };

      const res = await fetch("http://localhost:8000/api/schedule-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "YouTube upload job queue failed");
      }

      const result = await res.json();
      setYtUploadJobId(result.job_id);
      setYtUploadLogs(prev => [...prev, "🚀 YouTube upload started!"]);
      loadUploadQueue(); // refresh queue list

      // Poll job status
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch(`http://localhost:8000/api/upload-status/${result.job_id}`);
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            setYtUploadLogs(statusData.logs);

            if (statusData.status === "completed" || statusData.status === "failed") {
              setYtIsUploading(false);
              clearInterval(interval);
              loadUploadQueue();
            }
          }
        } catch (err) {
          console.error("Error polling YouTube upload status:", err);
        }
      }, 1500);

      setTimeout(() => {
        clearInterval(interval);
        setYtIsUploading(false);
      }, 300000);
    } catch (error: any) {
      setYtUploadLogs(prev => [...prev, `❌ Error: ${error.message || error}`]);
      setYtIsUploading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <h1 className="title-glow">🎬 ShortsGen AI</h1>
        <p className="subtitle">Type a topic. Get a finished YouTube Short.</p>
      </header>

      {/* Backend Status Alert */}
      {backendError && (
        <div className="glass-card" style={{ borderColor: "var(--danger)", background: "rgba(239, 68, 68, 0.05)", display: "flex", gap: "12px", alignItems: "center" }}>
          <AlertCircle size={24} color="var(--danger)" style={{ flexShrink: 0 }} />
          <div>
            <h4 style={{ color: "var(--danger)", fontWeight: 600 }}>Backend Connection Offline</h4>
            <p className="form-label-info" style={{ color: "var(--danger)" }}>{backendError}</p>
          </div>
          <button onClick={loadConfig} className="btn btn-secondary" style={{ width: "auto", marginLeft: "auto", padding: "8px 16px", fontSize: "14px" }}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      )}

      {/* Platform Publishing Readiness Checks */}
      {!backendError && (
        <div 
          className="glass-card" 
          style={{ 
            padding: "16px 24px", 
            marginBottom: "24px", 
            display: "flex", 
            flexWrap: "wrap", 
            alignItems: "center", 
            justifyContent: "space-between", 
            gap: "16px",
            borderColor: "rgba(200, 255, 0, 0.15)",
            background: "rgba(200, 255, 0, 0.02)"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <Settings size={20} color="var(--accent)" />
            <div>
              <h3 style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Social Publishing Readiness</h3>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "2px 0 0 0" }}>Check authorization status for direct video publishing to YouTube.</p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
            {/* YouTube Readiness */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.05)", padding: "6px 12px", borderRadius: "10px" }}>
              <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-secondary)" }}>YouTube Shorts:</span>
              {isYtAuthenticated ? (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--ok)", fontSize: "13px", fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Ready
                </span>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--danger)", fontSize: "13px", fontWeight: 600 }}>
                    <AlertCircle size={14} /> Unauthorized
                  </span>
                  <button 
                    onClick={handleInitYoutubeAuth}
                    className="btn btn-secondary" 
                    style={{ padding: "4px 8px", fontSize: "11px", width: "auto", height: "24px", margin: 0 }}
                  >
                    Authorize
                  </button>
                </div>
              )}
            </div>

            {/* Image Engine Readiness */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.05)", padding: "6px 12px", borderRadius: "10px" }}>
              <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-secondary)" }}>
                Image Engine{imageProviderStatus?.provider ? ` (${imageProviderStatus.provider})` : ""}:
              </span>
              {imageProviderStatus?.available ? (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--ok)", fontSize: "13px", fontWeight: 600 }}
                  title={imageProviderStatus?.device ? `${imageProviderStatus.model} on ${imageProviderStatus.device}` : ""}>
                  <CheckCircle2 size={14} /> {imageProviderStatus?.provider === "local" ? (imageProviderStatus?.device || "Ready") : "Ready"}
                </span>
              ) : (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--danger)", fontSize: "13px", fontWeight: 600 }}
                  title={imageProviderStatus?.provider === "local" ? "Start it with: python sd_server.py" : "Provider unavailable"}>
                  <AlertCircle size={14} /> {imageProviderStatus?.provider === "local" ? "Server Off" : "Unavailable"}
                </span>
              )}
            </div>

            {/* Refresh button */}
            <button
              onClick={refreshReadiness}
              disabled={isCheckingReadiness}
              className="btn btn-secondary"
              style={{ width: "auto", height: "34px", padding: "0 10px", margin: 0 }}
              title="Refresh Readiness Status"
            >
              <RefreshCw size={14} style={{ animation: isCheckingReadiness ? "spin 1s linear infinite" : "none" }} />
            </button>
          </div>
        </div>
      )}

      {/* Tabs Menu */}
      <div className="tabs-container">
        <button 
          onClick={() => setActiveTab("viral")} 
          className={`tab-btn ${activeTab === "viral" ? "tab-btn-active" : ""}`}
        >
          <Sparkles size={18} /> 📱 Viral Shorts Studio
        </button>
        <button 
          onClick={() => { setActiveTab("library"); loadHistory(); }} 
          className={`tab-btn ${activeTab === "library" ? "tab-btn-active" : ""}`}
        >
          <Tv size={18} /> 📚 Video Library
        </button>
        <button
          onClick={() => { setActiveTab("queue"); loadUploadQueue(); }}
          className={`tab-btn ${activeTab === "queue" ? "tab-btn-active" : ""}`}
        >
          <Layers size={18} /> 🕒 Upload Queue
        </button>
      </div>

      {/* Main Grid Panels / Full Screens */}
      {activeTab !== "library" && activeTab !== "queue" ? (
        <div className="dashboard-grid">
          {/* Left Side: Forms */}
          <div className="form-panel">
          
          {/* TAB 1: VIRAL SHORTS STUDIO */}
          {activeTab === "viral" && (
            <>
              <div className="glass-card" id="viral-config-card">
                <h2 className="card-title"><Sparkles /> Script Drafting Configuration</h2>
              
                <div className="form-group">
                  <label className="form-label">Video Topic or Category Prompt</label>
                  <textarea 
                    className="form-textarea" 
                    rows={2}
                    value={viralPrompt}
                    onChange={(e) => setViralPrompt(e.target.value)}
                    placeholder="Describe your video topic... (e.g. quantum physics facts, dark history of ancient cities)"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Script Hook Template</label>
                    <select 
                      className="form-select"
                      value={viralHookStyle}
                      onChange={(e) => setViralHookStyle(e.target.value)}
                    >
                      {config?.viral_hooks.map(hook => (
                        <option key={hook} value={hook}>{hook}</option>
                      )) || <option>Loading...</option>}
                    </select>
                    <p className="form-label-info">Shapes script opening scenes to maximize hook retention.</p>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Target Duration</label>
                    <select
                      className="form-select"
                      value={durationPreset}
                      onChange={(e) => setDurationPreset(e.target.value)}
                    >
                      {(config?.duration_presets ?? ["Quick (15-20s)", "Standard (25-35s)"]).map(d => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <p className="form-label-info">25-35s is the retention sweet spot for most niches; Quick trades depth for a faster loop.</p>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Ollama LLM Model</label>
                    <select 
                      className="form-select"
                      value={viralOllamaModel}
                      onChange={(e) => setViralOllamaModel(e.target.value)}
                    >
                      {config?.ollama_models.map(m => (
                        <option key={m} value={m}>{m}</option>
                      )) || <option>Loading...</option>}
                    </select>
                    <label className="checkbox-container" style={{ marginTop: "10px", display: "flex", alignItems: "center", cursor: "pointer" }}>
                      <input 
                        type="checkbox" 
                        checked={enableSearch}
                        onChange={(e) => setEnableSearch(e.target.checked)}
                        style={{ marginRight: "6px" }}
                      />
                      <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--accent)" }}>🔍 Fact-Check with Internet Search (RAG)</span>
                    </label>
                  </div>
                </div>

                <button 
                  onClick={handleDraftStoryboard}
                  disabled={drafting || !config} 
                  className="btn btn-primary"
                  style={{ marginTop: "15px", background: "linear-gradient(135deg, var(--accent) 0%, var(--accent) 100%)" }}
                >
                  📝 {drafting ? "Drafting Storyboard..." : "Draft Script & Storyboard"}
                </button>
              </div>

              <div className="glass-card" style={{ marginTop: "20px" }}>
                <h2 className="card-title"><Tv /> Video Style & Rendering Settings</h2>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Image Engine / Provider</label>
                    <select
                      className="form-select"
                      value={imageProvider}
                      onChange={(e) => handleChangeImageProvider(e.target.value)}
                    >
                      <option value="pollinations">Pollinations (Free hosted — no key, capped at 576×1024)</option>
                      <option value="local">Local SDXL (Free, on-device — full 1080p detail)</option>
                      <option value="leonardo">Leonardo (Cloud API — needs key)</option>
                    </select>
                    {/* Sharpness is decided here, not in the encoder: an image
                        generated below the delivery frame has to be upscaled,
                        and upscaling cannot put detail back. */}
                    {imageProviderStatus?.max_resolution && (
                      <p className="form-label-info">
                        Generates at {imageProviderStatus.max_resolution}, delivered at{" "}
                        {imageProviderStatus.delivery_resolution}
                        {imageProviderStatus.upscale_factor > 1.05 ? (
                          <>
                            {" "}— upscaled {imageProviderStatus.upscale_factor}×.{" "}
                            <strong style={{ color: "var(--warn)" }}>
                              Upscaling cannot add detail back.
                            </strong>
                          </>
                        ) : (
                          <> — near-native, no meaningful upscale.</>
                        )}
                      </p>
                    )}

                    {imageProvider === "local" && sdModels.length > 0 && (
                      <div style={{ marginTop: "10px" }}>
                        <label className="form-label">Local Model</label>
                        <select
                          className="form-select"
                          value={sdCurrentModel}
                          disabled={switchingModel}
                          onChange={(e) => handleSelectSdModel(e.target.value)}
                        >
                          {sdModels.map((m: any) => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                          ))}
                        </select>
                        {(() => {
                          const active = sdModels.find((m: any) => m.id === sdCurrentModel);
                          if (!active) return null;
                          return (
                            <p className="form-label-info">
                              {active.note} {active.steps} steps
                              {active.download_gb ? `, ~${active.download_gb}GB download on first use` : ""}.
                            </p>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Visual Format Mode</label>
                    <select
                      className="form-select"
                      value={visualMode}
                      onChange={(e) => setVisualMode(e.target.value)}
                    >
                      <option value="Cinematic Slideshow">Cinematic Slideshow (Pan & Zoom)</option>
                      <option value="Leonardo Motion Video">Leonardo Motion (Image-to-Video API)</option>
                      <option value="Hailuo Animated Video">Hailuo Animated Video (MiniMax)</option>
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Art Style</label>
                    <select
                      className="form-select"
                      value={artStyle}
                      onChange={(e) => setArtStyle(e.target.value)}
                    >
                      {(config?.art_styles && config.art_styles.length > 0
                        ? config.art_styles
                        : ["Photorealistic", "Stickman Animation"]
                      ).map((s: string) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {visualMode === "Hailuo Animated Video" && (
                  <p style={{ color: "var(--warn)", fontSize: 12, marginTop: -8 }}>
                    ~5–9 min/scene · needs MINIMAX_API_KEY (free trial at platform.minimax.io). Falls back to slideshow if unavailable.
                  </p>
                )}
                {artStyle === "Stickman Animation" && visualMode === "Hailuo Animated Video" && (
                  <p style={{ color: "var(--accent)", fontSize: 12, marginTop: -4 }}>
                    Best match for animated stickman videos.
                  </p>
                )}

                {imageProvider === "leonardo" && (
                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">Leonardo Generator Model</label>
                      <select
                        className="form-select"
                        value={viralLeonardoModel}
                        onChange={(e) => setViralLeonardoModel(e.target.value)}
                      >
                        {config?.leonardo_models.map(m => (
                          <option key={m} value={m}>{m}</option>
                        )) || <option>Loading...</option>}
                      </select>
                    </div>
                  </div>
                )}

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Voice Narrator</label>
                    <select 
                      className="form-select"
                      value={viralVoice}
                      onChange={(e) => {
                        const newVoice = e.target.value;
                        setViralVoice(newVoice);
                        if (storyboard && storyboard.length > 0) {
                          const updated = storyboard.map(scene => ({
                            ...scene,
                            speaker: newVoice
                          }));
                          setStoryboard(updated);
                        }
                      }}
                    >
                      {config?.voices.map(v => (
                        <option key={v} value={v}>{v}</option>
                      )) || <option>Loading...</option>}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Voice Speed ({viralVoiceSpeed}x)</label>
                    <input 
                      type="range" 
                      min="0.5" 
                      max="2.0" 
                      step="0.1"
                      className="form-input" 
                      value={viralVoiceSpeed}
                      onChange={(e) => setViralVoiceSpeed(parseFloat(e.target.value))}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Split-Screen Satisfying Loop</label>
                    <select 
                      className="form-select"
                      value={satisfyingBackground}
                      onChange={(e) => setSatisfyingBackground(e.target.value)}
                    >
                      {config?.satisfying_presets.map(p => (
                        <option key={p} value={p}>{p}</option>
                      )) || <option>Loading...</option>}
                    </select>
                    <p className="form-label-info">Displays story visual on top, gameplay on bottom.</p>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Background Music</label>
                    <select 
                      className="form-select"
                      value={musicStyle}
                      onChange={(e) => setMusicStyle(e.target.value)}
                    >
                      {config?.music_presets.map(m => (
                        <option key={m} value={m}>{m}</option>
                      )) || <option>Loading...</option>}
                    </select>
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: "12px", marginBottom: "12px" }}>
                  <label className="checkbox-container" style={{ margin: 0 }}>
                    <input 
                      type="checkbox" 
                      checked={enableTransitionSfx}
                      onChange={(e) => setEnableTransitionSfx(e.target.checked)}
                    />
                    <div className="checkbox-custom"></div>
                    <span style={{ fontSize: "14px", fontWeight: 600 }}>Transition Sound Effects</span>
                  </label>
                  <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "4px" }}>
                    Off by default &mdash; the bundled whoosh reads as noise rather than a transition.
                    Replace <code>assets/sfx/whoosh.wav</code> with your own before turning this on.
                  </p>
                </div>

                <div className="form-group" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "15px" }}>
                  <label className="form-label"><Subtitles size={16} style={{ display: "inline", marginRight: "6px" }} /> Auto-Caption & Visual Position Settings</label>
                  
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "20px", marginTop: "12px" }}>
                    <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: "16px" }}>
                      <label className="checkbox-container" style={{ margin: 0 }}>
                        <input 
                          type="checkbox" 
                          checked={enableCaptions}
                          onChange={(e) => setEnableCaptions(e.target.checked)}
                        />
                        <div className="checkbox-custom"></div>
                        <span style={{ fontSize: "14px", fontWeight: 600 }}>Burn Centered Word-Highlight Subtitles</span>
                      </label>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ marginBottom: "6px" }}>Caption Style</label>
                        <select
                          className="form-select"
                          value={captionStyle}
                          onChange={(e) => setCaptionStyle(e.target.value)}
                          disabled={!enableCaptions}
                        >
                          <option value="Viral Pop">Viral Pop (Pops + Color Highlights)</option>
                          <option value="Soft Pill">Soft Pill (Rounded Plate + Highlights)</option>
                          <option value="Standard">Standard Bottom Text</option>
                        </select>
                        <p className="form-label-info">
                          Soft Pill draws a rounded translucent plate behind the words, so they stay
                          readable over bright or busy footage where an outline alone disappears.
                        </p>
                      </div>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span>Text Size</span>
                          <span style={{ color: "var(--accent)", fontWeight: 600 }}>{captionSize}px</span>
                        </label>
                        <div className="slider-group">
                          <input 
                            type="range" 
                            min="24" 
                            max="120" 
                            value={captionSize} 
                            onChange={(e) => setCaptionSize(parseInt(e.target.value))}
                            style={{ flexGrow: 1, padding: 0, height: "6px", background: "rgba(255,255,255,0.1)", borderRadius: "3px", cursor: "pointer" }}
                            disabled={!enableCaptions}
                          />
                        </div>
                        <p className="form-label-info">Base subtitle font size on the 1920 height canvas.</p>
                      </div>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span>Vertical Position (from bottom)</span>
                          <span style={{ color: "var(--accent)", fontWeight: 600 }}>{captionMarginV}px</span>
                        </label>
                        <div className="slider-group">
                          <input 
                            type="range" 
                            min="50" 
                            max="800" 
                            value={captionMarginV} 
                            onChange={(e) => setCaptionMarginV(parseInt(e.target.value))}
                            style={{ flexGrow: 1, padding: 0, height: "6px", background: "rgba(255,255,255,0.1)", borderRadius: "3px", cursor: "pointer" }}
                            disabled={!enableCaptions}
                          />
                        </div>
                        <p className="form-label-info">Higher margin moves text upward on screen.</p>
                      </div>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ marginBottom: "6px" }}>Highlight Accent Color</label>
                        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                          {COLOR_PRESETS.map((preset) => {
                            const isSelected = captionColor === preset.ass;
                            return (
                              <button
                                key={preset.name}
                                type="button"
                                disabled={!enableCaptions}
                                onClick={() => setCaptionColor(preset.ass)}
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: "6px",
                                  background: isSelected ? "rgba(200, 255, 0, 0.25)" : "rgba(255,255,255,0.03)",
                                  border: `1px solid ${isSelected ? "var(--accent)" : "rgba(255,255,255,0.08)"}`,
                                  borderRadius: "20px",
                                  padding: "6px 12px",
                                  cursor: enableCaptions ? "pointer" : "not-allowed",
                                  color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                                  fontSize: "12px",
                                  fontWeight: 600,
                                  transition: "all 0.2s ease"
                                }}
                              >
                                <span style={{
                                  width: "10px",
                                  height: "10px",
                                  borderRadius: "50%",
                                  backgroundColor: preset.hex,
                                  border: "1px solid rgba(0,0,0,0.2)",
                                  display: "inline-block"
                                }} />
                                {preset.name}
                              </button>
                            );
                          })}
                        </div>
                        <p className="form-label-info">Spoken word active highlights color.</p>
                      </div>
                    </div>

                    <div 
                      style={{ 
                        flex: "0 0 180px", 
                        display: "flex", 
                        flexDirection: "column", 
                        alignItems: "center", 
                        margin: "0 auto",
                        opacity: enableCaptions ? 1 : 0.35,
                        transition: "opacity 0.3s ease" 
                      }}
                    >
                      <span className="form-label" style={{ marginBottom: "8px", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.5px" }}>Live Text Preview</span>
                      <div 
                        style={{ 
                          position: "relative", 
                          width: "180px", 
                          height: "320px", 
                          borderRadius: "14px", 
                          overflow: "hidden", 
                          border: "2px solid rgba(200, 255, 0, 0.3)",
                          boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
                          backgroundImage: "url('/sample_short.png')",
                          backgroundSize: "cover",
                          backgroundPosition: "center"
                        }}
                      >
                        <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: "1px", borderTop: "1px dashed rgba(255,255,255,0.4)", pointerEvents: "none" }} />
                        <div 
                          style={{ 
                            position: "absolute", 
                            left: 0, 
                            right: 0, 
                            bottom: `${(captionMarginV / 1920) * 320}px`, 
                            textAlign: "center", 
                            fontSize: `${(captionSize / 1920) * 320}px`, 
                            fontFamily: captionFont === "Arial" ? "Arial, sans-serif" : captionFont,
                            fontWeight: "bold",
                            lineHeight: 1.2,
                            color: "#FFFFFF",
                            textShadow: "1.5px 1.5px 0px #000, -1.5px -1.5px 0px #000, 1.5px -1.5px 0px #000, -1.5px 1.5px 0px #000, 2px 2px 4px rgba(0,0,0,0.8)",
                            padding: "0 12px",
                            pointerEvents: "none",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center"
                          }}
                        >
                          <span>
                            This is a <span style={{ color: COLOR_PRESETS.find(p => p.ass === captionColor)?.hex || "#FFFF00" }}>viral</span> short!
                          </span>
                        </div>
                        <div style={{ position: "absolute", inset: 0, boxShadow: "inset 0 0 10px rgba(0,0,0,0.8)", pointerEvents: "none" }} />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="form-group" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "15px", marginTop: "18px" }}>
                  <label className="form-label">
                    <Gauge size={16} style={{ display: "inline", marginRight: "6px" }} /> Delivery Quality &amp; Retention
                  </label>
                  <p className="form-label-info" style={{ marginBottom: "14px" }}>
                    Everything YouTube judges on playback: sharpness, motion, loudness and the first three seconds.
                  </p>

                  {/* The single biggest lever on whether a short looks real:
                      filmed footage has no anatomy for a model to get wrong. */}
                  <div className="form-group">
                    <label className="form-label">Where Visuals Come From</label>
                    <select
                      className="form-select"
                      value={visualSourceMode}
                      onChange={(e) => setVisualSourceMode(e.target.value)}
                    >
                      {(config?.visual_source_modes ?? ["Smart Mix", "Real Footage Only", "AI Only"]).map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <p className="form-label-info">
                      {visualSourceMode === "Real Footage Only" && (
                        <>Every scene uses real Pexels video. Most believable, but abstract topics get loose matches.</>
                      )}
                      {visualSourceMode === "Smart Mix" && (
                        <>Real footage for anything filmable, AI only for shots that can&apos;t exist
                          (inside a black hole, the year 3000). Recommended.</>
                      )}
                      {visualSourceMode === "AI Only" && (
                        <>Every scene generated. Full creative control, but people may come out
                          with distorted hands and faces.</>
                      )}
                      {config?.stock_available === false && (
                        <strong style={{ color: "var(--warn)", display: "block", marginTop: "4px" }}>
                          No PEXELS_API_KEY set — real footage will fall back to AI generation.
                        </strong>
                      )}
                    </p>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">Encode Quality</label>
                      <select className="form-select" value={quality} onChange={(e) => setQuality(e.target.value)}>
                        {(config?.quality_presets ?? ["High (recommended)"]).map((q) => (
                          <option key={q} value={q}>{q}</option>
                        ))}
                      </select>
                      <p className="form-label-info">
                        Delivered as {config?.delivery?.resolution ?? "1080x1920"} @ {config?.delivery?.fps ?? 30}fps,
                        fast-start so playback never stalls on the first frame.
                      </p>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Camera Motion</label>
                      <select className="form-select" value={motionStyle} onChange={(e) => setMotionStyle(e.target.value)}>
                        {(config?.motion_styles ?? ["Dynamic", "Subtle", "Off"]).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                      <p className="form-label-info">
                        Dynamic alternates the push and pan each scene so stills stop reading as a slideshow.
                      </p>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "8px" }}>
                    <label className="checkbox-container" style={{ margin: 0 }}>
                      <input type="checkbox" checked={normalizeAudio} onChange={(e) => setNormalizeAudio(e.target.checked)} />
                      <div className="checkbox-custom"></div>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>
                        Normalize loudness to {config?.delivery?.target_lufs ?? -14} LUFS
                      </span>
                    </label>
                    <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "-6px" }}>
                      Matches YouTube&apos;s playback target, so the platform leaves your mix alone instead of turning a quiet one up along with its noise floor.
                    </p>

                    <label className="checkbox-container" style={{ margin: 0 }}>
                      <input type="checkbox" checked={duckMusic} onChange={(e) => setDuckMusic(e.target.checked)} />
                      <div className="checkbox-custom"></div>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>Duck music under narration</span>
                    </label>
                    <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "-6px" }}>
                      Sidechain compression pulls the bed down while the voice speaks and lets it swell back between lines.
                    </p>

                    <label className="checkbox-container" style={{ margin: 0 }}>
                      <input type="checkbox" checked={progressBar} onChange={(e) => setProgressBar(e.target.checked)} />
                      <div className="checkbox-custom"></div>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>Burn a retention progress bar</span>
                    </label>
                    <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "-6px" }}>
                      Shorts hide the scrubber — a visible &ldquo;almost done&rdquo; cue keeps viewers from swiping away mid-video.
                    </p>

                    <label className="checkbox-container" style={{ margin: 0 }}>
                      <input type="checkbox" checked={enableThumbnail} onChange={(e) => setEnableThumbnail(e.target.checked)} />
                      <div className="checkbox-custom"></div>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>Generate a title thumbnail</span>
                    </label>
                    <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "-6px" }}>
                      A graded, big-text tile for search, the channel grid and suggested feeds.
                    </p>

                    <label className="checkbox-container" style={{ margin: 0 }}>
                      <input type="checkbox" checked={subscribeOverlay} onChange={(e) => setSubscribeOverlay(e.target.checked)} />
                      <div className="checkbox-custom"></div>
                      <span style={{ fontSize: "14px", fontWeight: 600 }}>Blinking SUBSCRIBE call-to-action</span>
                    </label>
                  </div>

                  {subscribeOverlay && (
                    <div className="form-group" style={{ marginTop: "12px" }}>
                      <label className="form-label">Channel Handle (optional)</label>
                      <input
                        className="form-input"
                        value={channelHandle}
                        onChange={(e) => setChannelHandle(e.target.value)}
                        placeholder="@yourchannel"
                      />
                      <p className="form-label-info">Shown under the SUBSCRIBE badge in the closing seconds.</p>
                    </div>
                  )}
                </div>

                <button
                  onClick={handleRenderStoryboard}
                  disabled={rendering || !config || storyboard.length === 0}
                  className="btn btn-primary"
                  style={{
                    marginTop: "20px",
                    background: "var(--surface-2)", border: "1px solid rgba(245,178,61,0.25)",
                    boxShadow: "0 4px 15px rgba(244, 63, 94, 0.2)"
                  }}
                >
                  🎬 {rendering ? "Rendering Video..." : "Compile & Render Video"}
                </button>
                {storyboard.length === 0 && (
                  <p className="form-label-info" style={{ color: "var(--danger)", marginTop: "8px", textAlign: "center" }}>
                    ⚠️ Please draft a script and storyboard above first to enable video rendering.
                  </p>
                )}
              </div>
            </>
          )}

          {/* TAB 2: FULL PRESENTER PIPELINE */}
        </div>

        {/* Right Side: Output and Previews */}
        <div className="preview-panel">
          <div className="preview-pane">
            
            {/* Main Video Output */}
            <div className="glass-card" style={{ padding: "18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px" }}>
                <h3 className="card-title" style={{ margin: 0, fontSize: "18px" }}>
                  <Tv size={18} /> Generated Output
                </h3>
                {statusText && (
                  <span style={{ 
                    fontSize: "12px", 
                    fontWeight: 700, 
                    color: statusText === "Finished!" ? "var(--ok)" : statusText === "Failed" ? "var(--danger)" : "var(--accent)",
                    background: "rgba(255,255,255,0.03)",
                    padding: "4px 10px",
                    borderRadius: "12px",
                    border: "1px solid rgba(255,255,255,0.05)"
                  }}>
                    {statusText}
                  </span>
                )}
              </div>

              {loading ? (
                <div className="video-container" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--bg-2)" }}>
                  <div className="loader-glow"></div>
                  <h4 style={{ color: "var(--accent)", fontWeight: 700 }}>Processing AI pipeline...</h4>
                  <p className="form-label-info" style={{ width: "80%", textAlign: "center", marginTop: "8px" }}>Exchanges models, draws images, loops voiceover, synthesizes lip-movements and merges B-roll layouts.</p>
                </div>
              ) : finalVideoUrl ? (
                <div className="video-container">
                  <video key={finalVideoUrl} controls autoPlay loop>
                    <source src={finalVideoUrl} type="video/mp4" />
                    Your browser does not support the video tag.
                  </video>
                </div>
              ) : (
                <div className="video-container" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--bg-2)", opacity: 0.8 }}>
                  <Tv size={48} color="var(--text-muted)" style={{ marginBottom: "15px" }} />
                  <p style={{ color: "var(--text-muted)", fontSize: "14px", fontWeight: 500 }}>No video generated yet.</p>
                  <p className="form-label-info" style={{ textAlign: "center", width: "80%" }}>Select a tab, fill in the topic details, and click Generate to start rendering your shorts video.</p>
                </div>
              )}

              {/* Download link */}
              {finalVideoUrl && !loading && (
                <a
                  href={finalVideoUrl}
                  download
                  className="btn btn-secondary"
                  style={{ marginTop: "10px", fontSize: "14px", padding: "8px 16px" }}
                >
                  📥 Download Rendered Video
                </a>
              )}

              {/* Generated thumbnail — what viewers actually click on in search
                  and suggested feeds, so it gets its own preview and download. */}
              {thumbnailUrl && !loading && (
                <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--border)" }}>
                  <span className="form-label" style={{ fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: "8px" }}>
                    Generated Thumbnail
                  </span>
                  <div style={{ display: "flex", gap: "14px", alignItems: "flex-start" }}>
                    <img
                      src={thumbnailUrl}
                      alt="Generated video thumbnail"
                      style={{
                        width: "108px",
                        borderRadius: "var(--border-radius-sm)",
                        border: "1px solid var(--border-strong)",
                        display: "block"
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p className="form-label-info" style={{ margin: "0 0 10px 0" }}>
                        Graded and captioned for legibility at grid size.
                      </p>
                      <a
                        href={thumbnailUrl}
                        download
                        className="btn btn-secondary"
                        style={{ fontSize: "13px", padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                      >
                        <Download size={14} /> Download Thumbnail
                      </a>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Publish to YouTube */}
            {finalVideoUrl && !loading && (
              <div className="glass-card" style={{ padding: "18px", border: "1px solid rgba(200, 255, 0, 0.2)", marginTop: "15px" }}>
                <h3 className="card-title" style={{ fontSize: "18px", display: "flex", gap: "8px", alignItems: "center", color: "var(--accent)", margin: "0 0 10px 0" }}>
                  <Sparkles size={18} /> Publish to YouTube
                </h3>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>YouTube account</span>
                  {isYtAuthenticated ? (
                    <span style={{ fontSize: "11px", color: "var(--ok)", fontWeight: 700 }}>Connected ✅</span>
                  ) : (
                    <button
                      onClick={handleInitYoutubeAuth}
                      className="btn btn-secondary"
                      style={{ padding: "4px 8px", fontSize: "11px", width: "auto", margin: 0 }}
                    >
                      Authorize
                    </button>
                  )}
                </div>

                <div className="form-group" style={{ marginBottom: "10px" }}>
                  <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Title (max 100 chars)</label>
                  <input
                    type="text"
                    className="form-input"
                    maxLength={100}
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    placeholder="E.g. Inside the Quantum Physics Realm! 🧪"
                  />
                  <span className="form-label-info" style={{ textAlign: "right", display: "block", fontSize: "10px", marginTop: "2px" }}>{uploadTitle.length}/100</span>
                </div>

                <div className="form-group" style={{ marginBottom: "10px" }}>
                  <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Description</label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    value={uploadDescription}
                    onChange={(e) => setUploadDescription(e.target.value)}
                    placeholder="Tell viewers what your short is about..."
                  />
                </div>

                <div className="form-row" style={{ gap: "10px", marginBottom: "14px" }}>
                  <div className="form-group" style={{ flex: 1, margin: 0 }}>
                    <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Tags (comma-separated)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={uploadTags}
                      onChange={(e) => setUploadTags(e.target.value)}
                      placeholder="shorts, science, viral"
                    />
                  </div>
                  <div className="form-group" style={{ width: "110px", margin: 0 }}>
                    <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Privacy</label>
                    <select
                      className="form-select"
                      value={uploadPrivacy}
                      onChange={(e) => setUploadPrivacy(e.target.value)}
                      style={{ height: "38px" }}
                    >
                      <option value="private">Private</option>
                      <option value="unlisted">Unlisted</option>
                      <option value="public">Public</option>
                    </select>
                  </div>
                </div>

                <button
                  onClick={handleYoutubeUpload}
                  disabled={ytIsUploading}
                  className="btn btn-primary"
                >
                  🚀 {ytIsUploading ? "Uploading..." : "Upload to YouTube"}
                </button>

                {(ytIsUploading || ytUploadLogs.length > 0) && (
                  <div style={{ marginTop: "12px" }}>
                    <span className="form-label" style={{ fontSize: "10px", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>Upload Progress</span>
                    <div className="log-console" style={{ height: "90px", fontSize: "11px", overflowY: "auto", padding: "6px" }}>
                      {ytUploadLogs.map((log, i) => (
                        <div key={i} style={{ color: log.startsWith("❌") ? "var(--danger)" : log.startsWith("✅") || log.includes("successful") ? "var(--ok)" : "var(--text-primary)", marginBottom: "2px" }}>{log}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}


            {/* Log Console */}
            <div className="glass-card" style={{ padding: "18px" }}>
              <h3 className="card-title" style={{ fontSize: "16px", marginBottom: "8px" }}><FileText size={16} /> Console Execution Logs</h3>
              <div className="log-console">
                {logs.length === 0 ? (
                  <div className="log-entry" style={{ color: "var(--text-muted)" }}>Waiting to run a generation job...</div>
                ) : (
                  logs.map((log, i) => (
                    <div key={i} className="log-entry">{log}</div>
                  ))
                )}
                <div ref={consoleEndRef} />
              </div>
            </div>

          </div>
        </div>
      </div>
      ) : (
        <div className="library-queue-panels">
          {activeTab === "library" && (
            <div className="glass-card" style={{ padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
                <div>
                  <h2 className="card-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                    <Tv /> Video Library History
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginTop: "4px" }}>
                    Browse your database of previously generated video shorts and drafts.
                  </p>
                </div>
                <button onClick={loadHistory} className="btn btn-secondary" style={{ width: "auto", margin: 0, padding: "8px 16px" }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              <div className="library-grid">
                {history.length === 0 ? (
                  <div style={{ gridColumn: "1/-1", textAlign: "center", padding: "60px 20px", color: "var(--text-muted)" }}>
                    <Tv size={48} style={{ marginBottom: "15px", opacity: 0.3 }} />
                    <p style={{ fontSize: "15px", fontWeight: 500 }}>No video history found.</p>
                    <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>Start generating shorts to build your video library.</p>
                  </div>
                ) : (
                  history.map((item) => (
                    <div key={item.id} className="library-card">
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                          <span style={{ 
                            fontSize: "10px", 
                            fontWeight: 700, 
                            textTransform: "uppercase",
                            padding: "3px 8px", 
                            borderRadius: "10px",
                            background: item.status === "completed" ? "rgba(16, 185, 129, 0.1)" : item.status === "draft" ? "rgba(200, 255, 0, 0.1)" : "rgba(239, 68, 68, 0.1)",
                            color: item.status === "completed" ? "var(--ok)" : item.status === "draft" ? "var(--accent)" : "var(--danger)",
                            border: `1px solid ${item.status === "completed" ? "rgba(16, 185, 129, 0.2)" : item.status === "draft" ? "rgba(200, 255, 0, 0.2)" : "rgba(239, 68, 68, 0.2)"}`
                          }}>
                            {item.status}
                          </span>
                          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                            {new Date(item.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        
                        <h4 style={{ color: "var(--text-primary)", fontSize: "15px", fontWeight: 600, margin: "0 0 8px 0", lineHeight: "1.4" }}>
                          {item.topic || item.prompt || "Untitled Short"}
                        </h4>
                        
                        {item.status === "completed" && item.video_url && (
                          <div className="video-container" style={{ minHeight: "150px", background: "var(--bg-2)", borderRadius: "8px", overflow: "hidden", margin: "10px 0" }}>
                            <video src={item.video_url} controls style={{ width: "100%", maxHeight: "200px" }} />
                          </div>
                        )}
                        
                        {item.status === "draft" && (
                          <div style={{ padding: "12px", background: "rgba(255,255,255,0.02)", borderRadius: "8px", border: "1px dashed rgba(255,255,255,0.05)", margin: "10px 0", textAlign: "center", color: "var(--text-secondary)", fontSize: "12px" }}>
                            📝 Storyboard draft ready for editing.
                          </div>
                        )}

                        {item.status === "failed" && (
                          <div style={{ padding: "12px", background: "rgba(239,68,68,0.02)", borderRadius: "8px", border: "1px dashed rgba(239,68,68,0.08)", margin: "10px 0", textAlign: "center", color: "var(--danger)", fontSize: "12px" }}>
                            ❌ Generation failed.
                          </div>
                        )}
                      </div>

                      {item.status === "completed" && item.video_url && (
                        <button
                          onClick={() => {
                            setGenerationId(item.id);
                            setFinalVideoUrl(item.video_url);
                            setStoryboard(item.storyboard || []);
                            setGeneratedTopic(item.topic || "");
                            
                            const scriptData = item.script_data || {};
                            setUploadTitle(scriptData.youtube_metadata?.title || item.topic || "");
                            setUploadDescription(scriptData.youtube_metadata?.description || "");
                            setUploadTags(scriptData.youtube_metadata?.tags?.join(", ") || "");

                            setActiveTab("viral");
                            addLog(`📂 Loaded video generation "${item.topic || "Untitled"}" to publisher.`);
                          }}
                          className="btn btn-secondary"
                          style={{
                            width: "100%",
                            marginTop: "12px",
                            background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-press) 100%)",
                            border: "none",
                            color: "var(--accent-ink)",
                            fontWeight: 600,
                            padding: "8px 0"
                          }}
                        >
                          📤 Load to Publisher Panel
                        </button>
                      )}

                      {item.status === "draft" && (
                        <button
                          onClick={() => {
                            setGenerationId(item.id);
                            setStoryboard(item.storyboard || []);
                            setGeneratedTopic(item.topic || "");
                            setActiveTab("viral");
                            addLog(`📂 Loaded draft "${item.topic || "Untitled"}" to Storyboard Editor.`);
                          }}
                          className="btn btn-secondary"
                          style={{
                            width: "100%",
                            marginTop: "12px",
                            borderColor: "rgba(200, 255, 0, 0.4)",
                            color: "var(--accent)"
                          }}
                        >
                          ✏️ Edit Storyboard Draft
                        </button>
                      )}

                      <button
                        onClick={() => handleDeleteGeneration(item.id, item.topic || item.prompt || "")}
                        className="btn btn-secondary"
                        style={{
                          width: "100%",
                          marginTop: "8px",
                          borderColor: "rgba(239, 68, 68, 0.2)",
                          color: "var(--danger)",
                          background: "rgba(239, 68, 68, 0.05)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "6px"
                        }}
                      >
                        <Trash2 size={14} /> Delete Video & Assets
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === "queue" && (
            <div className="glass-card" style={{ padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
                <div>
                  <h2 className="card-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                    <Layers /> Social Upload Queue
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginTop: "4px" }}>
                    Monitor YouTube upload jobs and view their execution logs.
                  </p>
                </div>
                <button onClick={loadUploadQueue} className="btn btn-secondary" style={{ width: "auto", margin: 0, padding: "8px 16px" }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              <div className="queue-list">
                {uploadQueue.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-muted)" }}>
                    <Layers style={{ marginBottom: "15px", opacity: 0.3 }} size={48} />
                    <p style={{ fontSize: "15px", fontWeight: 500 }}>No upload jobs in queue.</p>
                    <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>Upload a video to YouTube from the publisher panel to start.</p>
                  </div>
                ) : (
                  uploadQueue.map((job) => {
                    const isExpanded = expandedJobId === job.id;

                    return (
                      <div key={job.id} className="queue-item">
                        <div className="queue-item-header">
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                              <h4 style={{ color: "var(--text-primary)", fontSize: "16px", fontWeight: 600, margin: 0 }}>
                                {job.topic || "Untitled Video"}
                              </h4>
                              <span className={`status-badge status-${job.status}`}>
                                {job.status}
                              </span>
                            </div>

                            <div style={{ display: "flex", gap: "12px", marginTop: "6px", fontSize: "12px", color: "var(--text-secondary)" }}>
                              <span>📤 Platform: YouTube</span>
                              <span>•</span>
                              <span>Created: {new Date(job.created_at).toLocaleString()}</span>
                            </div>
                          </div>

                          <button
                            onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                            className="btn btn-secondary"
                            style={{ width: "auto", margin: 0, padding: "6px 12px", fontSize: "12px", borderColor: isExpanded ? "var(--accent)" : "rgba(255,255,255,0.1)" }}
                          >
                            {isExpanded ? "Hide Logs Console" : "View Logs Console"}
                          </button>
                        </div>

                        {isExpanded && (
                          <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "12px", marginTop: "6px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: "6px" }}>
                              Execution Terminal Log
                            </span>
                            <div className="log-console" style={{ height: "180px", overflowY: "auto", fontSize: "12px", fontFamily: "monospace", background: "var(--bg-2)" }}>
                              {job.logs && job.logs.length > 0 ? (
                                job.logs.map((log: string, lIdx: number) => (
                                  <div 
                                    key={lIdx} 
                                    className="log-entry" 
                                    style={{ 
                                      color: log.startsWith("❌") || log.toLowerCase().includes("error") ? "var(--danger)" : log.startsWith("✅") || log.toLowerCase().includes("success") ? "var(--ok)" : "var(--text-secondary)",
                                      marginBottom: "4px" 
                                    }}
                                  >
                                    {log}
                                  </div>
                                ))
                              ) : (
                                <div style={{ color: "var(--text-muted)" }}>No logs captured for this job.</div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

        </div>
      )}

      {/* Interactive Storyboard Editor */}
      {activeTab === "viral" && storyboard.length > 0 && (
        <div className="glass-card" style={{ marginTop: "24px", padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
            <div>
              <h2 className="card-title" style={{ color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                <Layers /> Interactive Storyboard: {generatedTopic}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginTop: "4px" }}>
                Edit narration scripts, adjust scene image prompts, select custom voiceovers per speaker, and regenerate individual assets before rendering.
              </p>
            </div>
            
            {/* Render Button */}
            <button
              onClick={handleRenderStoryboard}
              disabled={rendering || storyboard.length === 0}
              className="btn btn-primary"
              style={{
                width: "auto",
                minWidth: "180px",
                height: "44px",
                background: "var(--accent)",
                boxShadow: "none",
                fontWeight: 700,
                fontSize: "14px",
                margin: 0
              }}
            >
              {rendering ? (
                <>
                  <RefreshCw size={16} style={{ animation: "spin 1s linear infinite", marginRight: "8px" }} />
                  Rendering Video...
                </>
              ) : (
                <>
                  🚀 Compile & Render Video
                </>
              )}
            </button>
          </div>

          <div className="timeline">
            {storyboard.map((scene, idx) => {
              const isRegeneratingImage = regeneratingSceneIdx === idx && regeneratingAssetType === "image";
              const isRegeneratingAudio = regeneratingSceneIdx === idx && regeneratingAssetType === "audio";
              
              return (
                <div key={idx} className="timeline-step" style={{ display: "flex", flexDirection: "column", gap: "15px", background: "rgba(255, 255, 255, 0.02)", padding: "20px", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.03)", paddingBottom: "10px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span className="step-num">{idx + 1}</span>
                      <h3 style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>Scene {idx + 1}</h3>
                    </div>
                    {scene.duration && (
                      <span style={{ fontSize: "12px", color: "var(--text-secondary)", background: "rgba(255,255,255,0.03)", padding: "3px 8px", borderRadius: "12px" }}>
                        ⏱️ {scene.duration.toFixed(2)}s
                      </span>
                    )}
                  </div>
                  
                  <div style={{ display: "grid", gridTemplateColumns: "150px 1fr 250px", gap: "20px" }} className="storyboard-columns-layout">
                    
                    {/* Left Column: Visual Asset */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                      {scene.image_url ? (
                        <img
                          src={scene.image_url}
                          alt={`Scene ${idx + 1}`}
                          style={{ width: "120px", aspectRatio: "9/16", objectFit: "cover", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)", boxShadow: "0 4px 12px rgba(0,0,0,0.3)" }}
                        />
                      ) : (
                        <div style={{ width: "120px", aspectRatio: "9/16", background: "var(--bg-2)", border: "1px dashed rgba(255,255,255,0.1)", borderRadius: "8px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: "12px" }}>
                          <ImageIcon size={24} style={{ marginBottom: "8px" }} />
                          No Image
                        </div>
                      )}

                      <button
                        className="btn btn-secondary"
                        onClick={() => handleRegenerateAsset(idx, "image")}
                        disabled={isRegeneratingImage || rendering}
                        style={{ width: "100%", padding: "6px 0", fontSize: "12px" }}
                      >
                        {isRegeneratingImage ? (
                          <RefreshCw size={12} style={{ animation: "spin 1s linear infinite", marginRight: "4px" }} />
                        ) : "🎨"} Regenerate Visual
                      </button>
                    </div>

                    {/* Middle Column: Text Fields & Voice */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {/* Narration Script */}
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Narration Script (Voiceover Text)</label>
                        <textarea
                          className="form-textarea"
                          rows={2}
                          value={scene.narration || ""}
                          onChange={(e) => handleUpdateSceneNarration(idx, e.target.value)}
                          placeholder="What will the character say in this scene?"
                          style={{ fontSize: "13px", lineHeight: "1.4" }}
                        />
                      </div>
                      
                      {/* Visual Prompt */}
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Visual Generation Prompt</label>
                        <textarea
                          className="form-textarea"
                          rows={2}
                          value={scene.visual_prompt || ""}
                          onChange={(e) => handleUpdateScenePrompt(idx, e.target.value)}
                          placeholder="Describe the visual scene..."
                          style={{ fontSize: "13px", lineHeight: "1.4" }}
                        />
                      </div>
                    </div>

                    {/* Right Column: Audio & Speaker Selection */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {/* Speaker Dropdown */}
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Speaker Voice</label>
                        <select
                          className="form-select"
                          value={scene.speaker || viralVoice}
                          onChange={(e) => handleUpdateSceneSpeaker(idx, e.target.value)}
                          style={{ height: "36px", fontSize: "12px", padding: "0 8px" }}
                        >
                          {config?.voices.map(v => (
                            <option key={v} value={v}>{v}</option>
                          )) || <option>Loading...</option>}
                        </select>
                      </div>

                      {/* Audio Player */}
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "auto" }}>
                        <label className="form-label" style={{ fontSize: "12px" }}>🔊 Voice Preview</label>
                        {scene.audio_url ? (
                          <audio key={scene.audio_url} controls className="audio-preview" style={{ width: "100%", height: "28px" }}>
                            <source src={scene.audio_url} type="audio/wav" />
                          </audio>
                        ) : (
                          <div style={{ fontSize: "11px", color: "var(--text-muted)", padding: "6px", background: "rgba(0,0,0,0.2)", borderRadius: "4px", textAlign: "center" }}>
                            No Audio synthesized yet
                          </div>
                        )}
                        
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleRegenerateAsset(idx, "audio")}
                          disabled={isRegeneratingAudio || rendering}
                          style={{ width: "100%", padding: "6px 0", fontSize: "12px", marginTop: "4px" }}
                        >
                          {isRegeneratingAudio ? (
                            <RefreshCw size={12} style={{ animation: "spin 1s linear infinite", marginRight: "4px" }} />
                          ) : "🔊"} Regenerate Audio
                        </button>
                      </div>

                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
