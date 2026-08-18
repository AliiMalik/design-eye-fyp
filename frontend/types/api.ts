/** Types mirroring the FastAPI Pydantic schemas. No `any` anywhere. */

export interface User {
  user_id: string;
  email: string;
  display_name: string | null;
  role: string;
  bio: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface MessageResponse {
  message: string;
}

export interface FocusNode {
  x: number;
  y: number;
  rank: number;
  intensity: number;
}

export type RegionKey =
  | "top_left" | "top_center" | "top_right"
  | "mid_left" | "mid_center" | "mid_right"
  | "bot_left" | "bot_center" | "bot_right";

export interface Project {
  project_id: string;
  user_id: string;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  asset_count: number;
  avg_clarity_score: number | null;
}

export interface ProjectListResponse {
  projects: Project[];
  total_count: number;
  page: number;
  limit: number;
}

export interface Asset {
  asset_id: string;
  project_id: string;
  user_id: string;
  file_url: string;
  original_filename: string;
  format: string;
  file_size_kb: number;
  width: number;
  height: number;
  status: "pending" | "processing" | "complete" | "failed";
  uploaded_at: string;
}

export interface ProjectDetail {
  project: Project;
  assets: Asset[];
}

export interface UploadResponse {
  asset_id: string;
  task_id: string;
  status: string;
  /** A multi-page PDF analysed as one screen reports the real page count here. */
  pages_detected: number;
  pages_analysed: number;
}

export interface BatchScreen {
  asset_id: string;
  page_number: number;
  original_filename: string;
  status: string;
  mockup_url: string;
  heatmap_url: string | null;
  clarity_score: number | null;
  focus_index: number | null;
  clutter_index: number | null;
  width: number;
  height: number;
  suggestions: Suggestion[];
  headline: string;
}

export interface BatchUploadResponse {
  batch_id: string;
  project_id: string;
  page_count: number;
  pages_skipped: number;
  task_ids: string[];
  status: string;
}

export interface Batch {
  batch_id: string;
  project_id: string;
  source_filename: string;
  page_count: number;
  pages_skipped: number;
  status: "processing" | "complete" | "partial" | "failed";
  created_at: string;
  screens: BatchScreen[];
  screens_complete: number;
  screens_failed: number;
  avg_clarity_score: number | null;
  weakest_screen: number | null;
  strongest_screen: number | null;
  flow_summary: string;
  llm_status: string | null;
  llm_provider: string;
  llm_model: string;
}

export interface BatchListItem {
  batch_id: string;
  project_id: string;
  source_filename: string;
  page_count: number;
  status: string;
  created_at: string;
  avg_clarity_score: number | null;
}

export interface BatchListResponse {
  batches: BatchListItem[];
  total_count: number;
  page: number;
  limit: number;
}

/** One step of the predicted viewing order, with its timing on the playback. */
export interface ScanpathStep {
  rank: number;
  x: number;
  y: number;
  intensity: number;
  start_ms: number;
  dwell_ms: number;
  end_ms: number;
}

export interface AnalysisResult {
  result_id: string;
  asset_id: string;
  heatmap_url: string;
  saliency_array_url: string;
  mockup_url: string;
  clarity_score: number;
  focus_index: number;
  clutter_index: number;
  region_saliency: Record<string, number>;
  focus_nodes: FocusNode[];
  scanpath: ScanpathStep[];
  scanpath_total_ms: number;
  model_version: string;
  inference_time_ms: number;
  created_at: string;
  image_width: number;
  image_height: number;
  original_filename: string;
  project_id: string;
  /** 1 means the upload fitted one screen; above that, clarity_score is the
   *  mean of the per-viewport scores in `viewports`. */
  viewport_device: string;
  viewport_count: number;
  viewports: ViewportScore[];
  weakest_viewport: number | null;
  score_in_range: boolean;
}

export interface ViewportScore {
  index: number;
  top: number;
  bottom: number;
  clarity_score: number;
  focus_index: number;
  clutter_index: number;
}

export interface TaskStatus {
  task_id: string;
  asset_id: string;
  status: "pending" | "processing" | "complete" | "failed";
  stage: string;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  result_url: string | null;
  clarity_score: number | null;
  focus_nodes: FocusNode[] | null;
}

export interface ResultListItem {
  asset_id: string;
  project_id: string;
  original_filename: string;
  status: string;
  uploaded_at: string;
  clarity_score: number | null;
  heatmap_url: string | null;
  mockup_url: string | null;
  width: number;
  height: number;
}

export interface ResultListResponse {
  results: ResultListItem[];
  total_count: number;
  page: number;
  limit: number;
}

export interface ComparisonSide {
  asset_id: string;
  original_filename: string;
  mockup_url: string;
  heatmap_url: string;
  clarity_score: number;
  focus_index: number;
  clutter_index: number;
  focus_nodes: FocusNode[];
  region_saliency: Record<string, number>;
  width: number;
  height: number;
}

export interface Comparison {
  comparison_id: string;
  clarity_delta: number;
  winner: "A" | "B" | "tie";
  design_a: ComparisonSide;
  design_b: ComparisonSide;
  created_at: string;
}

export interface ComparisonListItem {
  comparison_id: string;
  asset_id_a: string;
  asset_id_b: string;
  clarity_delta: number;
  created_at: string;
}

export interface ComparisonListResponse {
  comparisons: ComparisonListItem[];
  total_count: number;
  page: number;
  limit: number;
}

export interface Suggestion {
  title: string;
  detail: string;
  severity: "high" | "medium" | "low";
  based_on: string;
}

export interface SuggestionsResponse {
  result_id: string | null;
  summary: string;
  suggestions: Suggestion[];
  llm_status: "ok" | "unavailable" | "error" | "rate_limited";
  provider: string;
  model_name: string;
  created_at: string | null;
}

export interface ClarityTrendPoint {
  date: string;
  clarity_score: number;
  asset_id: string;
  original_filename: string;
}

export interface DashboardStats {
  total_projects: number;
  total_analyses: number;
  avg_clarity_score: number;
  projects_this_month: number;
  clarity_trend: ClarityTrendPoint[];
  recent_assets: ResultListItem[];
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  db: boolean;
  redis: boolean;
  version: string;
  dev_mode: boolean;
  model_info: Record<string, unknown>;
}
