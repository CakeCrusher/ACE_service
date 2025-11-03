import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '/api' : 'http://localhost:8000')

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface Playbook {
  id: string
  created_at: string
  modified_at: string
  name: string | null
  description: string | null
}

export interface BulletMetadata {
  helpful_count: number
  harmful_count: number
  neutral_count: number
}

export interface Bullet {
  id: string
  playbook_id: string
  content: string
  metadata: BulletMetadata
  created_at: string
  modified_at: string
}

export interface LearnJob {
  id: string
  playbook_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  error: string | null
  reflection: any | null
  curation: any | null
}

export const api = {
  // Playbooks
  getPlaybooks: () => client.get<{ playbooks: Playbook[] }>('/playbooks'),
  getPlaybook: (id: string) => client.get<{ playbook: Playbook }>(`/playbooks/${id}`),
  createPlaybook: (data: { name: string; description?: string }) =>
    client.post<{ playbook: Playbook }>('/playbooks', data),

  // Bullets
  getBullets: (playbookId: string) =>
    client.get<{ bullets: Bullet[] }>(`/playbooks/${playbookId}/bullets`),
  createBullet: (playbookId: string, data: { content: string }) =>
    client.post<{ bullet: Bullet }>(`/playbooks/${playbookId}/bullets`, data),

  // Embed Prompt
  embedPrompt: (playbookId: string, data: { prompt: string; k?: number }) =>
    client.post<{ prompt: string }>(`/playbooks/${playbookId}/embed_prompt`, data),

  // Learn
  startLearn: (playbookId: string, data: {
    user_message: string
    trajectory: string
    ground_truth?: string | null
    evaluation?: string | null
    reflector_additional_instructions?: string | null
    curator_additional_instructions?: string | null
  }) =>
    client.post<{ learn_job_id: string }>(`/playbooks/${playbookId}/episodes/learn`, data),

  getLearnJob: (playbookId: string, jobId: string) =>
    client.get<{ learn_job: LearnJob }>(`/playbooks/${playbookId}/episodes/learn/${jobId}`),
}
