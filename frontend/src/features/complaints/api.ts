/** The single axios instance and every HTTP call the app makes.
 *  Components never call axios directly — they dispatch thunks, which call this file. */

import axios, { AxiosError } from 'axios';
import type {
  Complaint,
  ComplaintAnalysisResponse,
  ComplaintFormData,
  IntakeDialogueState,
  IntakeChatResponse,
  ComplaintListResponse,
} from '../../types/complaint';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

export const http = axios.create({ baseURL, timeout: 120_000 });

/** The backend always answers with {"error": {code, message, details}}. */
interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: { field?: string; message?: string }[] };
}

/** Turn any axios failure into one readable sentence for the UI. */
export function toErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiErrorBody>;
  if (axiosError?.response) {
    const body = axiosError.response.data?.error;
    const details = body?.details?.length
      ? ` (${body.details.map((d) => `${d.field}: ${d.message}`).join('; ')})`
      : '';
    return `${body?.message ?? `Request failed with status ${axiosError.response.status}`}${details}`;
  }
  if (axiosError?.code === 'ECONNABORTED') {
    return 'The request timed out. The AI analysis can take a while — please try again.';
  }
  if (axiosError?.request) {
    return 'Could not reach the API. Is the backend running on http://localhost:8000 ?';
  }
  return 'Something went wrong. Please try again.';
}

export async function analyzeComplaintRequest(input: {
  text?: string;
  file?: File;
}): Promise<ComplaintAnalysisResponse> {
  const form = new FormData();
  if (input.file) form.append('file', input.file);
  if (input.text) form.append('complaint_text', input.text);
  const { data } = await http.post<ComplaintAnalysisResponse>('/complaints/analyze', form);
  return data;
}

export async function createComplaintRequest(payload: Record<string, unknown>): Promise<Complaint> {
  const { data } = await http.post<Complaint>('/complaints/finalize', payload);
  return data;
}

export async function continueIntakeChatRequest(input: {
  message: string;
  currentFields: ComplaintFormData;
  history: { role: 'user' | 'assistant'; text: string }[];
  dialogueState: IntakeDialogueState;
  file?: File;
}): Promise<IntakeChatResponse> {
  const current_fields = Object.fromEntries(
    Object.entries(input.currentFields).map(([key, value]) => [
      key,
      value === '' ? null : key === 'quantity_affected' ? Number(value) : value,
    ]),
  );
  if (input.file) {
    const form = new FormData();
    form.append('message', input.message);
    form.append('current_fields', JSON.stringify(current_fields));
    form.append('history', JSON.stringify(input.history.slice(-20)));
    form.append('dialogue_state', JSON.stringify(input.dialogueState));
    form.append('file', input.file);
    const { data } = await http.post<IntakeChatResponse>(
      '/complaints/intake/chat/attachment',
      form,
    );
    return data;
  }
  const { data } = await http.post<IntakeChatResponse>('/complaints/intake/chat', {
    message: input.message,
    current_fields,
    history: input.history.slice(-20),
    dialogue_state: input.dialogueState,
  });
  return data;
}

export async function fetchComplaintsRequest(params: {
  limit: number;
  offset: number;
  search?: string;
}): Promise<ComplaintListResponse> {
  const { data } = await http.get<ComplaintListResponse>('/complaints', { params });
  return data;
}

export async function fetchComplaintRequest(id: number): Promise<Complaint> {
  const { data } = await http.get<Complaint>(`/complaints/${id}`);
  return data;
}

export async function updateComplaintRequest(
  id: number,
  payload: Record<string, unknown>,
): Promise<Complaint> {
  const { data } = await http.put<Complaint>(`/complaints/${id}`, payload);
  return data;
}

export async function askComplaintRequest(id: number, question: string): Promise<string> {
  const { data } = await http.post<{ answer: string }>(`/complaints/${id}/chat`, { question });
  return data.answer;
}
