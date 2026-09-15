export interface StoryboardScene {
  scene: number;
  narration: string;
  visual_prompt: string;
  speaker?: string;
  image_url?: string;
  audio_url?: string;
  clip_url?: string;
  duration?: number;
}
export interface YoutubeMetadata { title?: string; description?: string; tags?: string[] }
export interface Generation {
  id: string;
  topic?: string;
  prompt?: string;
  status: string;
  created_at: string;
  video_url: string;
  storyboard: StoryboardScene[];
  script_data?: { youtube_metadata?: YoutubeMetadata };
}
export interface UploadJob { id: string; topic?: string; status: string; created_at: string; logs?: string[] }
export interface ImageProviderStatus {
  provider: string; available: boolean; model?: string; device?: string;
  max_resolution?: string; delivery_resolution?: string; upscale_factor: number;
}
export interface LocalModel { id: string; name: string; note?: string; steps?: number; download_gb?: number }
export interface GenerationStatus {
  status: string; topic?: string; storyboard: StoryboardScene[];
  logs: string[]; error_message?: string; video_url: string; thumbnail_url?: string;
  youtube_metadata?: YoutubeMetadata; validation_warnings?: string[];
}
