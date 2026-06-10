"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Tv, Sparkles, Sliders, Play, Settings, AlertCircle, FileText, CheckCircle2, 
  Layers, Volume2, Image as ImageIcon, Music, RefreshCw, Subtitles, HelpCircle
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
  const [activeTab, setActiveTab] = useState<"viral" | "full" | "manual">("viral");
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [statusText, setStatusText] = useState("");
  
  // Results
  const [finalVideoUrl, setFinalVideoUrl] = useState<string | null>(null);
  const [presenterImageUrl, setPresenterImageUrl] = useState<string | null>(null);
  const [voiceAudioUrl, setVoiceAudioUrl] = useState<string | null>(null);
  const [storyboard, setStoryboard] = useState<StoryboardScene[]>([]);
  const [generatedTopic, setGeneratedTopic] = useState("");

  // Input states: Viral Shorts Studio
  const [viralPrompt, setViralPrompt] = useState("The giant hidden ocean underneath Jupiter's moon Europa");
  const [viralOllamaModel, setViralOllamaModel] = useState("");
  const [viralVoice, setViralVoice] = useState("Sarah (Female - US - Soft)");
  const [viralVoiceSpeed, setViralVoiceSpeed] = useState(1.0);
  const [visualMode, setVisualMode] = useState("Cinematic Slideshow");
  const [viralLeonardoModel, setViralLeonardoModel] = useState("Lucid Realism (High Quality Face)");
  const [musicStyle, setMusicStyle] = useState("Cinematic");
  const [satisfyingBackground, setSatisfyingBackground] = useState("Slime ASMR");
  const [viralHookStyle, setViralHookStyle] = useState("Did You Know? (Fact Hook)");
  const [enableCaptions, setEnableCaptions] = useState(true);
  const [captionFont, setCaptionFont] = useState("Arial");
  const [captionSize, setCaptionSize] = useState(72);
  const [captionMarginV, setCaptionMarginV] = useState(150);
  const [captionColor, setCaptionColor] = useState("&H00FFFF&");

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

  const consoleEndRef = useRef<HTMLDivElement>(null);

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
      }
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

  const handleGenerateViralShort = async () => {
    setLoading(true);
    setLogs([]);
    setFinalVideoUrl(null);
    setStoryboard([]);
    
    addLog("🚀 Initializing Viral Short Generation Pipeline...");
    addLog(`Topic: "${viralPrompt}"`);
    addLog(`Hook Style: ${viralHookStyle}`);
    addLog(`Visual Mode: ${visualMode}`);
    addLog(`Satisfying BG: ${satisfyingBackground}`);
    addLog(`Voice: ${viralVoice} (Speed: ${viralVoiceSpeed}x)`);
    addLog(`Captions: ${enableCaptions ? `Enabled (${captionFont}, Size: ${captionSize}, Position: ${captionMarginV}px, Color: ${captionColor})` : "Disabled"}`);

    try {
      setStatusText("Generating script...");
      addLog("Step 1/5: Requesting Ollama multi-scene script...");
      
      const payload = {
        prompt: viralPrompt,
        model: viralOllamaModel || "deepseek-v4-pro:cloud",
        hook_style: viralHookStyle,
        visual_mode: visualMode,
        leonardo_model: viralLeonardoModel,
        voice: viralVoice,
        speed: viralVoiceSpeed,
        music_style: musicStyle,
        satisfying_background: satisfyingBackground,
        enable_captions: enableCaptions,
        caption_font: captionFont,
        caption_size: captionSize,
        caption_margin_v: captionMarginV,
        caption_color: captionColor
      };

      const response = await fetch("http://localhost:8000/api/generate-short", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Server error occurred");
      }

      const result = await response.json();
      
      addLog("Step 2/5: Speech voices synthesized successfully.");
      addLog("Step 3/5: Scene background visuals generated via Leonardo.ai.");
      addLog("Step 4/5: Video segments created, merged, and mixed with music.");
      if (satisfyingBackground !== "None") {
        addLog(`Step 5/5: Satisfying split-screen (${satisfyingBackground}) composited.`);
      }
      if (enableCaptions) {
        addLog("Step 5/5: Styled captions burned in using FFmpeg.");
      }
      
      addLog("🎉 Success! Short video generation complete.");
      
      setFinalVideoUrl(result.video_url);
      setStoryboard(result.storyboard);
      setGeneratedTopic(result.topic);
      setStatusText("Finished!");
    } catch (err: any) {
      addLog(`❌ ERROR: ${err.message || err}`);
      setStatusText("Failed");
    } finally {
      setLoading(false);
    }
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
      </div>

      {/* Dashboard Grid */}
      <div className="dashboard-grid">
        {/* Left Side: Forms */}
        <div className="form-panel">
          
          {/* TAB 1: VIRAL SHORTS STUDIO */}
          {activeTab === "viral" && (
            <div className="glass-card">
              <h2 className="card-title"><Sparkles /> Viral Shorts Configuration</h2>
              
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
                </div>
              </div>

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
                    onChange={(e) => setViralVoice(e.target.value)}
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

              <div className="form-group" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.05)", paddingTop: "15px" }}>
                <label className="form-label"><Subtitles size={16} style={{ display: "inline", marginRight: "6px" }} /> Auto-Caption & Visual Position Settings</label>
                
                <div style={{ display: "flex", flexWrap: "wrap", gap: "20px", marginTop: "12px" }}>
                  {/* Left: Controls */}
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

                  {/* Right: Mockup Canvas Preview */}
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
                      {/* Split Screen divider visual indicator */}
                      <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: "1px", borderTop: "1px dashed rgba(255,255,255,0.4)", pointerEvents: "none" }} />
                      
                      {/* Caption mockup element */}
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
                      
                      {/* Screen borders mockup overlay */}
                      <div style={{ position: "absolute", inset: 0, boxShadow: "inset 0 0 10px rgba(0,0,0,0.8)", pointerEvents: "none" }} />
                    </div>
                  </div>
                </div>
              </div>

              <button 
                onClick={handleGenerateViralShort}
                disabled={loading || !config} 
                className="btn btn-primary"
                style={{ marginTop: "10px" }}
              >
                <Play size={18} /> {loading ? "Generating Premium Short..." : "Generate Storytelling Short"}
              </button>
            </div>
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

      {/* Storyboard timeline preview (Only for Viral tab when storyboard exists) */}
      {activeTab === "viral" && storyboard.length > 0 && (
        <div className="glass-card" style={{ marginTop: "24px" }}>
          <h2 className="card-title" style={{ color: "#f43f5e" }}><Layers /> Scene Storyboard: {generatedTopic}</h2>
          <div className="timeline">
            {storyboard.map((scene) => (
              <div key={scene.scene} className="timeline-step">
                <div className="step-num">{scene.scene}</div>
                <div className="step-content">
                  <p className="step-text">"{scene.narration}"</p>
                  <div className="step-meta">
                    <img src={scene.image_url} className="step-image" alt={`Scene ${scene.scene}`} />
                    <div>
                      <span className="form-label-info" style={{ display: "block", marginBottom: "4px" }}>
                        🔊 Speech Voiceover ({scene.duration.toFixed(2)} seconds)
                      </span>
                      <audio controls className="step-audio" style={{ height: "24px" }}>
                        <source src={scene.audio_url} type="audio/wav" />
                      </audio>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
