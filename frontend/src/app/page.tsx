"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Tv, Sparkles, Sliders, Play, Settings, AlertCircle, FileText, CheckCircle2, 
  Layers, Volume2, Image as ImageIcon, Music, RefreshCw, Subtitles, HelpCircle,
  Trash2, Film
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
  const [activeTab, setActiveTab] = useState<"viral" | "full" | "manual" | "library" | "queue" | "scheduler" | "longform">("viral");
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

  // Auto Agent Scheduler states
  const [schedulerConfig, setSchedulerConfig] = useState<any>(null);
  const [schedulerLogs, setSchedulerLogs] = useState<any[]>([]);
  const [triggerLoading, setTriggerLoading] = useState(false);

  // Input states: Viral Shorts Studio
  const [viralPrompt, setViralPrompt] = useState("The giant hidden ocean underneath Jupiter's moon Europa");
  const [viralOllamaModel, setViralOllamaModel] = useState("");
  const [enableSearch, setEnableSearch] = useState(false);

  // Trending Topics state
  const [trends, setTrends] = useState<any[]>([]);
  const [trendsGeo, setTrendsGeo] = useState("IN");
  const [isFetchingTrends, setIsFetchingTrends] = useState(false);
  const [trendsError, setTrendsError] = useState("");
  const [viralVoice, setViralVoice] = useState("Sarah (Female - US - Soft)");
  const [viralVoiceSpeed, setViralVoiceSpeed] = useState(1.0);
  const [visualMode, setVisualMode] = useState("Cinematic Slideshow");
  const [viralLeonardoModel, setViralLeonardoModel] = useState("Lucid Realism (High Quality Face)");
  const [musicStyle, setMusicStyle] = useState("Cinematic");
  const [satisfyingBackground, setSatisfyingBackground] = useState("Slime ASMR");
  const [viralHookStyle, setViralHookStyle] = useState("Did You Know? (Fact Hook)");
  const [enableCaptions, setEnableCaptions] = useState(true);
  const [enableTransitionSfx, setEnableTransitionSfx] = useState(true);
  const [captionFont, setCaptionFont] = useState("Arial");
  const [captionSize, setCaptionSize] = useState(72);
  const [captionMarginV, setCaptionMarginV] = useState(150);
  const [captionColor, setCaptionColor] = useState("&H00FFFF&");
  const [captionStyle, setCaptionStyle] = useState("Viral Pop");

  // Social Media Upload States
  const [isYtAuthenticated, setIsYtAuthenticated] = useState(false);
  const [isIgConfigured, setIsIgConfigured] = useState(false);
  const [isCheckingReadiness, setIsCheckingReadiness] = useState(false);
  const [uploadPlatforms, setUploadPlatforms] = useState({ youtube: false, instagram: false });
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadPrivacy, setUploadPrivacy] = useState("private");
  const [uploadCaption, setUploadCaption] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [uploadLogs, setUploadLogs] = useState<string[]>([]);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  
  // YouTube specific upload states
  const [ytIsUploading, setYtIsUploading] = useState(false);
  const [ytUploadJobId, setYtUploadJobId] = useState<string | null>(null);
  const [ytUploadLogs, setYtUploadLogs] = useState<string[]>([]);
  const [ytPublishImmediate, setYtPublishImmediate] = useState(true);
  const [ytScheduledTime, setYtScheduledTime] = useState("");

  // Instagram specific upload states
  const [igIsUploading, setIgIsUploading] = useState(false);
  const [igUploadJobId, setIgUploadJobId] = useState<string | null>(null);
  const [igUploadLogs, setIgUploadLogs] = useState<string[]>([]);
  const [igPublishImmediate, setIgPublishImmediate] = useState(true);
  const [igScheduledTime, setIgScheduledTime] = useState("");

  // Input states: Full talking presenter pipeline
  const [scriptPrompt, setScriptPrompt] = useState("Write a highly engaging 15-second script about a fascinating science fact.");
  const [ollamaModel, setOllamaModel] = useState("");
  const [voice, setVoice] = useState("Sarah (Female - US - Soft)");
  const [voiceSpeed, setVoiceSpeed] = useState(1.0);
  const [voiceEffect, setVoiceEffect] = useState("Normal");
  const [presenterPrompt, setPresenterPrompt] = useState("High quality vertical 9:16 portrait of a friendly talking presenter facing the camera, modern studio background, highly detailed face");
  const [leonardoModel, setLeonardoModel] = useState("Lucid Realism (High Quality Face)");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [lipsyncQuality, setLipsyncQuality] = useState("Enhanced");
  const [wav2lipVersion, setWav2lipVersion] = useState("Wav2Lip_GAN");
  const [noSmooth, setNoSmooth] = useState(true);
  const [padU, setPadU] = useState(0);
  const [padD, setPadD] = useState(10);
  const [padL, setPadL] = useState(0);
  const [padR, setPadR] = useState(0);
  const [bRollUrl, setBRollUrl] = useState("");
  const [compositeLayout, setCompositeLayout] = useState("None (Presenter Only)");

  // Input states: Manual lipsync
  const [manualImagePath, setManualImagePath] = useState("");
  const [manualAudioPath, setManualAudioPath] = useState("");
  const [manualQuality, setManualQuality] = useState("Enhanced");
  const [manualVersion, setManualVersion] = useState("Wav2Lip_GAN");
  const [manualNoSmooth, setManualNoSmooth] = useState(true);
  const [manualPadU, setManualPadU] = useState(0);
  const [manualPadD, setManualPadD] = useState(10);
  const [manualPadL, setManualPadL] = useState(0);
  const [manualPadR, setManualPadR] = useState(0);
  const [manualBRollUrl, setManualBRollUrl] = useState("");
  const [manualLayout, setManualLayout] = useState("None (Presenter Only)");

  // Input states: Landscape Studio
  const [longPrompt, setLongPrompt] = useState("Mariana Trench exploration and the mysterious creatures living at the bottom of the world");
  const [longOllamaModel, setLongOllamaModel] = useState("");
  const [longVoice, setLongVoice] = useState("Sarah (Female - US - Soft)");
  const [longVoiceSpeed, setLongVoiceSpeed] = useState(1.0);
  const [longMusicStyle, setLongMusicStyle] = useState("Cinematic");
  const [pexelsApiKey, setPexelsApiKey] = useState("");
  const [longCaptionSize, setLongCaptionSize] = useState(36);
  const [longCaptionMarginV, setLongCaptionMarginV] = useState(80);
  const [longCaptionColor, setLongCaptionColor] = useState("&H00FFFF&");
  const [longCaptionFont, setLongCaptionFont] = useState("Arial");
  const [longEnableTransitionSfx, setLongEnableTransitionSfx] = useState(true);
  const [longEnableCaptions, setLongEnableCaptions] = useState(true);

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
      
      // Fetch Instagram authentication status
      const igAuthRes = await fetch("http://localhost:8000/api/instagram/auth-status");
      if (igAuthRes.ok) {
        const igAuthData = await igAuthRes.json();
        setIsIgConfigured(igAuthData.configured);
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
      if (data.ollama_models.length > 0) {
        setOllamaModel(data.ollama_models[0]);
        setViralOllamaModel(data.ollama_models[0]);
        setLongOllamaModel(data.ollama_models[0]);
      }
      
      await refreshReadiness();
    } catch (err) {
      setBackendError("Could not connect to FastAPI backend on http://localhost:8000. Please start the backend server by running `.venv/bin/python backend.py`.");
    }
  };

  useEffect(() => {
    loadConfig();
    loadSchedulerData();
    const storedPexelsKey = localStorage.getItem("PEXELS_API_KEY");
    if (storedPexelsKey) {
      setPexelsApiKey(storedPexelsKey);
    }
  }, []);

  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const handleFetchTrends = async () => {
    setIsFetchingTrends(true);
    setTrendsError("");
    try {
      const res = await fetch(`http://localhost:8000/api/trends?geo=${trendsGeo}`);
      if (res.ok) {
        const data = await res.json();
        setTrends(data);
      } else {
        setTrendsError(`HTTP error! status: ${res.status}`);
      }
    } catch (e: any) {
      setTrendsError(`Connection failed: ${e.message || e}`);
    } finally {
      setIsFetchingTrends(false);
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

  const handlePexelsKeyChange = (val: string) => {
    setPexelsApiKey(val);
    localStorage.setItem("PEXELS_API_KEY", val);
  };

  const handleLongformDraft = async () => {
    setDrafting(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setStoryboard([]);
    setGenerationId(null);
    
    addLog("📝 Creating 5-Minute Long-Form Script & Storyboard Draft...");
    addLog(`Topic: "${longPrompt}"`);
    addLog(`Model: ${longOllamaModel}`);
    
    try {
      const response = await fetch("http://localhost:8000/api/longform/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: longPrompt,
          model: longOllamaModel || "minimax-m3:cloud"
        })
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      setGenerationId(result.generation_id);
      setStoryboard(result.storyboard);
      setGeneratedTopic(result.topic);
      
      // Pre-fill social upload metadata
      setUploadTitle(result.youtube_metadata?.title || result.topic || "");
      setUploadDescription(result.youtube_metadata?.description || "");
      setUploadTags(result.youtube_metadata?.tags?.join(", ") || "");
      setUploadCaption(result.instagram_metadata?.caption || "");
      
      addLog("✅ Landscape storyboard draft generated! Pexels video clips and scene texts are ready.");
    } catch (err: any) {
      addLog(`❌ ERROR drafting long-form script: ${err.message || err}`);
    } finally {
      setDrafting(false);
    }
  };

  const handleLongformRender = async () => {
    if (!generationId) return;
    setRendering(true);
    setLogs([]);
    setFinalVideoUrl(null);
    
    addLog("🚀 Starting Long-Form Video Render...");
    addLog(`Narration Voice: ${longVoice}`);
    addLog(`Background Music: ${longMusicStyle}`);
    
    try {
      const response = await fetch("http://localhost:8000/api/longform/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          generation_id: generationId,
          storyboard: storyboard,
          pexels_api_key: pexelsApiKey,
          voice: longVoice,
          speed: longVoiceSpeed,
          music_style: longMusicStyle,
          enable_captions: longEnableCaptions,
          caption_font: longCaptionFont,
          caption_size: longCaptionSize,
          caption_margin_v: longCaptionMarginV,
          caption_color: longCaptionColor,
          enable_transition_sfx: longEnableTransitionSfx
        })
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      addLog("⏳ Long-form rendering queued in the background. Polling render status...");
      setStatusText("Rendering...");
      
      // Poll rendering status
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch(`http://localhost:8000/api/generation-status/${generationId}`);
          if (statusRes.ok) {
            const data = await statusRes.json();
            if (data.status === "completed") {
              setFinalVideoUrl(data.video_url);
              setStoryboard(data.storyboard);
              setStatusText("Finished!");
              addLog("🎉 Success! Render complete. You can download or preview the final landscape video.");
              clearInterval(interval);
              setRendering(false);
              loadHistory(); // refresh library
            } else if (data.status === "failed") {
              setStatusText("Failed");
              addLog("❌ Video rendering failed on the server.");
              clearInterval(interval);
              setRendering(false);
            } else {
              addLog("Rendering long-form video in progress (downloading assets & editing clips)...");
            }
          }
        } catch (err) {
          console.error("Error polling render status:", err);
        }
      }, 5000);
      
      // Auto-clear after 20 minutes
      setTimeout(() => {
        clearInterval(interval);
        setRendering(false);
      }, 1200000);
      
    } catch (err: any) {
      addLog(`❌ ERROR starting long-form render: ${err.message || err}`);
      setRendering(false);
    }
  };

  const handleDraftStoryboard = async () => {
    setDrafting(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setStoryboard([]);
    setGenerationId(null);
    
    addLog("📝 Creating Script & Storyboard Draft...");
    addLog(`Topic: "${viralPrompt}"`);
    addLog(`Hook Style: ${viralHookStyle}`);
    
    try {
      const response = await fetch("http://localhost:8000/api/draft-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: viralPrompt,
          model: viralOllamaModel || "minimax-m3:cloud",
          hook_style: viralHookStyle,
          enable_search: enableSearch,
          voice: viralVoice
        })
      });
      
      if (!response.ok) {
        throw new Error(await response.text());
      }
      
      const result = await response.json();
      setGenerationId(result.generation_id);
      setStoryboard(result.storyboard);
      setGeneratedTopic(result.topic);
      
      // Pre-fill social upload metadata
      setUploadTitle(result.youtube_metadata?.title || result.topic || "");
      setUploadDescription(result.youtube_metadata?.description || "");
      setUploadTags(result.youtube_metadata?.tags?.join(", ") || "");
      setUploadCaption(result.instagram_metadata?.caption || "");
      
      addLog("✅ Script draft generated! Storyboard scenes are now ready for your edits.");
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
          caption_style: captionStyle
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
          setStoryboard([]);
          setGeneratedTopic("");
          setUploadTitle("");
          setUploadDescription("");
          setUploadTags("");
          setUploadCaption("");
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

  const loadSchedulerData = async () => {
    try {
      const resConfig = await fetch("http://localhost:8000/api/scheduler/config");
      if (resConfig.ok) {
        setSchedulerConfig(await resConfig.json());
      }
      const resLogs = await fetch("http://localhost:8000/api/scheduler/logs");
      if (resLogs.ok) {
        setSchedulerLogs(await resLogs.json());
      }
    } catch (err) {
      console.error("Error loading scheduler data:", err);
    }
  };

  const handleClearSchedulerLogs = async () => {
    if (!window.confirm("Are you sure you want to clear all scheduler execution logs? This action cannot be undone.")) {
      return;
    }
    try {
      const res = await fetch("http://localhost:8000/api/scheduler/logs", {
        method: "DELETE"
      });
      if (res.ok) {
        setSchedulerLogs([]);
        addLog("🗑️ Scheduler execution logs cleared successfully.");
      } else {
        alert("Failed to clear scheduler execution logs");
      }
    } catch (err) {
      console.error("Error clearing scheduler logs:", err);
    }
  };

  const saveSchedulerConfig = async (updatedConfig: any) => {
    try {
      const res = await fetch("http://localhost:8000/api/scheduler/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedConfig)
      });
      if (res.ok) {
        setSchedulerConfig(updatedConfig);
        addLog("💾 Scheduler settings updated successfully.");
      } else {
        alert("Failed to save scheduler configuration");
      }
    } catch (err) {
      console.error("Error saving scheduler config:", err);
      alert("Error saving settings");
    }
  };

  const triggerSchedulerAgent = async () => {
    setTriggerLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/scheduler/trigger", {
        method: "POST"
      });
      if (res.ok) {
        addLog("🚀 Manual Agent Run triggered in the background. Generating viral short...");
        setTimeout(loadSchedulerData, 2000);
      } else {
        alert("Failed to trigger agent");
      }
    } catch (err) {
      console.error("Error triggering agent:", err);
    } finally {
      setTriggerLoading(false);
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

  const handleGeneratePresenter = async () => {
    setLoading(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setPresenterImageUrl(null);
    setVoiceAudioUrl(null);
    
    addLog("🚀 Starting AI Presenter Full Pipeline...");
    
    try {
      // 1. Script
      setStatusText("Generating script...");
      addLog("Step 1/4: Generating script using Ollama...");
      const scriptRes = await fetch("http://localhost:8000/api/generate-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: scriptPrompt, model: ollamaModel })
      });
      if (!scriptRes.ok) throw new Error("Script generation failed");
      const scriptText = await scriptRes.json();
      addLog(`Script Generated: "${scriptText.substring(0, 80)}..."`);

      // 2. Speech
      setStatusText("Synthesizing voice...");
      addLog("Step 2/4: Synthesizing Kokoro-ONNX voice audio...");
      const speechRes = await fetch("http://localhost:8000/api/generate-speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: scriptText, voice: voice, speed: voiceSpeed, effect: voiceEffect })
      });
      if (!speechRes.ok) throw new Error("Speech synthesis failed");
      const speechData = await speechRes.json();
      setVoiceAudioUrl(speechData.url);
      setManualAudioPath(speechData.path); // Autofill manual path
      addLog(`Audio synthesized at: ${speechData.path}`);

      // 3. Image
      setStatusText("Generating presenter portrait...");
      addLog("Step 3/4: Submitting presenter image generation job to Leonardo.ai...");
      const presenterRes = await fetch("http://localhost:8000/api/generate-presenter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: presenterPrompt, model: leonardoModel, aspect_ratio: aspectRatio })
      });
      if (!presenterRes.ok) throw new Error("Presenter image generation failed");
      const presenterData = await presenterRes.json();
      setPresenterImageUrl(presenterData.url);
      setManualImagePath(presenterData.path); // Autofill manual path
      addLog(`Presenter image generated at: ${presenterData.path}`);

      // 4. Lipsync
      setStatusText("Processing lipsync...");
      addLog("Step 4/4: Executing Wav2Lip lipsync & compositing (FFmpeg)...");
      const lipsyncRes = await fetch("http://localhost:8000/api/run-lipsync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_path: presenterData.path,
          audio_path: presenterData.path,
          quality: lipsyncQuality,
          wav2lip_version: wav2lipVersion,
          nosmooth: noSmooth,
          padding_u: padU,
          padding_d: padD,
          padding_l: padL,
          padding_r: padR,
          b_roll_url: bRollUrl,
          layout: compositeLayout
        })
      });
      if (!lipsyncRes.ok) throw new Error("Lipsync process failed");
      const lipsyncData = await lipsyncRes.json();
      setFinalVideoUrl(lipsyncData.url);
      addLog(`Video render complete! Final path: ${lipsyncData.path}`);
      addLog("🎉 AI Talking Presenter generation completed successfully.");
      setStatusText("Finished!");
    } catch (err: any) {
      addLog(`❌ ERROR: ${err.message || err}`);
      setStatusText("Failed");
    } finally {
      setLoading(false);
    }
  };

  const handleManualLipsync = async () => {
    setLoading(true);
    setLogs([]);
    setFinalVideoUrl(null);
    addLog("🎬 Starting Manual Lipsync Job...");
    addLog(`Image: ${manualImagePath}`);
    addLog(`Audio: ${manualAudioPath}`);

    try {
      setStatusText("Lipsynching...");
      const response = await fetch("http://localhost:8000/api/run-lipsync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_path: manualImagePath,
          audio_path: manualAudioPath,
          quality: manualQuality,
          wav2lip_version: manualVersion,
          nosmooth: manualNoSmooth,
          padding_u: manualPadU,
          padding_d: manualPadD,
          padding_l: manualPadL,
          padding_r: manualPadR,
          b_roll_url: manualBRollUrl,
          layout: manualLayout
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Lipsync failed");
      }

      const data = await response.json();
      setFinalVideoUrl(data.url);
      addLog(`Manual Lipsync Succeeded! Output: ${data.path}`);
      setStatusText("Finished!");
    } catch (err: any) {
      addLog(`❌ ERROR: ${err.message || err}`);
      setStatusText("Failed");
    } finally {
      setLoading(false);
    }
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
        instagram_caption: "",
        scheduled_time: ytPublishImmediate ? null : (ytScheduledTime ? new Date(ytScheduledTime).toISOString() : null)
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
      
      const newLog = ytPublishImmediate ? "🚀 YouTube upload job queued immediately!" : `🕒 YouTube upload scheduled for: ${new Date(ytScheduledTime).toLocaleString()}`;
      setYtUploadLogs(prev => [...prev, newLog]);
      loadUploadQueue(); // refresh queue list
      
      if (ytPublishImmediate) {
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
      } else {
        setYtIsUploading(false);
      }
    } catch (error: any) {
      setYtUploadLogs(prev => [...prev, `❌ Error: ${error.message || error}`]);
      setYtIsUploading(false);
    }
  };

  const handleInstagramUpload = async () => {
    setIgIsUploading(true);
    setIgUploadLogs(["Initiating Instagram upload request..."]);
    
    try {
      const payload = {
        video_generation_id: generationId || "",
        platforms: ["instagram"],
        youtube_title: "",
        youtube_description: "",
        youtube_tags: [],
        youtube_privacy: "private",
        instagram_caption: uploadCaption,
        scheduled_time: igPublishImmediate ? null : (igScheduledTime ? new Date(igScheduledTime).toISOString() : null)
      };

      const res = await fetch("http://localhost:8000/api/schedule-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Instagram upload job queue failed");
      }

      const result = await res.json();
      setIgUploadJobId(result.job_id);
      
      const newLog = igPublishImmediate ? "🚀 Instagram upload job queued immediately!" : `🕒 Instagram upload scheduled for: ${new Date(igScheduledTime).toLocaleString()}`;
      setIgUploadLogs(prev => [...prev, newLog]);
      loadUploadQueue(); // refresh queue list
      
      if (igPublishImmediate) {
        // Poll job status
        const interval = setInterval(async () => {
          try {
            const statusRes = await fetch(`http://localhost:8000/api/upload-status/${result.job_id}`);
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              setIgUploadLogs(statusData.logs);
              
              if (statusData.status === "completed" || statusData.status === "failed") {
                setIgIsUploading(false);
                clearInterval(interval);
                loadUploadQueue();
              }
            }
          } catch (err) {
            console.error("Error polling Instagram upload status:", err);
          }
        }, 1500);

        setTimeout(() => {
          clearInterval(interval);
          setIgIsUploading(false);
        }, 300000);
      } else {
        setIgIsUploading(false);
      }
    } catch (error: any) {
      setIgUploadLogs(prev => [...prev, `❌ Error: ${error.message || error}`]);
      setIgIsUploading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <h1 className="title-glow">🎬 ShortsGen AI</h1>
        <p className="subtitle">Premium Talking Head & Viral Split-Screen Video Shorts Creator</p>
      </header>

      {/* Backend Status Alert */}
      {backendError && (
        <div className="glass-card" style={{ borderColor: "#ef4444", background: "rgba(239, 68, 68, 0.05)", display: "flex", gap: "12px", alignItems: "center" }}>
          <AlertCircle size={24} color="#ef4444" style={{ flexShrink: 0 }} />
          <div>
            <h4 style={{ color: "#ef4444", fontWeight: 600 }}>Backend Connection Offline</h4>
            <p className="form-label-info" style={{ color: "#fca5a5" }}>{backendError}</p>
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
            borderColor: "rgba(168, 85, 247, 0.15)",
            background: "rgba(168, 85, 247, 0.02)"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <Settings size={20} color="#a855f7" />
            <div>
              <h3 style={{ fontSize: "16px", fontWeight: 600, color: "#f8fafc", margin: 0 }}>Social Publishing Readiness</h3>
              <p style={{ fontSize: "12px", color: "#94a3b8", margin: "2px 0 0 0" }}>Check authorization status for direct video publishing to YouTube and Instagram.</p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
            {/* YouTube Readiness */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.05)", padding: "6px 12px", borderRadius: "10px" }}>
              <span style={{ fontSize: "13px", fontWeight: 500, color: "#cbd5e1" }}>YouTube Shorts:</span>
              {isYtAuthenticated ? (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#10b981", fontSize: "13px", fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Ready
                </span>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#ef4444", fontSize: "13px", fontWeight: 600 }}>
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

            {/* Instagram Readiness */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.05)", padding: "6px 12px", borderRadius: "10px" }}>
              <span style={{ fontSize: "13px", fontWeight: 500, color: "#cbd5e1" }}>Instagram Reels:</span>
              {isIgConfigured ? (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#10b981", fontSize: "13px", fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Ready
                </span>
              ) : (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#eab308", fontSize: "13px", fontWeight: 600 }} title="Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN in .env">
                  <AlertCircle size={14} /> Needs Keys
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
          onClick={() => setActiveTab("full")} 
          className={`tab-btn ${activeTab === "full" ? "tab-btn-active" : ""}`}
        >
          <Tv size={18} /> 🚀 Full Presenter Pipeline
        </button>
        <button 
          onClick={() => setActiveTab("manual")} 
          className={`tab-btn ${activeTab === "manual" ? "tab-btn-active" : ""}`}
        >
          <Sliders size={18} /> 🎬 Manual Lipsync Studio
        </button>
        <button 
          onClick={() => setActiveTab("longform")} 
          className={`tab-btn ${activeTab === "longform" ? "tab-btn-active" : ""}`}
        >
          <Tv size={18} /> 🖥️ Landscape Studio
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
        <button 
          onClick={() => { setActiveTab("scheduler"); loadSchedulerData(); }} 
          className={`tab-btn ${activeTab === "scheduler" ? "tab-btn-active" : ""}`}
        >
          <Settings size={18} /> 🤖 Auto-Agent Scheduler
        </button>
      </div>

      {/* Main Grid Panels / Full Screens */}
      {activeTab !== "library" && activeTab !== "queue" && activeTab !== "scheduler" ? (
        <div className="dashboard-grid">
          {/* Left Side: Forms */}
          <div className="form-panel">
          
          {/* TAB 1: VIRAL SHORTS STUDIO */}
          {activeTab === "viral" && (
            <>
              {/* Trending Topics Discoverer */}
              <div className="glass-card" style={{ marginBottom: "20px" }}>
                <h2 className="card-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "1.2em" }}>🔥</span> Discover Trending Topics
                  </span>
                  <span className="badge" style={{ background: "#ef4444", fontSize: "0.75rem", padding: "2px 8px" }}>Real-time</span>
                </h2>
                
                <p className="card-subtitle" style={{ color: "#94a3b8", fontSize: "0.9rem", marginBottom: "15px" }}>
                  Find out what people are searching for right now and instantly generate viral shorts about them.
                </p>

                <div className="form-row" style={{ alignItems: "flex-end", marginBottom: "20px" }}>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label">Select Target Region</label>
                    <select 
                      className="form-select"
                      value={trendsGeo}
                      onChange={(e) => setTrendsGeo(e.target.value)}
                    >
                      <option value="IN">India (IN)</option>
                      <option value="US">United States (US)</option>
                      <option value="GB">United Kingdom (GB)</option>
                      <option value="CA">Canada (CA)</option>
                      <option value="AU">Australia (AU)</option>
                    </select>
                  </div>
                  <button 
                    className="btn btn-primary" 
                    onClick={handleFetchTrends}
                    disabled={isFetchingTrends}
                    style={{ height: "42px", minWidth: "150px" }}
                  >
                    {isFetchingTrends ? "Fetching..." : "Fetch Hot Trends"}
                  </button>
                </div>

                {trendsError && (
                  <p style={{ color: "#ef4444", fontSize: "0.9rem", marginBottom: "15px" }}>{trendsError}</p>
                )}

                {trends.length > 0 && (
                  <div 
                    style={{ 
                      display: "grid", 
                      gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", 
                      gap: "15px", 
                      maxHeight: "350px", 
                      overflowY: "auto", 
                      paddingRight: "5px",
                      marginTop: "10px"
                    }}
                  >
                    {trends.map((t, idx) => (
                      <div 
                        key={idx} 
                        style={{ 
                          background: "#0f172a", 
                          borderRadius: "8px", 
                          padding: "12px", 
                          border: "1px solid #334155", 
                          display: "flex", 
                          flexDirection: "column",
                          justifyContent: "space-between",
                          transition: "all 0.2s ease"
                        }}
                        className="trend-card"
                      >
                        <div>
                          {t.picture_url ? (
                            <img 
                              src={t.picture_url} 
                              alt={t.title} 
                              style={{ width: "100%", height: "110px", objectFit: "cover", borderRadius: "6px", marginBottom: "10px" }}
                            />
                          ) : (
                            <div style={{ height: "110px", background: "#1e293b", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: "0.85rem", marginBottom: "10px" }}>
                              No Thumbnail
                            </div>
                          )}
                          <h4 style={{ margin: "0 0 4px 0", color: "#f1f5f9", fontSize: "1rem" }}>{t.title}</h4>
                          <span style={{ background: "#ef4444", color: "#ffffff", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold" }}>
                            🔥 {t.traffic}
                          </span>
                          
                          {t.news_title && (
                            <p style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "8px", lineHeight: "1.25" }}>
                              <b>News</b>: <a href={t.news_url} target="_blank" rel="noopener noreferrer" style={{ color: "#c084fc", textDecoration: "none" }}>{t.news_title}</a>
                            </p>
                          )}
                        </div>
                        
                        <button 
                          className="btn btn-secondary" 
                          style={{ width: "100%", marginTop: "12px", padding: "6px 0", fontSize: "0.85rem" }}
                          onClick={() => {
                            setViralPrompt(`Write a script about: ${t.title}. Context: ${t.news_title || ""}`);
                            setEnableSearch(true);
                            const configSection = document.getElementById("viral-config-card");
                            if (configSection) {
                              configSection.scrollIntoView({ behavior: "smooth" });
                            }
                          }}
                        >
                          Create Reel
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

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
                      <span style={{ fontSize: "12px", fontWeight: 600, color: "#d8b4fe" }}>🔍 Fact-Check with Internet Search (RAG)</span>
                    </label>
                  </div>
                </div>

                <button 
                  onClick={handleDraftStoryboard}
                  disabled={drafting || !config} 
                  className="btn btn-primary"
                  style={{ marginTop: "15px", background: "linear-gradient(135deg, #a855f7 0%, #7c3aed 100%)" }}
                >
                  📝 {drafting ? "Drafting Storyboard..." : "Draft Script & Storyboard"}
                </button>
              </div>

              <div className="glass-card" style={{ marginTop: "20px" }}>
                <h2 className="card-title"><Tv /> Video Style & Rendering Settings</h2>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Visual Format Mode</label>
                    <select 
                      className="form-select"
                      value={visualMode}
                      onChange={(e) => setVisualMode(e.target.value)}
                    >
                      <option value="Cinematic Slideshow">Cinematic Slideshow (Pan & Zoom)</option>
                      <option value="Leonardo Motion Video">Leonardo Motion (Image-to-Video API)</option>
                    </select>
                  </div>
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
                    <span style={{ fontSize: "14px", fontWeight: 600 }}>Enable Transition Sound Effects (Whoosh & Pop)</span>
                  </label>
                  <p className="form-label-info" style={{ marginLeft: "30px", marginTop: "4px" }}>Adds satisfying audio sweeps at scene switches.</p>
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
                        <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span>Text Size</span>
                          <span style={{ color: "#c084fc", fontWeight: 600 }}>{captionSize}px</span>
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
                          <span style={{ color: "#c084fc", fontWeight: 600 }}>{captionMarginV}px</span>
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
                                  background: isSelected ? "rgba(168, 85, 247, 0.25)" : "rgba(255,255,255,0.03)",
                                  border: `1px solid ${isSelected ? "#a855f7" : "rgba(255,255,255,0.08)"}`,
                                  borderRadius: "20px",
                                  padding: "6px 12px",
                                  cursor: enableCaptions ? "pointer" : "not-allowed",
                                  color: isSelected ? "#f8fafc" : "#94a3b8",
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
                          border: "2px solid rgba(168, 85, 247, 0.3)",
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

                <button 
                  onClick={handleRenderStoryboard}
                  disabled={rendering || !config || storyboard.length === 0} 
                  className="btn btn-primary"
                  style={{ 
                    marginTop: "20px",
                    background: "linear-gradient(135deg, #ec4899 0%, #f43f5e 100%)",
                    boxShadow: "0 4px 15px rgba(244, 63, 94, 0.2)" 
                  }}
                >
                  🎬 {rendering ? "Rendering Video..." : "Compile & Render Video"}
                </button>
                {storyboard.length === 0 && (
                  <p className="form-label-info" style={{ color: "#fca5a5", marginTop: "8px", textAlign: "center" }}>
                    ⚠️ Please draft a script and storyboard above first to enable video rendering.
                  </p>
                )}
              </div>
            </>
          )}

          {/* TAB 2: FULL PRESENTER PIPELINE */}
          {activeTab === "full" && (
            <div className="glass-card">
              <h2 className="card-title"><Tv /> Presenter Pipeline Settings</h2>
              
              <div className="form-group">
                <label className="form-label">Script Topic / Prompt (Ollama)</label>
                <textarea 
                  className="form-textarea" 
                  rows={2}
                  value={scriptPrompt}
                  onChange={(e) => setScriptPrompt(e.target.value)}
                  placeholder="Ask Ollama to write a custom monologue script..."
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Ollama Model</label>
                  <select 
                    className="form-select"
                    value={ollamaModel}
                    onChange={(e) => setOllamaModel(e.target.value)}
                  >
                    {config?.ollama_models.map(m => (
                      <option key={m} value={m}>{m}</option>
                    )) || <option>Loading...</option>}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Narrator Voice</label>
                  <select 
                    className="form-select"
                    value={voice}
                    onChange={(e) => setVoice(e.target.value)}
                  >
                    {config?.voices.map(v => (
                      <option key={v} value={v}>{v}</option>
                    )) || <option>Loading...</option>}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Speech Speed ({voiceSpeed}x)</label>
                  <input 
                    type="range" min="0.5" max="2.0" step="0.1" className="form-input"
                    value={voiceSpeed} onChange={(e) => setVoiceSpeed(parseFloat(e.target.value))}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Voice Pitch Effect</label>
                  <select className="form-select" value={voiceEffect} onChange={(e) => setVoiceEffect(e.target.value)}>
                    <option value="Normal">Normal</option>
                    <option value="Kid (High Pitch)">Kid (High Pitch)</option>
                    <option value="Deep (Low Pitch)">Deep (Low Pitch)</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Visual Portrait Prompt (Leonardo.ai)</label>
                <textarea 
                  className="form-textarea" 
                  rows={2}
                  value={presenterPrompt}
                  onChange={(e) => setPresenterPrompt(e.target.value)}
                  placeholder="Describe your talking presenter face, outfit, and background..."
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Leonardo Model</label>
                  <select className="form-select" value={leonardoModel} onChange={(e) => setLeonardoModel(e.target.value)}>
                    {config?.leonardo_models.map(m => (
                      <option key={m} value={m}>{m}</option>
                    )) || <option>Loading...</option>}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Aspect Ratio</label>
                  <select className="form-select" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
                    {config?.aspect_ratios.map(ar => (
                      <option key={ar} value={ar}>{ar}</option>
                    )) || <option>Loading...</option>}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Wav2Lip Quality</label>
                  <select className="form-select" value={lipsyncQuality} onChange={(e) => setLipsyncQuality(e.target.value)}>
                    <option value="Fast">Fast</option>
                    <option value="Improved">Improved</option>
                    <option value="Enhanced">Enhanced</option>
                  </select>
                </div>
                <div className="form-group" style={{ display: "flex", alignItems: "center" }}>
                  <label className="checkbox-container">
                    <input type="checkbox" checked={noSmooth} onChange={(e) => setNoSmooth(e.target.checked)} />
                    <div className="checkbox-custom"></div>
                    <span style={{ fontSize: "14px" }}>Disable Lip Smoothing (nosmooth)</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Compositing B-Roll Layout</label>
                <select className="form-select" value={compositeLayout} onChange={(e) => setCompositeLayout(e.target.value)}>
                  <option value="None (Presenter Only)">None (Presenter Only)</option>
                  <option value="Split-Screen (Top B-Roll, Bottom Presenter)">Split-Screen (Top B-Roll, Bottom Presenter)</option>
                  <option value="Picture-in-Picture (Presenter Bottom Right)">Picture-in-Picture (Presenter Bottom Right)</option>
                  <option value="Green Screen (Chroma Key Presenter on B-Roll)">Green Screen (Chroma Key Presenter on B-Roll)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">B-Roll Video Direct URL (Optional)</label>
                <input 
                  type="text" className="form-input" value={bRollUrl} 
                  onChange={(e) => setBRollUrl(e.target.value)} 
                  placeholder="Direct MP4 video URL (e.g. from Pexels)..."
                />
              </div>

              <button 
                onClick={handleGeneratePresenter} 
                disabled={loading || !config} 
                className="btn btn-primary"
              >
                <Play size={18} /> {loading ? "Generating Presenter Video..." : "Run Talking Head Pipeline"}
              </button>
            </div>
          )}

          {/* TAB 3: MANUAL LIPSYNC STUDIO */}
          {activeTab === "manual" && (
            <div className="glass-card">
              <h2 className="card-title"><Sliders /> Manual Lipsync Tools</h2>
              
              <div className="form-group">
                <label className="form-label">Presenter Image File Path (Absolute Local Path)</label>
                <input 
                  type="text" className="form-input" value={manualImagePath}
                  onChange={(e) => setManualImagePath(e.target.value)}
                  placeholder="Paste absolute path (e.g. /Volumes/.../presenter.png)"
                />
                <p className="form-label-info">If you generated an image in the pipeline tab, it auto-fills here.</p>
              </div>

              <div className="form-group">
                <label className="form-label">Vocal Audio File Path (Absolute Local Path)</label>
                <input 
                  type="text" className="form-input" value={manualAudioPath}
                  onChange={(e) => setManualAudioPath(e.target.value)}
                  placeholder="Paste absolute path (e.g. /Volumes/.../speech.wav)"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Wav2Lip Model</label>
                  <select className="form-select" value={manualVersion} onChange={(e) => setManualVersion(e.target.value)}>
                    <option value="Wav2Lip_GAN">Wav2Lip_GAN</option>
                    <option value="Wav2Lip">Wav2Lip</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Quality Mode</label>
                  <select className="form-select" value={manualQuality} onChange={(e) => setManualQuality(e.target.value)}>
                    <option value="Fast">Fast</option>
                    <option value="Improved">Improved</option>
                    <option value="Enhanced">Enhanced</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Background / B-Roll Video URL (Optional)</label>
                <input 
                  type="text" className="form-input" value={manualBRollUrl}
                  onChange={(e) => setManualBRollUrl(e.target.value)}
                  placeholder="Direct video link..."
                />
              </div>

              <div className="form-group">
                <label className="form-label">B-Roll Composite Layout</label>
                <select className="form-select" value={manualLayout} onChange={(e) => setManualLayout(e.target.value)}>
                  <option value="None (Presenter Only)">None (Presenter Only)</option>
                  <option value="Split-Screen (Top B-Roll, Bottom Presenter)">Split-Screen (Top B-Roll, Bottom Presenter)</option>
                  <option value="Picture-in-Picture (Presenter Bottom Right)">Picture-in-Picture (Presenter Bottom Right)</option>
                  <option value="Green Screen (Chroma Key Presenter on B-Roll)">Green Screen (Chroma Key Presenter on B-Roll)</option>
                </select>
              </div>

              <button 
                onClick={handleManualLipsync} 
                disabled={loading || !config} 
                className="btn btn-primary"
              >
                <Play size={18} /> {loading ? "Lipsynching..." : "Sync Audio with Portrait"}
              </button>
            </div>
          )}

          {/* TAB 4: LONG-FORM LANDSCAPE STUDIO */}
          {activeTab === "longform" && (
            <>
              <div className="glass-card">
                <h2 className="card-title"><Sparkles /> Landscape Script Configuration</h2>
                
                <div className="form-group">
                  <label className="form-label">Video Topic or Category Prompt</label>
                  <textarea 
                    className="form-textarea" 
                    rows={2}
                    value={longPrompt}
                    onChange={(e) => setLongPrompt(e.target.value)}
                    placeholder="Describe your video topic... (e.g. quantum physics facts, dark history of ancient cities)"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Ollama LLM Model</label>
                    <select 
                      className="form-select"
                      value={longOllamaModel}
                      onChange={(e) => setLongOllamaModel(e.target.value)}
                    >
                      {config?.ollama_models.map(m => (
                        <option key={m} value={m}>{m}</option>
                      )) || <option>Loading...</option>}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Pexels API Key</label>
                    <input 
                      type="password" 
                      className="form-input"
                      value={pexelsApiKey}
                      onChange={(e) => handlePexelsKeyChange(e.target.value)}
                      placeholder="Enter Pexels API Key..."
                    />
                    <p className="form-label-info">Saved locally in your browser's localStorage.</p>
                  </div>
                </div>

                <button 
                  onClick={handleLongformDraft}
                  disabled={drafting || !config} 
                  className="btn btn-primary"
                  style={{ marginTop: "15px", background: "linear-gradient(135deg, #a855f7 0%, #7c3aed 100%)" }}
                >
                  📝 {drafting ? "Drafting Landscape Storyboard..." : "Draft Landscape Script & Storyboard"}
                </button>
              </div>

              <div className="glass-card" style={{ marginTop: "20px" }}>
                <h2 className="card-title"><Tv /> Video Style & Rendering Settings</h2>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Visual Format Mode</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      value="Pexels Stock Video (Landscape 16:9)" 
                      disabled 
                      style={{ opacity: 0.8 }}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Background Music</label>
                    <select 
                      className="form-select"
                      value={longMusicStyle}
                      onChange={(e) => setLongMusicStyle(e.target.value)}
                    >
                      {config?.music_presets.map(m => (
                        <option key={m} value={m}>{m}</option>
                      )) || <option>Loading...</option>}
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Voice Narrator</label>
                    <select 
                      className="form-select"
                      value={longVoice}
                      onChange={(e) => {
                        const newVoice = e.target.value;
                        setLongVoice(newVoice);
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
                    <label className="form-label">Voice Speed ({longVoiceSpeed}x)</label>
                    <input 
                      type="range" 
                      min="0.5" 
                      max="2.0" 
                      step="0.1"
                      className="form-input" 
                      value={longVoiceSpeed}
                      onChange={(e) => setLongVoiceSpeed(parseFloat(e.target.value))}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: "12px", marginBottom: "12px" }}>
                  <label className="checkbox-container" style={{ margin: 0 }}>
                    <input 
                      type="checkbox" 
                      checked={longEnableTransitionSfx}
                      onChange={(e) => setLongEnableTransitionSfx(e.target.checked)}
                    />
                    <div className="checkbox-custom"></div>
                    <span style={{ fontSize: "14px", fontWeight: 600 }}>Enable Transition Sound Effects (Whoosh & Pop)</span>
                  </label>
                </div>

                <div className="form-group" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "15px" }}>
                  <label className="form-label"><Subtitles size={16} style={{ display: "inline", marginRight: "6px" }} /> Auto-Caption & Position Settings</label>
                  
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "20px", marginTop: "12px" }}>
                    <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: "16px" }}>
                      <label className="checkbox-container" style={{ margin: 0 }}>
                        <input 
                          type="checkbox" 
                          checked={longEnableCaptions}
                          onChange={(e) => setLongEnableCaptions(e.target.checked)}
                        />
                        <div className="checkbox-custom"></div>
                        <span style={{ fontSize: "14px", fontWeight: 600 }}>Burn Centered Word Subtitles</span>
                      </label>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span>Text Size</span>
                          <span style={{ color: "#c084fc", fontWeight: 600 }}>{longCaptionSize}px</span>
                        </label>
                        <div className="slider-group">
                          <input 
                            type="range" 
                            min="18" 
                            max="72" 
                            value={longCaptionSize} 
                            onChange={(e) => setLongCaptionSize(parseInt(e.target.value))}
                            style={{ flexGrow: 1, padding: 0, height: "6px", background: "rgba(255,255,255,0.1)", borderRadius: "3px", cursor: "pointer" }}
                            disabled={!longEnableCaptions}
                          />
                        </div>
                      </div>

                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span>Vertical Position (from bottom)</span>
                          <span style={{ color: "#c084fc", fontWeight: 600 }}>{longCaptionMarginV}px</span>
                        </label>
                        <div className="slider-group">
                          <input 
                            type="range" 
                            min="20" 
                            max="300" 
                            value={longCaptionMarginV} 
                            onChange={(e) => setLongCaptionMarginV(parseInt(e.target.value))}
                            style={{ flexGrow: 1, padding: 0, height: "6px", background: "rgba(255,255,255,0.1)", borderRadius: "3px", cursor: "pointer" }}
                            disabled={!longEnableCaptions}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <button 
                  onClick={handleLongformRender}
                  disabled={rendering || !config || storyboard.length === 0} 
                  className="btn btn-primary"
                  style={{ 
                    marginTop: "20px",
                    background: "linear-gradient(135deg, #ec4899 0%, #f43f5e 100%)",
                    boxShadow: "0 4px 15px rgba(244, 63, 94, 0.2)" 
                  }}
                >
                  🎬 {rendering ? "Rendering Long-form Video..." : "Compile & Render Long-form Video"}
                </button>
                {storyboard.length === 0 && (
                  <p className="form-label-info" style={{ color: "#fca5a5", marginTop: "8px", textAlign: "center" }}>
                    ⚠️ Please draft a script and storyboard above first to enable video rendering.
                  </p>
                )}
              </div>
            </>
          )}

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
                    color: statusText === "Finished!" ? "#10b981" : statusText === "Failed" ? "#ef4444" : "#a855f7",
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
                <div className="video-container" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#05040a" }}>
                  <div className="loader-glow"></div>
                  <h4 style={{ color: "#a855f7", fontWeight: 700 }}>Processing AI pipeline...</h4>
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
                <div className="video-container" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#06050e", opacity: 0.8 }}>
                  <Tv size={48} color="#475569" style={{ marginBottom: "15px" }} />
                  <p style={{ color: "#64748b", fontSize: "14px", fontWeight: 500 }}>No video generated yet.</p>
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
            </div>

            {/* Social Media Publish Section */}
            {finalVideoUrl && !loading && (
              <div className="glass-card" style={{ padding: "18px", border: "1px solid rgba(168, 85, 247, 0.2)", marginTop: "15px" }}>
                <h3 className="card-title" style={{ fontSize: "18px", display: "flex", gap: "8px", alignItems: "center", color: "#c084fc", margin: "0 0 10px 0" }}>
                  <Sparkles size={18} /> Publish to Social Media
                </h3>
                <p className="form-label-info" style={{ marginBottom: "15px" }}>
                  Publish this generated short directly to YouTube Shorts and Instagram Reels.
                </p>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "15px", marginBottom: 0 }}>
                  
                  {/* YouTube Shorts Section */}
                  <div style={{ background: "rgba(255,255,255,0.02)", padding: "15px", borderRadius: "8px", border: "1px solid rgba(239, 68, 68, 0.15)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "8px" }}>
                      <label className="checkbox-container" style={{ margin: 0, display: "flex", alignItems: "center", cursor: "pointer" }}>
                        <input 
                          type="checkbox" 
                          checked={uploadPlatforms.youtube}
                          onChange={(e) => setUploadPlatforms({ ...uploadPlatforms, youtube: e.target.checked })}
                          style={{ marginRight: "8px" }}
                        />
                        <span style={{ fontSize: "15px", fontWeight: 600, color: "#f87171" }}>YouTube Shorts</span>
                      </label>
                      {isYtAuthenticated ? (
                        <span style={{ fontSize: "11px", color: "#10b981", fontWeight: 700 }}>Connected ✅</span>
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

                    {uploadPlatforms.youtube ? (
                      <div>
                        <div className="form-group" style={{ marginBottom: "10px" }}>
                          <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Shorts Title (Catchy, max 100 chars)</label>
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
                          <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Shorts Description</label>
                          <textarea 
                            className="form-textarea" 
                            rows={3}
                            value={uploadDescription}
                            onChange={(e) => setUploadDescription(e.target.value)}
                            placeholder="Tell viewers what your short is about..."
                          />
                        </div>

                        <div className="form-row" style={{ gap: "10px", marginBottom: 0 }}>
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

                        {/* Scheduling UI inside YouTube Section */}
                        <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px", borderRadius: "6px", margin: "12px 0 10px 0", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <span style={{ color: "#f87171", fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "6px", textTransform: "uppercase" }}>Scheduling</span>
                          <div style={{ display: "flex", gap: "15px", marginBottom: "6px" }}>
                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="yt_publish_time_opt"
                                checked={ytPublishImmediate}
                                onChange={() => setYtPublishImmediate(true)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "#cbd5e1" }}>Immediate</span>
                            </label>

                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="yt_publish_time_opt"
                                checked={!ytPublishImmediate}
                                onChange={() => setYtPublishImmediate(false)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "#cbd5e1" }}>Later</span>
                            </label>
                          </div>

                          {!ytPublishImmediate && (
                            <input 
                              type="datetime-local" 
                              className="form-input" 
                              value={ytScheduledTime}
                              onChange={(e) => setYtScheduledTime(e.target.value)}
                              style={{ height: "32px", fontSize: "12px", padding: "4px 8px", marginTop: "4px", colorScheme: "dark" }}
                            />
                          )}
                        </div>

                        {/* YouTube Publish Button */}
                        <button 
                          onClick={handleYoutubeUpload}
                          disabled={ytIsUploading}
                          className="btn btn-primary"
                          style={{ 
                            background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
                            boxShadow: "0 4px 12px rgba(239, 68, 68, 0.2)",
                            marginTop: "5px",
                            padding: "8px 12px",
                            fontSize: "13px",
                            width: "100%"
                          }}
                        >
                          🚀 {ytIsUploading ? "Uploading..." : (ytPublishImmediate ? "Publish to YouTube Now" : "Schedule to YouTube")}
                        </button>

                        {/* YouTube logs console */}
                        {(ytIsUploading || ytUploadLogs.length > 0) && (
                          <div style={{ marginTop: "12px" }}>
                            <span className="form-label" style={{ fontSize: "10px", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>YouTube Progress Logs</span>
                            <div className="log-console" style={{ height: "90px", fontSize: "11px", overflowY: "auto", padding: "6px" }}>
                              {ytUploadLogs.map((log, i) => (
                                <div key={i} style={{ color: log.startsWith("❌") ? "#ef4444" : log.startsWith("✅") || log.includes("successful") ? "#10b981" : "#e2e8f0", marginBottom: "2px" }}>{log}</div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p style={{ fontSize: "12px", color: "#64748b", margin: "10px 0 0 0" }}>Check the box above to enable YouTube Shorts publishing configuration.</p>
                    )}
                  </div>

                  {/* Instagram Reels Section */}
                  <div style={{ background: "rgba(255,255,255,0.02)", padding: "15px", borderRadius: "8px", border: "1px solid rgba(236, 72, 153, 0.15)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "8px" }}>
                      <label className="checkbox-container" style={{ margin: 0, display: "flex", alignItems: "center", cursor: "pointer" }}>
                        <input 
                          type="checkbox" 
                          checked={uploadPlatforms.instagram}
                          onChange={(e) => setUploadPlatforms({ ...uploadPlatforms, instagram: e.target.checked })}
                          style={{ marginRight: "8px" }}
                        />
                        <span style={{ fontSize: "15px", fontWeight: 600, color: "#f472b6" }}>Instagram Reels</span>
                      </label>
                      {isIgConfigured ? (
                        <span style={{ fontSize: "11px", color: "#10b981", fontWeight: 700 }}>Ready ✅</span>
                      ) : (
                        <span style={{ fontSize: "11px", color: "#eab308", fontWeight: 700 }}>Not Configured ⚠️</span>
                      )}
                    </div>

                    {uploadPlatforms.instagram ? (
                      <div>
                        <div className="form-group" style={{ marginBottom: "10px" }}>
                          <label className="form-label" style={{ fontSize: "12px", marginBottom: "4px" }}>Reels Caption & Hashtags</label>
                          <textarea 
                            className="form-textarea" 
                            rows={4}
                            value={uploadCaption}
                            onChange={(e) => setUploadCaption(e.target.value)}
                            placeholder="Write caption... #reels #explore"
                          />
                        </div>

                        {/* Scheduling UI inside Instagram Section */}
                        <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px", borderRadius: "6px", margin: "12px 0 10px 0", border: "1px solid rgba(255,255,255,0.03)" }}>
                          <span style={{ color: "#f472b6", fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "6px", textTransform: "uppercase" }}>Scheduling</span>
                          <div style={{ display: "flex", gap: "15px", marginBottom: "6px" }}>
                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="ig_publish_time_opt"
                                checked={igPublishImmediate}
                                onChange={() => setIgPublishImmediate(true)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "#cbd5e1" }}>Immediate</span>
                            </label>

                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="ig_publish_time_opt"
                                checked={!igPublishImmediate}
                                onChange={() => setIgPublishImmediate(false)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "#cbd5e1" }}>Later</span>
                            </label>
                          </div>

                          {!igPublishImmediate && (
                            <input 
                              type="datetime-local" 
                              className="form-input" 
                              value={igScheduledTime}
                              onChange={(e) => setIgScheduledTime(e.target.value)}
                              style={{ height: "32px", fontSize: "12px", padding: "4px 8px", marginTop: "4px", colorScheme: "dark" }}
                            />
                          )}
                        </div>

                        {/* Instagram Publish Button */}
                        <button 
                          onClick={handleInstagramUpload}
                          disabled={igIsUploading}
                          className="btn btn-primary"
                          style={{ 
                            background: "linear-gradient(135deg, #ec4899 0%, #db2777 100%)",
                            boxShadow: "0 4px 12px rgba(236, 72, 153, 0.2)",
                            marginTop: "5px",
                            padding: "8px 12px",
                            fontSize: "13px",
                            width: "100%"
                          }}
                        >
                          🚀 {igIsUploading ? "Uploading..." : (igPublishImmediate ? "Publish to Instagram Now" : "Schedule to Instagram")}
                        </button>

                        {/* Instagram logs console */}
                        {(igIsUploading || igUploadLogs.length > 0) && (
                          <div style={{ marginTop: "12px" }}>
                            <span className="form-label" style={{ fontSize: "10px", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>Instagram Progress Logs</span>
                            <div className="log-console" style={{ height: "90px", fontSize: "11px", overflowY: "auto", padding: "6px" }}>
                              {igUploadLogs.map((log, i) => (
                                <div key={i} style={{ color: log.startsWith("❌") ? "#ef4444" : log.startsWith("✅") || log.includes("successful") ? "#10b981" : "#e2e8f0", marginBottom: "2px" }}>{log}</div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p style={{ fontSize: "12px", color: "#64748b", margin: "10px 0 0 0" }}>Check the box above to enable Instagram Reels publishing configuration.</p>
                    )}
                  </div>

                </div>
              </div>
            )}

            {/* Intermediate Assets (Only for Talking Head) */}
            {activeTab === "full" && (presenterImageUrl || voiceAudioUrl) && (
              <div className="glass-card" style={{ padding: "18px" }}>
                <h3 className="card-title" style={{ fontSize: "16px", marginBottom: "12px" }}>Pipeline Assets</h3>
                <div style={{ display: "flex", gap: "15px", alignItems: "center" }}>
                  {presenterImageUrl && (
                    <div style={{ flexShrink: 0 }}>
                      <img src={presenterImageUrl} className="img-preview" style={{ height: "120px", width: "70px", margin: 0 }} alt="Presenter Asset" />
                    </div>
                  )}
                  {voiceAudioUrl && (
                    <div style={{ flexGrow: 1 }}>
                      <label className="form-label" style={{ fontSize: "12px" }}><Volume2 size={12} style={{ display: "inline" }} /> Voice Audio</label>
                      <audio key={voiceAudioUrl} controls className="audio-preview" style={{ height: "30px", marginTop: "4px" }}>
                        <source src={voiceAudioUrl} type="audio/wav" />
                      </audio>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Log Console */}
            <div className="glass-card" style={{ padding: "18px" }}>
              <h3 className="card-title" style={{ fontSize: "16px", marginBottom: "8px" }}><FileText size={16} /> Console Execution Logs</h3>
              <div className="log-console">
                {logs.length === 0 ? (
                  <div className="log-entry" style={{ color: "#475569" }}>Waiting to run a generation job...</div>
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
                  <p style={{ color: "#94a3b8", fontSize: "13px", marginTop: "4px" }}>
                    Browse your database of previously generated video shorts, drafts, and talking head presentations.
                  </p>
                </div>
                <button onClick={loadHistory} className="btn btn-secondary" style={{ width: "auto", margin: 0, padding: "8px 16px" }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              <div className="library-grid">
                {history.length === 0 ? (
                  <div style={{ gridColumn: "1/-1", textAlign: "center", padding: "60px 20px", color: "#64748b" }}>
                    <Tv size={48} style={{ marginBottom: "15px", opacity: 0.3 }} />
                    <p style={{ fontSize: "15px", fontWeight: 500 }}>No video history found.</p>
                    <p style={{ fontSize: "12px", color: "#475569", marginTop: "4px" }}>Start generating shorts to build your video library.</p>
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
                            background: item.status === "completed" ? "rgba(16, 185, 129, 0.1)" : item.status === "draft" ? "rgba(168, 85, 247, 0.1)" : "rgba(239, 68, 68, 0.1)",
                            color: item.status === "completed" ? "#10b981" : item.status === "draft" ? "#c084fc" : "#ef4444",
                            border: `1px solid ${item.status === "completed" ? "rgba(16, 185, 129, 0.2)" : item.status === "draft" ? "rgba(168, 85, 247, 0.2)" : "rgba(239, 68, 68, 0.2)"}`
                          }}>
                            {item.status}
                          </span>
                          <span style={{ fontSize: "11px", color: "#64748b" }}>
                            {new Date(item.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        
                        <h4 style={{ color: "#f8fafc", fontSize: "15px", fontWeight: 600, margin: "0 0 8px 0", lineHeight: "1.4" }}>
                          {item.topic || item.prompt || "Untitled Short"}
                        </h4>
                        
                        {item.status === "completed" && item.video_url && (
                          <div className="video-container" style={{ minHeight: "150px", background: "#06050e", borderRadius: "8px", overflow: "hidden", margin: "10px 0" }}>
                            <video src={item.video_url} controls style={{ width: "100%", maxHeight: "200px" }} />
                          </div>
                        )}
                        
                        {item.status === "draft" && (
                          <div style={{ padding: "12px", background: "rgba(255,255,255,0.02)", borderRadius: "8px", border: "1px dashed rgba(255,255,255,0.05)", margin: "10px 0", textAlign: "center", color: "#94a3b8", fontSize: "12px" }}>
                            📝 Storyboard draft ready for editing.
                          </div>
                        )}

                        {item.status === "failed" && (
                          <div style={{ padding: "12px", background: "rgba(239,68,68,0.02)", borderRadius: "8px", border: "1px dashed rgba(239,68,68,0.08)", margin: "10px 0", textAlign: "center", color: "#fca5a5", fontSize: "12px" }}>
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
                            setUploadCaption(scriptData.instagram_metadata?.caption || "");
                            
                            setActiveTab("viral");
                            addLog(`📂 Loaded video generation "${item.topic || "Untitled"}" to publisher.`);
                          }}
                          className="btn btn-secondary"
                          style={{
                            width: "100%",
                            marginTop: "12px",
                            background: "linear-gradient(135deg, #a855f7 0%, #ec4899 100%)",
                            border: "none",
                            color: "white",
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
                            borderColor: "rgba(168, 85, 247, 0.4)",
                            color: "#d8b4fe"
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
                          color: "#f87171",
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
                  <p style={{ color: "#94a3b8", fontSize: "13px", marginTop: "4px" }}>
                    Monitor the background social media uploader, track status, and view execution logs for scheduled posts.
                  </p>
                </div>
                <button onClick={loadUploadQueue} className="btn btn-secondary" style={{ width: "auto", margin: 0, padding: "8px 16px" }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              <div className="queue-list">
                {uploadQueue.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "60px 20px", color: "#64748b" }}>
                    <Layers style={{ marginBottom: "15px", opacity: 0.3 }} size={48} />
                    <p style={{ fontSize: "15px", fontWeight: 500 }}>No scheduled upload jobs in queue.</p>
                    <p style={{ fontSize: "12px", color: "#475569", marginTop: "4px" }}>Publish or schedule a video from the publisher panel to start.</p>
                  </div>
                ) : (
                  uploadQueue.map((job) => {
                    const isExpanded = expandedJobId === job.id;
                    const platformsList = job.platforms || [];
                    const isScheduled = job.status === "scheduled";
                    
                    return (
                      <div key={job.id} className="queue-item">
                        <div className="queue-item-header">
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                              <h4 style={{ color: "#f8fafc", fontSize: "16px", fontWeight: 600, margin: 0 }}>
                                {job.topic || "Untitled Video"}
                              </h4>
                              <span className={`status-badge status-${job.status}`}>
                                {job.status}
                              </span>
                            </div>
                            
                            <div style={{ display: "flex", gap: "12px", marginTop: "6px", fontSize: "12px", color: "#94a3b8" }}>
                              <span>
                                📤 Platforms: {platformsList.map((p: string) => p === "youtube" ? "YouTube Shorts" : "Instagram Reels").join(", ")}
                              </span>
                              <span>•</span>
                              <span>
                                {isScheduled ? (
                                  <span style={{ color: "#f59e0b", fontWeight: 500 }}>
                                    🕒 Scheduled for: {new Date(job.scheduled_time).toLocaleString()}
                                  </span>
                                ) : (
                                  <span>Created: {new Date(job.created_at).toLocaleString()}</span>
                                )}
                              </span>
                            </div>
                          </div>

                          <button
                            onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                            className="btn btn-secondary"
                            style={{ width: "auto", margin: 0, padding: "6px 12px", fontSize: "12px", borderColor: isExpanded ? "#a855f7" : "rgba(255,255,255,0.1)" }}
                          >
                            {isExpanded ? "Hide Logs Console" : "View Logs Console"}
                          </button>
                        </div>

                        {isExpanded && (
                          <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "12px", marginTop: "6px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 600, color: "#a855f7", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: "6px" }}>
                              Execution Terminal Log
                            </span>
                            <div className="log-console" style={{ height: "180px", overflowY: "auto", fontSize: "12px", fontFamily: "monospace", background: "#05040a" }}>
                              {job.logs && job.logs.length > 0 ? (
                                job.logs.map((log: string, lIdx: number) => (
                                  <div 
                                    key={lIdx} 
                                    className="log-entry" 
                                    style={{ 
                                      color: log.startsWith("❌") || log.toLowerCase().includes("error") ? "#ef4444" : log.startsWith("✅") || log.toLowerCase().includes("success") ? "#10b981" : "#cbd5e1",
                                      marginBottom: "4px" 
                                    }}
                                  >
                                    {log}
                                  </div>
                                ))
                              ) : (
                                <div style={{ color: "#475569" }}>No logs captured for this job.</div>
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

          {activeTab === "scheduler" && (
            <div className="glass-card" style={{ padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
                <div>
                  <h2 className="card-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                    🤖 Daily Auto-Agent Scheduler
                  </h2>
                  <p style={{ color: "#94a3b8", fontSize: "13px", marginTop: "4px" }}>
                    Configure the autonomous scheduler agent to dynamically find trends, compose custom music, render videos, and post on YouTube.
                  </p>
                </div>
                <button onClick={loadSchedulerData} className="btn btn-secondary" style={{ width: "auto", margin: 0, padding: "8px 16px" }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              {schedulerConfig ? (
                <div className="scheduler-layout" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
                  {/* Left Side: Settings */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "16px", background: "rgba(255,255,255,0.02)", padding: "20px", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)" }}>
                    <h3 style={{ margin: "0 0 10px 0", color: "#f8fafc", fontSize: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
                      ⚙️ Scheduler Settings
                    </h3>
                    
                    {/* Enable Toggle */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(168, 85, 247, 0.05)", border: "1px solid rgba(168, 85, 247, 0.2)", padding: "12px 16px", borderRadius: "8px" }}>
                      <div>
                        <div style={{ fontWeight: 600, color: "#e9d5ff", fontSize: "14px" }}>Enable Automatic Posting</div>
                        <div style={{ fontSize: "12px", color: "#c084fc" }}>Autonomously publish 2 videos daily</div>
                      </div>
                      <input 
                        type="checkbox" 
                        checked={schedulerConfig.enabled} 
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, enabled: e.target.checked };
                          saveSchedulerConfig(updated);
                        }}
                        style={{ width: "20px", height: "20px", cursor: "pointer", accentColor: "#a855f7" }}
                      />
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                      {/* Region */}
                      <div className="form-group">
                        <label className="form-label">Trending Region</label>
                        <select 
                          value={schedulerConfig.region}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, region: e.target.value };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        >
                          <option value="US">United States (US)</option>
                          <option value="IN">India (IN)</option>
                          <option value="GB">United Kingdom (GB)</option>
                          <option value="CA">Canada (CA)</option>
                          <option value="AU">Australia (AU)</option>
                        </select>
                      </div>

                      {/* YouTube Default Privacy */}
                      <div className="form-group">
                        <label className="form-label">YouTube Upload Privacy</label>
                        <select 
                          value={schedulerConfig.privacy}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, privacy: e.target.value };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        >
                          <option value="private">Private (Recommended)</option>
                          <option value="unlisted">Unlisted</option>
                          <option value="public">Public (Immediate Post)</option>
                        </select>
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                      {/* Time Slot 1 */}
                      <div className="form-group">
                        <label className="form-label">Slot 1 Run Time</label>
                        <input 
                          type="time" 
                          value={schedulerConfig.time1}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, time1: e.target.value };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        />
                      </div>

                      {/* Time Slot 2 */}
                      <div className="form-group">
                        <label className="form-label">Slot 2 Run Time</label>
                        <input 
                          type="time" 
                          value={schedulerConfig.time2}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, time2: e.target.value };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Ollama Model (Script/Topic Evaluation)</label>
                      <select 
                        value={schedulerConfig.model}
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, model: e.target.value };
                          saveSchedulerConfig(updated);
                        }}
                        className="form-input"
                      >
                        {config?.ollama_models.map((m: string) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Leonardo Model (Image Synthesis)</label>
                      <select 
                        value={schedulerConfig.leonardo_model}
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, leonardo_model: e.target.value };
                          saveSchedulerConfig(updated);
                        }}
                        className="form-input"
                      >
                        {config?.leonardo_models.map((m: string) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Default Voice Actor</label>
                      <select 
                        value={schedulerConfig.voice}
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, voice: e.target.value };
                          saveSchedulerConfig(updated);
                        }}
                        className="form-input"
                      >
                        {config?.voices.map((v: string) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </div>

                    {/* Subtitle Settings */}
                    <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: "16px", marginTop: "8px" }}>
                      <h4 style={{ margin: "0 0 12px 0", color: "#e9d5ff", fontSize: "14px", fontWeight: 600 }}>
                        📝 Subtitle Customization
                      </h4>
                      
                      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                        {/* Enable Subtitles Checkbox */}
                        <label className="checkbox-container" style={{ margin: 0 }}>
                          <input 
                            type="checkbox" 
                            checked={schedulerConfig.enable_captions}
                            onChange={(e) => {
                              const updated = { ...schedulerConfig, enable_captions: e.target.checked };
                              saveSchedulerConfig(updated);
                            }}
                          />
                          <div className="checkbox-custom"></div>
                          <span style={{ fontSize: "13px", fontWeight: 600 }}>Burn Centered Subtitles</span>
                        </label>

                        {/* Font and Style Selector */}
                        {schedulerConfig.enable_captions && (
                          <>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                              <div className="form-group" style={{ margin: 0 }}>
                                <label className="form-label" style={{ fontSize: "12px" }}>Font Family</label>
                                <select 
                                  value={schedulerConfig.caption_font}
                                  onChange={(e) => {
                                    const updated = { ...schedulerConfig, caption_font: e.target.value };
                                    saveSchedulerConfig(updated);
                                  }}
                                  className="form-input"
                                  style={{ padding: "6px 10px", fontSize: "12px" }}
                                >
                                  <option value="Arial">Arial</option>
                                  <option value="Impact">Impact</option>
                                  <option value="Trebuchet MS">Trebuchet MS</option>
                                  <option value="Verdana">Verdana</option>
                                </select>
                              </div>

                              <div className="form-group" style={{ margin: 0 }}>
                                <label className="form-label" style={{ fontSize: "12px" }}>Highlight Style</label>
                                <select 
                                  value={schedulerConfig.caption_style}
                                  onChange={(e) => {
                                    const updated = { ...schedulerConfig, caption_style: e.target.value };
                                    saveSchedulerConfig(updated);
                                  }}
                                  className="form-input"
                                  style={{ padding: "6px 10px", fontSize: "12px" }}
                                >
                                  <option value="Viral Pop">Viral Pop (Pops + Color Highlights)</option>
                                  <option value="Standard">Standard Bottom Text</option>
                                </select>
                              </div>
                            </div>

                            {/* Size Slider */}
                            <div className="form-group" style={{ margin: 0 }}>
                              <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px", fontSize: "12px" }}>
                                <span>Font Size</span>
                                <span style={{ color: "#c084fc", fontWeight: 600 }}>{schedulerConfig.caption_size}px</span>
                              </label>
                              <div className="slider-group" style={{ gap: "8px" }}>
                                <input 
                                  type="range" 
                                  min="24" 
                                  max="120" 
                                  value={schedulerConfig.caption_size} 
                                  onChange={(e) => {
                                    const updated = { ...schedulerConfig, caption_size: parseInt(e.target.value) };
                                    saveSchedulerConfig(updated);
                                  }}
                                  style={{ flexGrow: 1, padding: 0, height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", cursor: "pointer" }}
                                />
                              </div>
                            </div>

                            {/* Margin Slider */}
                            <div className="form-group" style={{ margin: 0 }}>
                              <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px", fontSize: "12px" }}>
                                <span>Vertical Margin</span>
                                <span style={{ color: "#c084fc", fontWeight: 600 }}>{schedulerConfig.caption_margin_v}px</span>
                              </label>
                              <div className="slider-group" style={{ gap: "8px" }}>
                                <input 
                                  type="range" 
                                  min="50" 
                                  max="800" 
                                  value={schedulerConfig.caption_margin_v} 
                                  onChange={(e) => {
                                    const updated = { ...schedulerConfig, caption_margin_v: parseInt(e.target.value) };
                                    saveSchedulerConfig(updated);
                                  }}
                                  style={{ flexGrow: 1, padding: 0, height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", cursor: "pointer" }}
                                />
                              </div>
                            </div>

                            {/* Highlight Color */}
                            <div className="form-group" style={{ margin: 0 }}>
                              <label className="form-label" style={{ marginBottom: "6px", fontSize: "12px" }}>Highlight Accent Color</label>
                              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                {COLOR_PRESETS.map((preset) => {
                                  const isSelected = schedulerConfig.caption_color === preset.ass;
                                  return (
                                    <button
                                      key={preset.name}
                                      type="button"
                                      onClick={() => {
                                        const updated = { ...schedulerConfig, caption_color: preset.ass };
                                        saveSchedulerConfig(updated);
                                      }}
                                      style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "4px",
                                        background: isSelected ? "rgba(168, 85, 247, 0.25)" : "rgba(255,255,255,0.03)",
                                        border: `1px solid ${isSelected ? "#a855f7" : "rgba(255,255,255,0.08)"}`,
                                        borderRadius: "16px",
                                        padding: "4px 8px",
                                        cursor: "pointer",
                                        color: isSelected ? "#f8fafc" : "#94a3b8",
                                        fontSize: "11px",
                                        fontWeight: 600,
                                        transition: "all 0.2s ease"
                                      }}
                                    >
                                      <span style={{
                                        width: "8px",
                                        height: "8px",
                                        borderRadius: "50%",
                                        backgroundColor: preset.hex,
                                        display: "inline-block"
                                      }} />
                                      {preset.name}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    <div style={{ marginTop: "10px" }}>
                      <button
                        onClick={triggerSchedulerAgent}
                        disabled={triggerLoading}
                        className="btn btn-secondary"
                        style={{
                          width: "100%",
                          background: "linear-gradient(135deg, #a855f7 0%, #ec4899 100%)",
                          border: "none",
                          color: "white",
                          fontWeight: 600,
                          padding: "10px 0"
                        }}
                      >
                        {triggerLoading ? "🚀 Triggering..." : "🔥 Trigger Agent Run Now"}
                      </button>
                    </div>
                  </div>

                  {/* Right Side: Logs & Execution History */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h3 style={{ margin: 0, color: "#f8fafc", fontSize: "16px" }}>
                        📜 Scheduler Execution Logs
                      </h3>
                      {schedulerLogs.length > 0 && (
                        <button
                          onClick={handleClearSchedulerLogs}
                          style={{
                            background: "rgba(239, 68, 68, 0.1)",
                            border: "1px solid rgba(239, 68, 68, 0.2)",
                            color: "#ef4444",
                            borderRadius: "6px",
                            padding: "4px 10px",
                            fontSize: "11px",
                            fontWeight: 600,
                            cursor: "pointer",
                            transition: "all 0.2s"
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "rgba(239, 68, 68, 0.2)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "rgba(239, 68, 68, 0.1)";
                          }}
                        >
                          🗑️ Clear Logs
                        </button>
                      )}
                    </div>
                    
                    <div style={{ 
                      maxHeight: "530px", 
                      overflowY: "auto", 
                      display: "flex", 
                      flexDirection: "column", 
                      gap: "12px",
                      paddingRight: "6px"
                    }}>
                      {schedulerLogs.length === 0 ? (
                        <div style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
                          No execution logs found. Trigger a run or wait for the scheduler to execute.
                        </div>
                      ) : (
                        schedulerLogs.map((log: any, lIdx: number) => (
                          <div key={log.id || lIdx} style={{ 
                            background: "rgba(255,255,255,0.02)", 
                            border: `1px solid ${log.status === "success" ? "rgba(16, 185, 129, 0.15)" : log.status === "failed" ? "rgba(239, 68, 68, 0.15)" : "rgba(168, 85, 247, 0.15)"}`, 
                            borderRadius: "8px", 
                            padding: "12px" 
                          }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                              <span style={{ 
                                fontSize: "11px", 
                                fontWeight: 700, 
                                textTransform: "uppercase", 
                                padding: "2px 6px", 
                                borderRadius: "4px",
                                background: log.status === "success" ? "rgba(16, 185, 129, 0.1)" : log.status === "failed" ? "rgba(239, 68, 68, 0.1)" : "rgba(168, 85, 247, 0.1)",
                                color: log.status === "success" ? "#10b981" : log.status === "failed" ? "#ef4444" : "#a855f7"
                              }}>
                                {log.status}
                              </span>
                              <span style={{ fontSize: "11px", color: "#64748b" }}>
                                {new Date(log.timestamp).toLocaleString()}
                              </span>
                            </div>
                            
                            <div style={{ fontWeight: 600, color: "#f8fafc", fontSize: "13px", marginBottom: "4px" }}>
                              📌 {log.topic}
                            </div>
                            <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "8px" }}>
                              🕒 Slot: {log.slot}
                            </div>
                            
                            {/* Expandable step-by-step logs */}
                            <details style={{ cursor: "pointer" }}>
                              <summary style={{ fontSize: "11px", color: "#a855f7", outline: "none", fontWeight: 500 }}>
                                View Detailed Steps
                              </summary>
                              <div style={{ 
                                background: "#06050e", 
                                border: "1px solid rgba(255,255,255,0.05)", 
                                borderRadius: "6px", 
                                padding: "8px 12px", 
                                marginTop: "8px",
                                fontFamily: "monospace",
                                fontSize: "11px",
                                color: "#10b981",
                                overflowX: "auto",
                                maxHeight: "150px",
                                whiteSpace: "pre-wrap"
                              }}>
                                {log.logs?.join("\n")}
                              </div>
                            </details>

                            {log.youtube_id && (
                              <div style={{ marginTop: "10px", fontSize: "12px" }}>
                                <a 
                                  href={`https://youtu.be/${log.youtube_id}`}
                                  target="_blank" 
                                  rel="noopener noreferrer" 
                                  style={{ color: "#ec4899", fontWeight: 600, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "4px" }}
                                >
                                  📺 Watch on YouTube ↗
                                </a>
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
                  Loading scheduler configuration...
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Interactive Storyboard Editor */}
      {(activeTab === "viral" || activeTab === "longform") && storyboard.length > 0 && (
        <div className="glass-card" style={{ marginTop: "24px", padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
            <div>
              <h2 className="card-title" style={{ color: "#f43f5e", margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                <Layers /> Interactive Storyboard: {generatedTopic}
              </h2>
              <p style={{ color: "#94a3b8", fontSize: "13px", marginTop: "4px" }}>
                Edit narration scripts, adjust scene image prompts, select custom voiceovers per speaker, and regenerate individual assets before rendering.
              </p>
            </div>
            
            {/* Render Button */}
            <button
              onClick={activeTab === "longform" ? handleLongformRender : handleRenderStoryboard}
              disabled={rendering || storyboard.length === 0}
              className="btn btn-primary"
              style={{
                width: "auto",
                minWidth: "180px",
                height: "44px",
                background: "linear-gradient(135deg, #a855f7 0%, #ec4899 100%)",
                boxShadow: "0 4px 15px rgba(236, 72, 153, 0.3)",
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
                      <h3 style={{ fontSize: "16px", fontWeight: 600, color: "#f8fafc", margin: 0 }}>Scene {idx + 1}</h3>
                    </div>
                    {scene.duration && (
                      <span style={{ fontSize: "12px", color: "#94a3b8", background: "rgba(255,255,255,0.03)", padding: "3px 8px", borderRadius: "12px" }}>
                        ⏱️ {scene.duration.toFixed(2)}s
                      </span>
                    )}
                  </div>
                  
                  <div style={{ display: "grid", gridTemplateColumns: "150px 1fr 250px", gap: "20px" }} className="storyboard-columns-layout">
                    
                    {/* Left Column: Visual Asset */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                      {activeTab === "longform" ? (
                        scene.video_url ? (
                          <video 
                            src={scene.video_url} 
                            style={{ width: "120px", aspectRatio: "16/9", objectFit: "cover", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)", boxShadow: "0 4px 12px rgba(0,0,0,0.3)" }} 
                            controls
                          />
                        ) : (
                          <div style={{ width: "120px", aspectRatio: "16/9", background: "#06050e", border: "1px dashed rgba(255,255,255,0.1)", borderRadius: "8px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: "11px", textAlign: "center", padding: "4px" }}>
                            <Film size={20} style={{ marginBottom: "4px" }} />
                            Pexels Video
                          </div>
                        )
                      ) : (
                        scene.image_url ? (
                          <img 
                            src={scene.image_url} 
                            alt={`Scene ${idx + 1}`} 
                            style={{ width: "120px", aspectRatio: "9/16", objectFit: "cover", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)", boxShadow: "0 4px 12px rgba(0,0,0,0.3)" }} 
                          />
                        ) : (
                          <div style={{ width: "120px", aspectRatio: "9/16", background: "#06050e", border: "1px dashed rgba(255,255,255,0.1)", borderRadius: "8px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: "12px" }}>
                            <ImageIcon size={24} style={{ marginBottom: "8px" }} />
                            No Image
                          </div>
                        )
                      )}
                      
                      {activeTab !== "longform" && (
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
                      )}
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
                          <div style={{ fontSize: "11px", color: "#64748b", padding: "6px", background: "rgba(0,0,0,0.2)", borderRadius: "4px", textAlign: "center" }}>
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
