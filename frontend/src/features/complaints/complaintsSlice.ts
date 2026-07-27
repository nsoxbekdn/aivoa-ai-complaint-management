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
    'Hello! Tell me what went wrong with the product in your own words. You can paste an email or attach a complaint PDF, and I will help fill in the form.',
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
        state.formData = form;
        state.fieldSources = sources;
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
        const fields = action.payload.updated_fields;
        (Object.keys(fields) as ComplaintFormField[]).forEach((field) => {
          const value = fields[field as keyof typeof fields];
          state.formData[field] = value === null || value === undefined ? '' : String(value);
        });
        action.payload.changed_fields.forEach((field) => {
          if (field in state.formData) state.fieldSources[field as ComplaintFormField] = 'ai';
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
