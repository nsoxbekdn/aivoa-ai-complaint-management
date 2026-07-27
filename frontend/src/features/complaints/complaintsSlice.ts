/** The one slice of application state.
 *
 *  Everything the intake screen needs lives here: the editable form, where each value came
 *  from, the AI analysis, and the loading/error flags for every request. Components read it
 *  with useAppSelector and change it by dispatching — none of them own server state.
 */

import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';

import {
  analyzeComplaintRequest,
  askComplaintRequest,
  continueIntakeChatRequest,
  createComplaintRequest,
  fetchComplaintRequest,
  fetchComplaintsRequest,
  toErrorMessage,
  updateComplaintRequest,
} from './api';
import { EMPTY_FORM, formFromAnalysis, validateForm } from './formUtils';
import type {
  Complaint,
  ComplaintAnalysisResponse,
  ComplaintFormData,
  ComplaintFormField,
  IntakeDialogueState,
  IntakeChatResponse,
  ComplaintListResponse,
  FieldSourceMap,
} from '../../types/complaint';

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  attachmentName?: string;
  ocrUsed?: boolean;
}

export interface ComplaintsState {
  formData: ComplaintFormData;
  /** Which fields the AI filled — used for the subtle highlight and the review reminder. */
  fieldSources: FieldSourceMap;
  validationErrors: Partial<Record<ComplaintFormField, string>>;

  pastedText: string;
  upload: { fileName: string | null; fileSize: number | null };

  analysis: ComplaintAnalysisResponse | null;
  analyzing: boolean;
  analysisStartedAt: number | null;
  analysisError: string | null;
  intakeChat: {
    messages: ChatMessage[];
    pending: boolean;
    error: string | null;
    readyToLodge: boolean;
    dialogueState: IntakeDialogueState;
  };

  saving: boolean;
  saveError: string | null;
  savedComplaint: Complaint | null;

  list: {
    items: Complaint[];
    total: number;
    limit: number;
    offset: number;
    search: string;
    loading: boolean;
    error: string | null;
  };

  current: {
    complaint: Complaint | null;
    loading: boolean;
    error: string | null;
    updating: boolean;
  };

  chat: { messages: ChatMessage[]; pending: boolean; error: string | null };
}

const INTAKE_WELCOME: ChatMessage = {
  role: 'assistant',
  text:
    'Hello! Tell me what happened, attach a complaint document, or fill in any facts you already know. I will continue from what is already in the form and ask only for what is still needed.',
};

const EMPTY_DIALOGUE_STATE: IntakeDialogueState = {
  pending_field: null,
  partial_fields: {},
  unavailable_fields: [],
  question_history: [],
  retry_counts: {},
  last_action: null,
};

const initialState: ComplaintsState = {
  formData: { ...EMPTY_FORM },
  fieldSources: {},
  validationErrors: {},
  pastedText: '',
  upload: { fileName: null, fileSize: null },
  analysis: null,
  analyzing: false,
  analysisStartedAt: null,
  analysisError: null,
  intakeChat: {
    messages: [{ ...INTAKE_WELCOME }],
    pending: false,
    error: null,
    readyToLodge: false,
    dialogueState: { ...EMPTY_DIALOGUE_STATE },
  },
  saving: false,
  saveError: null,
  savedComplaint: null,
  list: { items: [], total: 0, limit: 25, offset: 0, search: '', loading: false, error: null },
  current: { complaint: null, loading: false, error: null, updating: false },
  chat: { messages: [], pending: false, error: null },
};

// --- thunks ---------------------------------------------------------------------------

export const analyzeComplaint = createAsyncThunk<
  ComplaintAnalysisResponse,
  { text?: string; file?: File },
  { rejectValue: string }
>('complaints/analyze', async (input, { rejectWithValue }) => {
  try {
    return await analyzeComplaintRequest(input);
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

export const createComplaint = createAsyncThunk<
  Complaint,
  Record<string, unknown>,
  { rejectValue: string }
>('complaints/create', async (payload, { rejectWithValue }) => {
  try {
    return await createComplaintRequest(payload);
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

export const continueIntakeChat = createAsyncThunk<
  IntakeChatResponse,
  {
    message: string;
    currentFields: ComplaintFormData;
    history: ChatMessage[];
    dialogueState: IntakeDialogueState;
    file?: File;
  },
  { rejectValue: string }
>('complaints/continueIntakeChat', async (input, { rejectWithValue }) => {
  try {
    return await continueIntakeChatRequest(input);
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

export const fetchComplaints = createAsyncThunk<
  ComplaintListResponse,
  { limit?: number; offset?: number; search?: string } | undefined,
  { rejectValue: string }
>('complaints/fetchAll', async (params, { rejectWithValue }) => {
  try {
    return await fetchComplaintsRequest({
      limit: params?.limit ?? 25,
      offset: params?.offset ?? 0,
      search: params?.search || undefined,
    });
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

export const fetchComplaint = createAsyncThunk<Complaint, number, { rejectValue: string }>(
  'complaints/fetchOne',
  async (id, { rejectWithValue }) => {
    try {
      return await fetchComplaintRequest(id);
    } catch (error) {
      return rejectWithValue(toErrorMessage(error));
    }
  },
);

export const updateComplaint = createAsyncThunk<
  Complaint,
  { id: number; payload: Record<string, unknown> },
  { rejectValue: string }
>('complaints/update', async ({ id, payload }, { rejectWithValue }) => {
  try {
    return await updateComplaintRequest(id, payload);
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

export const askAboutComplaint = createAsyncThunk<
  string,
  { id: number; question: string },
  { rejectValue: string }
>('complaints/chat', async ({ id, question }, { rejectWithValue }) => {
  try {
    return await askComplaintRequest(id, question);
  } catch (error) {
    return rejectWithValue(toErrorMessage(error));
  }
});

// --- slice ----------------------------------------------------------------------------

const complaintsSlice = createSlice({
  name: 'complaints',
  initialState,
  reducers: {
    setFormField(
      state,
      action: PayloadAction<{ field: ComplaintFormField; value: string }>,
    ) {
      const { field, value } = action.payload;
      state.formData[field] = value;
      // A field the human typed into is no longer an unreviewed AI value.
      state.fieldSources[field] = 'user';
      delete state.validationErrors[field];
      state.saveError = null;
      state.savedComplaint = null;
    },
    setPastedText(state, action: PayloadAction<string>) {
      state.pastedText = action.payload;
      state.analysisError = null;
    },
    setUploadedFile(state, action: PayloadAction<{ name: string; size: number } | null>) {
      state.upload = action.payload
        ? { fileName: action.payload.name, fileSize: action.payload.size }
        : { fileName: null, fileSize: null };
      state.analysisError = null;
    },
    validateBeforeSave(state) {
      state.validationErrors = validateForm(state.formData);
    },
    resetForm(state) {
      state.formData = { ...EMPTY_FORM };
      state.fieldSources = {};
      state.validationErrors = {};
      state.saveError = null;
      state.savedComplaint = null;
    },
    clearIntake(state) {
      state.formData = { ...EMPTY_FORM };
      state.fieldSources = {};
      state.validationErrors = {};
      state.analysis = null;
      state.analysisError = null;
      state.pastedText = '';
      state.upload = { fileName: null, fileSize: null };
      state.saveError = null;
      state.savedComplaint = null;
      state.intakeChat = {
        messages: [{ ...INTAKE_WELCOME }],
        pending: false,
        error: null,
        readyToLodge: false,
        dialogueState: { ...EMPTY_DIALOGUE_STATE },
      };
    },
    dismissAnalysisError(state) {
      state.analysisError = null;
    },
    dismissSaveError(state) {
      state.saveError = null;
    },
    setListSearch(state, action: PayloadAction<string>) {
      state.list.search = action.payload;
      state.list.offset = 0; // a new search always starts on page one
    },
    setListOffset(state, action: PayloadAction<number>) {
      state.list.offset = Math.max(0, action.payload);
    },
    resetChat(state) {
      state.chat = { messages: [], pending: false, error: null };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(analyzeComplaint.pending, (state, action) => {
        state.analyzing = true;
        state.analysisError = null;
        state.analysisStartedAt = Date.now();
        state.savedComplaint = null;
        state.intakeChat.error = null;
        state.intakeChat.messages.push({
          role: 'user',
          text: action.meta.arg.text || (action.meta.arg.file ? 'Please read this attachment.' : ''),
          attachmentName: action.meta.arg.file?.name,
        });
      })
      .addCase(analyzeComplaint.fulfilled, (state, action) => {
        state.analyzing = false;
        state.analysis = action.payload;
        // This is the automatic form population the whole product is built around.
        const { form, sources } = formFromAnalysis(action.payload);
        // Never erase facts the reporter edited while analysis was running. AI values
        // populate untouched fields, while human-owned values remain authoritative.
        (Object.keys(form) as ComplaintFormField[]).forEach((field) => {
          if (state.fieldSources[field] === 'user') return;
          if (form[field].trim()) {
            state.formData[field] = form[field];
            state.fieldSources[field] = sources[field];
          }
        });
        state.validationErrors = {};
        const reporterMissing = [
          ...action.payload.completeness.missing_critical_fields,
          ...action.payload.completeness.missing_optional_fields.filter(
            (field) => field !== 'initial severity' && field !== 'priority',
          ),
        ];
        const question = reporterMissing.length
          ? action.payload.completeness.follow_up_questions.find(
              (item) => !/\bseverity\b|\bpriority\b/i.test(item),
            )
          : undefined;
        const understood = action.payload.summary || action.payload.extracted_fields.complaint_details;
        const lastUserMessage = [...state.intakeChat.messages]
          .reverse()
          .find((message) => message.role === 'user');
        if (lastUserMessage) {
          lastUserMessage.ocrUsed = action.payload.source_documents.some(
            (document) => document.ocr_used,
          );
        }
        state.intakeChat.messages.push({
          role: 'assistant',
          text: question
            ? `Thanks — this is what I understood: ${understood || 'I recorded the complaint details.'} I still need one detail: ${question}`
            : `Thanks — this is what I understood: ${understood || 'I recorded the complaint details.'} I have the important information needed to lodge this complaint. Please review the form and correct anything that does not look right.`,
        });
        state.intakeChat.readyToLodge = action.payload.completeness.is_complete;
      })
      .addCase(analyzeComplaint.rejected, (state, action) => {
        state.analyzing = false;
        state.analysisError = action.payload ?? 'Analysis failed.';
      })

      .addCase(continueIntakeChat.pending, (state, action) => {
        state.intakeChat.pending = true;
        state.intakeChat.error = null;
        state.intakeChat.messages.push({
          role: 'user',
          text: action.meta.arg.message || 'Please read this attachment.',
          attachmentName: action.meta.arg.file?.name,
        });
      })
      .addCase(continueIntakeChat.fulfilled, (state, action) => {
        state.intakeChat.pending = false;
        state.intakeChat.messages.push({
          role: 'assistant',
          text: action.payload.assistant_message,
        });
        state.intakeChat.readyToLodge = action.payload.ready_to_lodge;
        state.intakeChat.dialogueState = action.payload.dialogue_state;
        // Manual-first intake has no initial analysis response. Seed lightweight intake
        // state from this continuation so completeness and later chat turns work normally.
        if (!state.analysis) {
          state.analysis = {
            extracted_fields: action.payload.updated_fields,
            completeness: action.payload.completeness,
            risk_assessment: {
              risk_level: 'unknown',
              severity: 'unknown',
              priority: 'medium',
              patient_safety_concern: false,
              product_quality_concern: false,
              rationale: '',
              confidence: 0,
            },
            summary: action.payload.updated_fields.complaint_details ?? '',
            recommendations: {
              possible_root_causes: [],
              initial_investigation_steps: [],
              preliminary_capa_suggestions: [],
            },
            warnings: [],
            duplicate_candidates: [],
            original_text: '',
            input_filename: null,
            source_documents: [],
            disclaimer:
              'AI-generated analysis is preliminary and requires qualified review.',
          };
        }
        if (action.payload.source_document && state.analysis) {
          state.analysis.source_documents.push(action.payload.source_document);
          state.analysis.original_text = [
            state.analysis.original_text,
            `[Attachment: ${action.payload.source_document.filename}]\n${action.payload.source_document.text}`,
          ]
            .filter(Boolean)
            .join('\n\n');
          state.analysis.input_filename =
            state.analysis.input_filename ?? action.payload.source_document.filename;
          const lastUserMessage = [...state.intakeChat.messages]
            .reverse()
            .find((message) => message.role === 'user');
          if (lastUserMessage) lastUserMessage.ocrUsed = action.payload.source_document.ocr_used;
        }
        // Apply only facts actually learned or corrected in this turn. Re-copying the
        // whole request snapshot would overwrite any form edits made while chat was pending.
        action.payload.changed_fields.forEach((changedField) => {
          if (!(changedField in state.formData)) return;
          const field = changedField as ComplaintFormField;
          const value = action.payload.updated_fields[field];
          state.formData[field] = value === null || value === undefined ? '' : String(value);
          state.fieldSources[field] = 'ai';
        });
        if (state.analysis) {
          state.analysis.extracted_fields = action.payload.updated_fields;
          state.analysis.completeness = action.payload.completeness;
          state.analysis.warnings = [
            ...state.analysis.warnings,
            ...action.payload.warnings,
          ];
        }
        state.validationErrors = {};
      })
      .addCase(continueIntakeChat.rejected, (state, action) => {
        state.intakeChat.pending = false;
        state.intakeChat.error =
          action.payload ?? 'The intake assistant could not understand that response.';
      })

      .addCase(createComplaint.pending, (state) => {
        state.saving = true;
        state.saveError = null;
      })
      .addCase(createComplaint.fulfilled, (state, action) => {
        state.saving = false;
        state.savedComplaint = action.payload;
      })
      .addCase(createComplaint.rejected, (state, action) => {
        state.saving = false;
        state.saveError = action.payload ?? 'Could not save the complaint.';
      })

      .addCase(fetchComplaints.pending, (state) => {
        state.list.loading = true;
        state.list.error = null;
      })
      .addCase(fetchComplaints.fulfilled, (state, action) => {
        state.list.loading = false;
        state.list.items = action.payload.items;
        state.list.total = action.payload.total;
        state.list.limit = action.payload.limit;
        state.list.offset = action.payload.offset;
      })
      .addCase(fetchComplaints.rejected, (state, action) => {
        state.list.loading = false;
        state.list.error = action.payload ?? 'Could not load complaints.';
      })

      .addCase(fetchComplaint.pending, (state) => {
        state.current.loading = true;
        state.current.error = null;
        state.current.complaint = null;
      })
      .addCase(fetchComplaint.fulfilled, (state, action) => {
        state.current.loading = false;
        state.current.complaint = action.payload;
      })
      .addCase(fetchComplaint.rejected, (state, action) => {
        state.current.loading = false;
        state.current.error = action.payload ?? 'Could not load the complaint.';
      })

      .addCase(updateComplaint.pending, (state) => {
        state.current.updating = true;
        state.current.error = null;
      })
      .addCase(updateComplaint.fulfilled, (state, action) => {
        state.current.updating = false;
        state.current.complaint = action.payload;
      })
      .addCase(updateComplaint.rejected, (state, action) => {
        state.current.updating = false;
        state.current.error = action.payload ?? 'Could not update the complaint.';
      })

      .addCase(askAboutComplaint.pending, (state, action) => {
        state.chat.pending = true;
        state.chat.error = null;
        state.chat.messages.push({ role: 'user', text: action.meta.arg.question });
      })
      .addCase(askAboutComplaint.fulfilled, (state, action) => {
        state.chat.pending = false;
        state.chat.messages.push({ role: 'assistant', text: action.payload });
      })
      .addCase(askAboutComplaint.rejected, (state, action) => {
        state.chat.pending = false;
        state.chat.error = action.payload ?? 'The assistant could not answer.';
      });
  },
});

export const {
  setFormField,
  setPastedText,
  setUploadedFile,
  validateBeforeSave,
  resetForm,
  clearIntake,
  dismissAnalysisError,
  dismissSaveError,
  setListSearch,
  setListOffset,
  resetChat,
} = complaintsSlice.actions;

export default complaintsSlice.reducer;
