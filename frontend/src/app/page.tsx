"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Tv, Sparkles, Sliders, Play, Settings, AlertCircle, FileText, CheckCircle2,
  Layers, Volume2, Image as ImageIcon, Music, RefreshCw, Subtitles, HelpCircle,
  Trash2, Film, DollarSign, Lightbulb, Shuffle, ArrowRight, Gauge, Download
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
  art_styles?: string[];
  visual_modes?: string[];
  quality_presets?: string[];
  visual_source_modes?: string[];
  stock_available?: boolean;
  default_quality?: string;
  motion_styles?: string[];
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

// Evergreen "curiosity-gap" topics — the kind that reliably trend on YouTube
// Shorts. Each opens a loop the viewer feels compelled to close. One click
// loads it into the script drafter below.
interface CuriosityTopic {
  category: string;
  emoji: string;
  title: string;
  hook: string;
}

const CURIOSITY_TOPICS: CuriosityTopic[] = [
  // Space & Cosmos
  { category: "Space", emoji: "🌌", title: "What's really inside a black hole", hook: "Nothing that falls in ever comes back — and time itself breaks down." },
  { category: "Space", emoji: "🌌", title: "The hidden ocean beneath Jupiter's moon Europa", hook: "More water than all of Earth's oceans, sealed under miles of ice." },
  { category: "Space", emoji: "🌌", title: "What you'd see at the edge of the universe", hook: "Spoiler: there may be no edge at all." },
  { category: "Space", emoji: "🌌", title: "The star so big it makes the Sun look invisible", hook: "UY Scuti could swallow billions of Suns whole." },
  { category: "Space", emoji: "🌌", title: "Why the Moon is slowly escaping Earth", hook: "It drifts 3.8 cm farther away every single year." },

  // Deep Ocean
  { category: "Deep Ocean", emoji: "🌊", title: "The creatures at the bottom of the Mariana Trench", hook: "Life thrives seven miles down, where sunlight has never reached." },
  { category: "Deep Ocean", emoji: "🌊", title: "What's hiding in the ocean's midnight zone", hook: "95% of the ocean has never been seen by human eyes." },
  { category: "Deep Ocean", emoji: "🌊", title: "The underwater waterfall you can actually see", hook: "Mauritius hides an optical illusion of an ocean falling off a cliff." },
  { category: "Deep Ocean", emoji: "🌊", title: "Why we've mapped Mars better than our own seafloor", hook: "We know the red planet's surface in sharper detail than Earth's." },

  // Unsolved Mysteries
  { category: "Mysteries", emoji: "🕵️", title: "The ships that vanished in the Bermuda Triangle", hook: "Decades of disappearances — and not a single wreck ever found." },
  { category: "Mysteries", emoji: "🕵️", title: "The radio signal from space we still can't explain", hook: "The 'Wow!' signal lasted 72 seconds and never repeated." },
  { category: "Mysteries", emoji: "🕵️", title: "The ancient computer 2,000 years ahead of its time", hook: "The Antikythera mechanism predicted eclipses before clocks existed." },
  { category: "Mysteries", emoji: "🕵️", title: "The lost city that might actually be Atlantis", hook: "Real ruins keep dragging the legend back to life." },

  // Human Body & Mind
  { category: "Body & Mind", emoji: "🧠", title: "What happens in the seconds after you die", hook: "The brain may stay active far longer than anyone believed." },
  { category: "Body & Mind", emoji: "🧠", title: "Why you forget your dreams within minutes", hook: "Your brain is wired to erase them on purpose." },
  { category: "Body & Mind", emoji: "🧠", title: "The organ scientists only just discovered inside you", hook: "Hiding in plain sight for centuries until 2018." },
  { category: "Body & Mind", emoji: "🧠", title: "Why you can't tickle yourself", hook: "Your brain cancels the sensation before it even happens." },

  // Ancient World
  { category: "Ancient World", emoji: "🏛️", title: "How the pyramids were really built", hook: "New evidence overturns almost everything you were taught." },
  { category: "Ancient World", emoji: "🏛️", title: "The Roman concrete that heals its own cracks", hook: "Stronger after 2,000 years than the cement we pour today." },
  { category: "Ancient World", emoji: "🏛️", title: "The 12,000-year-old temple that rewrites history", hook: "Göbekli Tepe was built before farming was even invented." },
  { category: "Ancient World", emoji: "🏛️", title: "The library that held all of humanity's knowledge", hook: "And the fire that erased it from history forever." },

  // What If
  { category: "What If", emoji: "⚡", title: "What if the Earth stopped spinning for 5 seconds", hook: "The consequences would be catastrophic and instant." },
  { category: "What If", emoji: "⚡", title: "What if you fell into a hole through the Earth", hook: "Physics gives a far stranger answer than you'd expect." },
  { category: "What If", emoji: "⚡", title: "What if the Sun disappeared right now", hook: "You wouldn't even notice for eight whole minutes." },
  { category: "What If", emoji: "⚡", title: "What if every human jumped at the exact same time", hook: "The Earth barely flinches — here's the math." },

  // Hidden Micro World
  { category: "Micro World", emoji: "🔬", title: "The animal that can survive in outer space", hook: "Tardigrades are basically impossible to kill." },
  { category: "Micro World", emoji: "🔬", title: "How many bacteria are living on your phone", hook: "More than you'd find on a public toilet seat." },
  { category: "Micro World", emoji: "🔬", title: "What a single drop of pond water really contains", hook: "An entire alien-looking universe you can't see." },

  // Future & Tech
  { category: "Future & Tech", emoji: "🤖", title: "The AI that taught itself to do the impossible", hook: "And the researchers still can't fully explain how." },
  { category: "Future & Tech", emoji: "🤖", title: "Why scientists want to bring back the woolly mammoth", hook: "De-extinction is far closer than you think." },
  { category: "Future & Tech", emoji: "🤖", title: "The material thinner than paper, stronger than steel", hook: "Graphene could quietly rebuild the entire world." },
];

const CURIOSITY_CATEGORIES = ["All", ...Array.from(new Set(CURIOSITY_TOPICS.map((t) => t.category)))];

export default function Home() {
  const [activeTab, setActiveTab] = useState<"viral" | "library" | "queue" | "scheduler">("viral");
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
  const [curiosityCatOptions, setCuriosityCatOptions] = useState<string[]>(["All"]);
  const [schedulerLogs, setSchedulerLogs] = useState<any[]>([]);
  const [triggerLoading, setTriggerLoading] = useState(false);

  // Input states: Viral Shorts Studio
  const [viralPrompt, setViralPrompt] = useState("The giant hidden ocean underneath Jupiter's moon Europa");
  const [viralOllamaModel, setViralOllamaModel] = useState("");
  const [enableSearch, setEnableSearch] = useState(false);

  // Curiosity Topics state (curated evergreen library)
  const [curiosityCategory, setCuriosityCategory] = useState("All");

  // Trending Topics state
  const [trends, setTrends] = useState<any[]>([]);
  const [trendsGeo, setTrendsGeo] = useState("IN");
  const [isFetchingTrends, setIsFetchingTrends] = useState(false);
  const [trendsError, setTrendsError] = useState("");

  // Revenue-optimized topic recommender state
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [recsGeo, setRecsGeo] = useState("US");
  const [discoverMode, setDiscoverMode] = useState<"trends" | "ideas">("trends");
  const [isFetchingRecs, setIsFetchingRecs] = useState(false);
  const [recsError, setRecsError] = useState("");
  const [viralVoice, setViralVoice] = useState("Sarah (Female - US - Soft)");
  const [viralVoiceSpeed, setViralVoiceSpeed] = useState(1.0);
  const [visualMode, setVisualMode] = useState("Cinematic Slideshow");
  const [artStyle, setArtStyle] = useState("Photorealistic");
  const [viralLeonardoModel, setViralLeonardoModel] = useState("Lucid Realism (High Quality Face)");
  const [musicStyle, setMusicStyle] = useState("Cinematic");
  const [satisfyingBackground, setSatisfyingBackground] = useState("Slime ASMR");
  const [viralHookStyle, setViralHookStyle] = useState("Did You Know? (Fact Hook)");
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
  const [isIgConfigured, setIsIgConfigured] = useState(false);
  const [imageProviderStatus, setImageProviderStatus] = useState<any>(null);
  const [sdModels, setSdModels] = useState<any[]>([]);
  const [sdCurrentModel, setSdCurrentModel] = useState<string>("");
  const [switchingModel, setSwitchingModel] = useState(false);
  const [imageProvider, setImageProvider] = useState("");
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

  const handleFetchRecommendations = async () => {
    setIsFetchingRecs(true);
    setRecsError("");
    try {
      const res = await fetch(`http://localhost:8000/api/recommend-topics?geo=${recsGeo}&count=5`);
      if (res.ok) {
        const data = await res.json();
        setRecommendations(data);
      } else {
        const detail = await res.json().catch(() => null);
        setRecsError(detail?.detail || `HTTP error! status: ${res.status}`);
      }
    } catch (e: any) {
      setRecsError(`Connection failed: ${e.message || e}`);
    } finally {
      setIsFetchingRecs(false);
    }
  };

  const handleUseRecommendedTopic = (rec: any) => {
    const parts = [`Write a 15-second viral short about: ${rec.title}.`];
    if (rec.rationale) parts.push(`Angle: ${rec.rationale}`);
    if (rec.niche) parts.push(`Niche: ${rec.niche} (high-RPM, ${rec.geo || "US"} audience).`);
    setViralPrompt(parts.join(" "));
    setEnableSearch(true);
    const configSection = document.getElementById("viral-config-card");
    if (configSection) configSection.scrollIntoView({ behavior: "smooth" });
  };

  const handleUseCuriosityTopic = (topic: CuriosityTopic) => {
    setViralPrompt(
      `Write a 15-second viral short about: ${topic.title}. Curiosity angle: ${topic.hook} Open with an irresistible hook, build tension fast, and end on a mind-blowing payoff.`
    );
    setEnableSearch(true);
    const configSection = document.getElementById("viral-config-card");
    if (configSection) configSection.scrollIntoView({ behavior: "smooth" });
  };

  const handleSurpriseCuriosityTopic = () => {
    const pool =
      curiosityCategory === "All"
        ? CURIOSITY_TOPICS
        : CURIOSITY_TOPICS.filter((t) => t.category === curiosityCategory);
    if (pool.length === 0) return;
    handleUseCuriosityTopic(pool[Math.floor(Math.random() * pool.length)]);
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
    
    try {
      const response = await fetch("http://localhost:8000/api/draft-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: viralPrompt,
          model: viralOllamaModel || "minimax-m3:cloud",
          hook_style: viralHookStyle,
          enable_search: enableSearch,
          voice: viralVoice,
          art_style: artStyle
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
      const resCat = await fetch("http://localhost:8000/api/curiosity-topics");
      if (resCat.ok) {
        const data = await resCat.json();
        if (Array.isArray(data.categories)) setCuriosityCatOptions(data.categories);
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
      if (!res.ok) {
        alert("Failed to trigger agent");
        setTriggerLoading(false);
        return;
      }
      addLog("🚀 Manual Agent Run triggered. Generating viral short (this can take a minute)...");

      // The run executes in the background, so poll the logs until the latest
      // entry leaves the "running" state, keeping the loader live the whole time.
      const startedAt = Date.now();
      const poll = async () => {
        try {
          const r = await fetch("http://localhost:8000/api/scheduler/logs");
          if (r.ok) {
            const logs = await r.json();
            setSchedulerLogs(logs);
            const latest = logs?.[0];
            if (latest && latest.status !== "running") {
              setTriggerLoading(false);
              if (latest.status === "success") {
                addLog("✅ Agent run completed successfully.");
              } else {
                const reason = latest.logs?.[latest.logs.length - 1] || "see scheduler logs";
                addLog(`❌ Agent run failed: ${reason}`);
              }
              return;
            }
          }
        } catch (e) {
          console.error("Error polling scheduler logs:", e);
        }
        if (Date.now() - startedAt > 300000) {
          setTriggerLoading(false);
          addLog("⌛ Stopped watching the agent run after 5 minutes. Check scheduler logs for the result.");
          return;
        }
        setTimeout(poll, 4000);
      };
      setTimeout(poll, 3000);
    } catch (err) {
      console.error("Error triggering agent:", err);
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
        <p className="subtitle">AI Shorts &amp; Reels Creator for YouTube and Instagram</p>
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
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "2px 0 0 0" }}>Check authorization status for direct video publishing to YouTube and Instagram.</p>
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

            {/* Instagram Readiness */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.05)", padding: "6px 12px", borderRadius: "10px" }}>
              <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-secondary)" }}>Instagram Reels:</span>
              {isIgConfigured ? (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--ok)", fontSize: "13px", fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Ready
                </span>
              ) : (
                <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--warn)", fontSize: "13px", fontWeight: 600 }} title="Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN in .env">
                  <AlertCircle size={14} /> Needs Keys
                </span>
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
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px", gap: "12px", flexWrap: "wrap" }}>
                  <h2 className="card-title" style={{ margin: 0 }}>
                    <DollarSign /> Discover Topics
                  </h2>
                  <div style={{ display: "inline-flex", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "10px", padding: "3px" }}>
                    <button onClick={() => setDiscoverMode("trends")} style={{ cursor: "pointer", border: "none", width: "auto", padding: "6px 14px", fontSize: "13px", fontWeight: 600, borderRadius: "7px", background: discoverMode === "trends" ? "var(--accent)" : "transparent", color: discoverMode === "trends" ? "var(--accent-ink)" : "var(--text-secondary)" }}>🔥 Trending</button>
                    <button onClick={() => setDiscoverMode("ideas")} style={{ cursor: "pointer", border: "none", width: "auto", padding: "6px 14px", fontSize: "13px", fontWeight: 600, borderRadius: "7px", background: discoverMode === "ideas" ? "var(--accent)" : "transparent", color: discoverMode === "ideas" ? "var(--accent-ink)" : "var(--text-secondary)" }}>💲 High-RPM</button>
                  </div>
                </div>

                {discoverMode === "trends" && (<>
                <p className="card-subtitle" style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "15px" }}>
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
                  <p style={{ color: "var(--danger)", fontSize: "0.9rem", marginBottom: "15px" }}>{trendsError}</p>
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
                          background: "var(--surface-2)", 
                          borderRadius: "8px", 
                          padding: "12px", 
                          border: "1px solid var(--border)", 
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
                            <div style={{ height: "110px", background: "var(--surface-2)", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "10px" }}>
                              No Thumbnail
                            </div>
                          )}
                          <h4 style={{ margin: "0 0 4px 0", color: "var(--text-primary)", fontSize: "1rem" }}>{t.title}</h4>
                          <span style={{ background: "var(--danger)", color: "#ffffff", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold" }}>
                            🔥 {t.traffic}
                          </span>
                          
                          {t.news_title && (
                            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "8px", lineHeight: "1.25" }}>
                              <b>News</b>: <a href={t.news_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", textDecoration: "none" }}>{t.news_title}</a>
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
                </>)}

                {discoverMode === "ideas" && (<>
                <p className="card-subtitle" style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "15px" }}>
                  Trends from high-paying markets (USA pays the most), ranked toward high-CPM niches like finance, tech &amp; business. Pick one and make a video.
                </p>

                <div className="form-row" style={{ alignItems: "flex-end", marginBottom: "20px" }}>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label">Target Market (by RPM)</label>
                    <select
                      className="form-select"
                      value={recsGeo}
                      onChange={(e) => setRecsGeo(e.target.value)}
                    >
                      <option value="US">🇺🇸 United States — Highest RPM</option>
                      <option value="AU">🇦🇺 Australia — Very High RPM</option>
                      <option value="CA">🇨🇦 Canada — High RPM</option>
                      <option value="GB">🇬🇧 United Kingdom — High RPM</option>
                    </select>
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={handleFetchRecommendations}
                    disabled={isFetchingRecs}
                    style={{ height: "42px", minWidth: "190px", background: "linear-gradient(135deg, var(--ok) 0%, var(--ok) 100%)" }}
                  >
                    {isFetchingRecs ? "Thinking..." : "Get High-RPM Topic Ideas"}
                  </button>
                </div>

                {recsError && (
                  <p style={{ color: "var(--danger)", fontSize: "0.9rem", marginBottom: "15px" }}>{recsError}</p>
                )}

                {recommendations.length > 0 && (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                      gap: "15px",
                      maxHeight: "380px",
                      overflowY: "auto",
                      paddingRight: "5px",
                      marginTop: "10px"
                    }}
                  >
                    {recommendations.map((rec, idx) => {
                      const tier = String(rec.rpm_tier || "Medium");
                      const tierColor = tier === "High" ? "var(--ok)" : tier === "Low" ? "var(--text-muted)" : "var(--warn)";
                      return (
                        <div
                          key={idx}
                          className="trend-card"
                          style={{
                            background: "var(--surface-2)",
                            borderRadius: "8px",
                            padding: "14px",
                            border: "1px solid var(--border)",
                            display: "flex",
                            flexDirection: "column",
                            justifyContent: "space-between",
                            transition: "all 0.2s ease"
                          }}
                        >
                          <div>
                            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "8px" }}>
                              <span style={{ background: tierColor, color: "var(--accent-ink)", fontSize: "0.72rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold" }}>
                                {tier} RPM
                              </span>
                              <span style={{ background: "var(--surface-2)", color: "var(--accent)", fontSize: "0.72rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold", textTransform: "capitalize" }}>
                                {rec.niche || "general"}
                              </span>
                              {rec.est_rpm && (
                                <span style={{ background: "var(--surface-2)", color: "var(--ok)", fontSize: "0.72rem", padding: "2px 8px", borderRadius: "10px", fontWeight: "bold" }}>
                                  ~{rec.est_rpm} / 1k
                                </span>
                              )}
                            </div>
                            <h4 style={{ margin: "0 0 6px 0", color: "var(--text-primary)", fontSize: "1rem", lineHeight: "1.3" }}>{rec.title}</h4>
                            {rec.rationale && (
                              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "4px", lineHeight: "1.3" }}>{rec.rationale}</p>
                            )}
                          </div>

                          <button
                            className="btn btn-secondary"
                            style={{ width: "100%", marginTop: "12px", padding: "6px 0", fontSize: "0.85rem" }}
                            onClick={() => handleUseRecommendedTopic(rec)}
                          >
                            Use this topic
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
                </>)}
              </div>

              {/* Curiosity Topics — curated evergreen library that trends on YouTube */}
              <div className="glass-card curiosity-card-wrap" style={{ marginBottom: "20px" }}>
                <div className="curiosity-head">
                  <div>
                    <h2 className="card-title" style={{ margin: 0 }}>
                      <Lightbulb /> Curiosity Topics
                    </h2>
                    <p className="card-subtitle" style={{ marginTop: "6px" }}>
                      Hand-picked curiosity-gap ideas built to trend on Shorts. Tap one to load it straight into the drafter.
                    </p>
                  </div>
                  <button
                    className="curiosity-surprise"
                    onClick={handleSurpriseCuriosityTopic}
                    title="Pick a random topic and load it"
                  >
                    <Shuffle size={15} /> Surprise me
                  </button>
                </div>

                <div className="curiosity-chips">
                  {CURIOSITY_CATEGORIES.map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setCuriosityCategory(cat)}
                      className={`curiosity-chip ${curiosityCategory === cat ? "curiosity-chip-active" : ""}`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                <div className="curiosity-grid">
                  {CURIOSITY_TOPICS
                    .filter((t) => curiosityCategory === "All" || t.category === curiosityCategory)
                    .map((topic, idx) => (
                      <button
                        key={`${topic.title}-${idx}`}
                        className="curiosity-item"
                        onClick={() => handleUseCuriosityTopic(topic)}
                      >
                        <span className="curiosity-item-cat">
                          <span className="curiosity-item-emoji">{topic.emoji}</span>
                          {topic.category}
                        </span>
                        <span className="curiosity-item-title">{topic.title}</span>
                        <span className="curiosity-item-hook">{topic.hook}</span>
                        <span className="curiosity-item-cta">
                          Use topic <ArrowRight size={13} />
                        </span>
                      </button>
                    ))}
                </div>
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

            {/* Social Media Publish Section */}
            {finalVideoUrl && !loading && (
              <div className="glass-card" style={{ padding: "18px", border: "1px solid rgba(200, 255, 0, 0.2)", marginTop: "15px" }}>
                <h3 className="card-title" style={{ fontSize: "18px", display: "flex", gap: "8px", alignItems: "center", color: "var(--accent)", margin: "0 0 10px 0" }}>
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
                        <span style={{ fontSize: "15px", fontWeight: 600, color: "var(--danger)" }}>YouTube Shorts</span>
                      </label>
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
                          <span style={{ color: "var(--danger)", fontSize: "11px", fontWeight: 600, display: "block", marginBottom: "6px", textTransform: "uppercase" }}>Scheduling</span>
                          <div style={{ display: "flex", gap: "15px", marginBottom: "6px" }}>
                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="yt_publish_time_opt"
                                checked={ytPublishImmediate}
                                onChange={() => setYtPublishImmediate(true)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Immediate</span>
                            </label>

                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="yt_publish_time_opt"
                                checked={!ytPublishImmediate}
                                onChange={() => setYtPublishImmediate(false)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Later</span>
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
                            background: "linear-gradient(135deg, var(--danger) 0%, var(--danger) 100%)",
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
                                <div key={i} style={{ color: log.startsWith("❌") ? "var(--danger)" : log.startsWith("✅") || log.includes("successful") ? "var(--ok)" : "var(--text-primary)", marginBottom: "2px" }}>{log}</div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "10px 0 0 0" }}>Check the box above to enable YouTube Shorts publishing configuration.</p>
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
                        <span style={{ fontSize: "11px", color: "var(--ok)", fontWeight: 700 }}>Ready ✅</span>
                      ) : (
                        <span style={{ fontSize: "11px", color: "var(--warn)", fontWeight: 700 }}>Not Configured ⚠️</span>
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
                              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Immediate</span>
                            </label>

                            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", margin: 0 }}>
                              <input 
                                type="radio" 
                                name="ig_publish_time_opt"
                                checked={!igPublishImmediate}
                                onChange={() => setIgPublishImmediate(false)}
                                style={{ marginRight: "4px" }}
                              />
                              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Later</span>
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
                                <div key={i} style={{ color: log.startsWith("❌") ? "var(--danger)" : log.startsWith("✅") || log.includes("successful") ? "var(--ok)" : "var(--text-primary)", marginBottom: "2px" }}>{log}</div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "10px 0 0 0" }}>Check the box above to enable Instagram Reels publishing configuration.</p>
                    )}
                  </div>

                </div>
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
                    Browse your database of previously generated video shorts, drafts, and talking head presentations.
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
                            setUploadCaption(scriptData.instagram_metadata?.caption || "");
                            
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
                    Monitor the background social media uploader, track status, and view execution logs for scheduled posts.
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
                    <p style={{ fontSize: "15px", fontWeight: 500 }}>No scheduled upload jobs in queue.</p>
                    <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>Publish or schedule a video from the publisher panel to start.</p>
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
                              <h4 style={{ color: "var(--text-primary)", fontSize: "16px", fontWeight: 600, margin: 0 }}>
                                {job.topic || "Untitled Video"}
                              </h4>
                              <span className={`status-badge status-${job.status}`}>
                                {job.status}
                              </span>
                            </div>
                            
                            <div style={{ display: "flex", gap: "12px", marginTop: "6px", fontSize: "12px", color: "var(--text-secondary)" }}>
                              <span>
                                📤 Platforms: {platformsList.map((p: string) => p === "youtube" ? "YouTube Shorts" : "Instagram Reels").join(", ")}
                              </span>
                              <span>•</span>
                              <span>
                                {isScheduled ? (
                                  <span style={{ color: "var(--warn)", fontWeight: 500 }}>
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

          {activeTab === "scheduler" && (
            <div className="glass-card" style={{ padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "15px", marginBottom: "20px" }}>
                <div>
                  <h2 className="card-title" style={{ margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                    🤖 Daily Auto-Agent Scheduler
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "13px", marginTop: "4px" }}>
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
                    <h3 style={{ margin: "0 0 10px 0", color: "var(--text-primary)", fontSize: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
                      ⚙️ Scheduler Settings
                    </h3>
                    
                    {/* Enable Toggle */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(200, 255, 0, 0.05)", border: "1px solid rgba(200, 255, 0, 0.2)", padding: "12px 16px", borderRadius: "8px" }}>
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "14px" }}>Enable Automatic Posting</div>
                        <div style={{ fontSize: "12px", color: "var(--accent)" }}>
                          Autonomously publish {2 * (schedulerConfig.videos_per_run || 1)} videos daily
                          {" "}({schedulerConfig.videos_per_run || 1} per slot × 2 slots)
                        </div>
                      </div>
                      <input 
                        type="checkbox" 
                        checked={schedulerConfig.enabled} 
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, enabled: e.target.checked };
                          saveSchedulerConfig(updated);
                        }}
                        style={{ width: "20px", height: "20px", cursor: "pointer", accentColor: "var(--accent)" }}
                      />
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                      {/* Topic Source */}
                      <div className="form-group">
                        <label className="form-label">Topic Source</label>
                        <select
                          value={schedulerConfig.topic_source || "trends"}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, topic_source: e.target.value };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        >
                          <option value="trends">🔥 Live Google Trends</option>
                          <option value="curiosity">💡 Curiosity Topics (curated)</option>
                          <option value="mixed">🔀 Mixed (blend both)</option>
                        </select>
                        <p className="form-label-info">
                          {(schedulerConfig.topic_source || "trends") === "trends"
                            ? "Picks the best safe topic from live trends."
                            : (schedulerConfig.topic_source === "curiosity")
                            ? "Pulls evergreen curiosity-gap topics; the hook is fed in as script context."
                            : "Alternates randomly between live trends and curiosity topics."}
                        </p>
                      </div>

                      {/* Curiosity Category (only relevant when curiosity topics are in play) */}
                      {(schedulerConfig.topic_source === "curiosity" || schedulerConfig.topic_source === "mixed") && (
                        <div className="form-group">
                          <label className="form-label">Curiosity Category</label>
                          <select
                            value={schedulerConfig.curiosity_category || "All"}
                            onChange={(e) => {
                              const updated = { ...schedulerConfig, curiosity_category: e.target.value };
                              saveSchedulerConfig(updated);
                            }}
                            className="form-input"
                          >
                            {curiosityCatOptions.map((cat) => (
                              <option key={cat} value={cat}>{cat === "All" ? "All categories" : cat}</option>
                            ))}
                          </select>
                          <p className="form-label-info">Keep runs on-theme for a niche channel.</p>
                        </div>
                      )}

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
                        <p className="form-label-info">Used by the trends source.</p>
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

                      {/* Videos per run (each a different topic) */}
                      <div className="form-group">
                        <label className="form-label">Videos Per Run</label>
                        <select
                          value={schedulerConfig.videos_per_run || 1}
                          onChange={(e) => {
                            const updated = { ...schedulerConfig, videos_per_run: parseInt(e.target.value) };
                            saveSchedulerConfig(updated);
                          }}
                          className="form-input"
                        >
                          {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => (
                            <option key={n} value={n}>{n} video{n > 1 ? "s" : ""} (different topics)</option>
                          ))}
                        </select>
                        <div className="form-label-info">
                          Each run generates this many videos, every one on a distinct trending topic.
                        </div>
                      </div>
                    </div>

                    {/* Subscribe / channel growth */}
                    <div className="form-group" style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "14px" }}>
                      <label className="checkbox-container" style={{ marginBottom: "12px" }}>
                        <input
                          type="checkbox"
                          checked={schedulerConfig.subscribe_overlay !== false}
                          onChange={(e) => saveSchedulerConfig({ ...schedulerConfig, subscribe_overlay: e.target.checked })}
                        />
                        <span className="checkbox-custom"></span>
                        <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>Show animated SUBSCRIBE button at the end of each video</span>
                      </label>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                        <div>
                          <label className="form-label">Channel Handle (shown on screen)</label>
                          <input
                            type="text"
                            value={schedulerConfig.channel_handle || ""}
                            placeholder="@yourchannel"
                            onChange={(e) => setSchedulerConfig({ ...schedulerConfig, channel_handle: e.target.value })}
                            onBlur={(e) => saveSchedulerConfig({ ...schedulerConfig, channel_handle: e.target.value })}
                            className="form-input"
                          />
                        </div>
                        <div>
                          <label className="form-label">Channel URL (in description)</label>
                          <input
                            type="text"
                            value={schedulerConfig.youtube_channel_url || ""}
                            placeholder="https://youtube.com/@yourchannel?sub_confirmation=1"
                            onChange={(e) => setSchedulerConfig({ ...schedulerConfig, youtube_channel_url: e.target.value })}
                            onBlur={(e) => saveSchedulerConfig({ ...schedulerConfig, youtube_channel_url: e.target.value })}
                            className="form-input"
                          />
                        </div>
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
                      <label className="form-label">Image Provider</label>
                      <select
                        value={schedulerConfig.image_provider || "local"}
                        onChange={(e) => {
                          const updated = { ...schedulerConfig, image_provider: e.target.value };
                          saveSchedulerConfig(updated);
                        }}
                        className="form-input"
                      >
                        <option value="local">Local (on-device SD · M4 GPU · free)</option>
                        <option value="pollinations">Pollinations (free hosted · no key)</option>
                        <option value="leonardo">Leonardo (cloud · needs API tokens)</option>
                      </select>
                      <div className="form-label-info">
                        {(schedulerConfig.image_provider || "local") === "local"
                          ? "Requires the local SD server running (python sd_server.py)."
                          : (schedulerConfig.image_provider === "leonardo"
                            ? "Uses your Leonardo API credits."
                            : "No setup needed; images generated by a free hosted endpoint.")}
                      </div>
                    </div>

                    {(schedulerConfig.image_provider || "local") === "leonardo" && (
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
                    )}

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
                      <h4 style={{ margin: "0 0 12px 0", color: "var(--text-primary)", fontSize: "14px", fontWeight: 600 }}>
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
                                  <option value="Soft Pill">Soft Pill (Rounded Plate + Highlights)</option>
                                  <option value="Standard">Standard Bottom Text</option>
                                </select>
                              </div>
                            </div>

                            {/* Size Slider */}
                            <div className="form-group" style={{ margin: 0 }}>
                              <label className="form-label" style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px", fontSize: "12px" }}>
                                <span>Font Size</span>
                                <span style={{ color: "var(--accent)", fontWeight: 600 }}>{schedulerConfig.caption_size}px</span>
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
                                <span style={{ color: "var(--accent)", fontWeight: 600 }}>{schedulerConfig.caption_margin_v}px</span>
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
                                        background: isSelected ? "rgba(200, 255, 0, 0.25)" : "rgba(255,255,255,0.03)",
                                        border: `1px solid ${isSelected ? "var(--accent)" : "rgba(255,255,255,0.08)"}`,
                                        borderRadius: "16px",
                                        padding: "4px 8px",
                                        cursor: "pointer",
                                        color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
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
                          background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-press) 100%)",
                          border: "none",
                          color: "var(--accent-ink)",
                          fontWeight: 600,
                          padding: "10px 0"
                        }}
                      >
                        {triggerLoading ? "⏳ Agent running… generating video" : "🔥 Trigger Agent Run Now"}
                      </button>
                    </div>
                  </div>

                  {/* Right Side: Logs & Execution History */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h3 style={{ margin: 0, color: "var(--text-primary)", fontSize: "16px" }}>
                        📜 Scheduler Execution Logs
                      </h3>
                      {schedulerLogs.length > 0 && (
                        <button
                          onClick={handleClearSchedulerLogs}
                          style={{
                            background: "rgba(239, 68, 68, 0.1)",
                            border: "1px solid rgba(239, 68, 68, 0.2)",
                            color: "var(--danger)",
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
                        <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                          No execution logs found. Trigger a run or wait for the scheduler to execute.
                        </div>
                      ) : (
                        schedulerLogs.map((log: any, lIdx: number) => (
                          <div key={log.id || lIdx} style={{ 
                            background: "rgba(255,255,255,0.02)", 
                            border: `1px solid ${log.status === "success" ? "rgba(16, 185, 129, 0.15)" : log.status === "failed" ? "rgba(239, 68, 68, 0.15)" : "rgba(200, 255, 0, 0.15)"}`, 
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
                                background: log.status === "success" ? "rgba(16, 185, 129, 0.1)" : log.status === "failed" ? "rgba(239, 68, 68, 0.1)" : "rgba(200, 255, 0, 0.1)",
                                color: log.status === "success" ? "var(--ok)" : log.status === "failed" ? "var(--danger)" : "var(--accent)"
                              }}>
                                {log.status}
                              </span>
                              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                                {new Date(log.timestamp).toLocaleString()}
                              </span>
                            </div>
                            
                            <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "13px", marginBottom: "4px" }}>
                              📌 {log.topic}
                            </div>
                            <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "8px" }}>
                              🕒 Slot: {log.slot}
                            </div>
                            
                            {/* Expandable step-by-step logs */}
                            <details style={{ cursor: "pointer" }}>
                              <summary style={{ fontSize: "11px", color: "var(--accent)", outline: "none", fontWeight: 500 }}>
                                View Detailed Steps
                              </summary>
                              <div style={{ 
                                background: "var(--bg-2)", 
                                border: "1px solid rgba(255,255,255,0.05)", 
                                borderRadius: "6px", 
                                padding: "8px 12px", 
                                marginTop: "8px",
                                fontFamily: "monospace",
                                fontSize: "11px",
                                color: "var(--ok)",
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
                <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                  Loading scheduler configuration...
                </div>
              )}
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
