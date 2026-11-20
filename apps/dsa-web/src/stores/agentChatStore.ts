import { create } from 'zustand';
import { agentApi, isAbortError } from '../api/agent';
import type { AgentBackendId, AgentBackendOption, ChatSessionItem, ChatStreamRequest } from '../api/agent';
import {
  createParsedApiError,
  getParsedApiError,
  isApiRequestError,
  isParsedApiError,
  type ParsedApiError,
} from '../api/error';
import { generateUUID } from '../utils/uuid';

const STORAGE_KEY_SESSION = 'dsa_chat_session_id';
const STORAGE_KEY_BACKEND = 'dsa_chat_backend';
const ACCEPTED_STREAM_BACKENDS = new Set<string>(['litellm', 'codex_app_server', 'claude_cli', 'gemini_cli']);
const SERVER_CANCELLABLE_BACKENDS = new Set<string>(['codex_app_server', 'claude_cli', 'gemini_cli']);

export interface ProgressStep {
  type: string;
  step?: number;
  stage?: string;
  tool?: string;
  display_name?: string;
  status?: string;
  success?: boolean;
  duration?: number;
  elapsed?: number;
  timeout?: number;
  remaining?: number;
  minimum?: number;
  reason?: string;
  message?: string;
  content?: string;
  meta?: Record<string, unknown>;
  backend?: string;
  error_code?: string;
  request_id?: string;
  session_id?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  skills?: string[];
  skill?: string;
  skillNames?: string[];
  skillName?: string;
  thinkingSteps?: ProgressStep[];
  backend?: string;
}

export interface StreamMeta {
  skillNames?: string[];
  skillName?: string;
  onAccepted?: (event: StreamAcceptedEvent) => void;
}

export interface StreamAcceptedEvent {
  type: 'accepted';
  backend: AgentBackendId;
  request_id: string;
  session_id: string;
}

type StreamTerminalStatus = 'cancelled' | 'timeout' | null;

type StreamFailureEvent = {
  type: string;
  success?: boolean;
  content?: string;
  error?: unknown;
  message?: unknown;
  backend?: string;
  error_code?: string;
};

function streamFailureFallback(event: StreamFailureEvent, defaultMessage: string): string {
  if (event.backend === 'codex_app_server') {
    return 'Codex Ajan şu anda bu soruyu yanıtlayamıyor; lütfen Ajan ayarlarındaki çalışma durumunu kontrol edin.';
  }
  if (event.backend === 'claude_cli') {
    return 'Claude CLI (MCP) yanıt üretemedi. Yerel `claude` oturumunuzu kontrol edip tekrar deneyin.';
  }
  if (event.backend === 'gemini_cli') {
    return 'Gemini CLI (MCP) yanıt üretemedi. Yerel `gemini` oturumunuzu kontrol edip tekrar deneyin.';
  }
  return defaultMessage;
}

function getFirstMeaningfulStreamError(...candidates: Array<unknown>): unknown {
  for (const candidate of candidates) {
    if (typeof candidate === 'string') {
      if (candidate.trim() !== '') {
        return candidate;
      }
      continue;
    }

    if (candidate != null) {
      return candidate;
    }
  }

  return undefined;
}

function getStreamFailureError(
  event: StreamFailureEvent,
  fallbackMessage: string,
): ParsedApiError {
  return getParsedApiError(
    getFirstMeaningfulStreamError(
      event.error,
      event.message,
      event.content,
      fallbackMessage,
    ),
  );
}

interface AgentChatState {
  messages: Message[];
  selectedSkillIds: string[] | null;
  selectedBackend: AgentBackendId | null;
  backends: AgentBackendOption[];
  recommendedBackend: AgentBackendId | null;
  backendsLoaded: boolean;
  copilotOpen: boolean;
  copilotPrefill: string | null;
  loading: boolean;
  progressSteps: ProgressStep[];
  sessionId: string;
  sessions: ChatSessionItem[];
  sessionsLoading: boolean;
  chatError: ParsedApiError | null;
  currentRoute: string;
  completionBadge: boolean;
  hasInitialLoad: boolean;
  abortController: AbortController | null;
  activeRequestId: string | null;
  serverCancellation: boolean;
  stopping: boolean;
  terminalStatus: StreamTerminalStatus;
  stopError: boolean;
}

interface AgentChatActions {
  setSelectedSkillIds: (skillIds: string[]) => void;
  setSelectedBackend: (backend: AgentBackendId | null) => void;
  loadBackends: (force?: boolean) => Promise<void>;
  openCopilot: (prefill?: string) => void;
  closeCopilot: () => void;
  toggleCopilot: () => void;
  consumeCopilotPrefill: () => string | null;
  setCurrentRoute: (path: string) => void;
  clearCompletionBadge: () => void;
  loadSessions: () => Promise<void>;
  loadInitialSession: () => Promise<void>;
  switchSession: (targetSessionId: string) => Promise<void>;
  startNewChat: () => void;
  stopStream: () => Promise<void>;
  startStream: (payload: ChatStreamRequest, meta?: StreamMeta) => Promise<void>;
}

const getInitialSessionId = (): string =>
  typeof localStorage !== 'undefined'
    ? localStorage.getItem(STORAGE_KEY_SESSION) || generateUUID()
    : generateUUID();

const getInitialBackend = (): AgentBackendId | null => {
  if (typeof localStorage === 'undefined') return null;
  const saved = localStorage.getItem(STORAGE_KEY_BACKEND);
  if (saved && ACCEPTED_STREAM_BACKENDS.has(saved)) {
    return saved as AgentBackendId;
  }
  return null;
};

export const useAgentChatStore = create<AgentChatState & AgentChatActions>((set, get) => {
  const deliverServerCancellation = async (requestId: string): Promise<void> => {
    try {
      await agentApi.cancelChatStream(requestId);
    } catch {
      const current = get();
      if (current.activeRequestId === requestId && current.loading) {
        set({ stopping: false, stopError: true });
      }
    }
  };

  return {
  messages: [],
  selectedSkillIds: null,
  selectedBackend: getInitialBackend(),
  backends: [],
  recommendedBackend: null,
  backendsLoaded: false,
  copilotOpen: false,
  copilotPrefill: null,
  loading: false,
  progressSteps: [],
  sessionId: getInitialSessionId(),
  sessions: [],
  sessionsLoading: false,
  chatError: null,
  currentRoute: '',
  completionBadge: false,
  hasInitialLoad: false,
  abortController: null,
  activeRequestId: null,
  serverCancellation: false,
  stopping: false,
  terminalStatus: null,
  stopError: false,

  setSelectedSkillIds: (skillIds) => set({ selectedSkillIds: skillIds }),

  setSelectedBackend: (backend) => {
    set({ selectedBackend: backend });
    if (typeof localStorage !== 'undefined') {
      if (backend) {
        localStorage.setItem(STORAGE_KEY_BACKEND, backend);
      } else {
        localStorage.removeItem(STORAGE_KEY_BACKEND);
      }
    }
  },

  loadBackends: async (force = false) => {
    if (!force && get().backendsLoaded) return;
    try {
      const data = await agentApi.getBackends();
      const recommended = ACCEPTED_STREAM_BACKENDS.has(data.recommendedBackend)
        ? (data.recommendedBackend as AgentBackendId)
        : null;
      const currentSelected = get().selectedBackend;
      const currentStillAvailable = currentSelected
        ? data.backends.some((b) => b.id === currentSelected && b.available)
        : false;
      const nextSelected = currentStillAvailable ? currentSelected : recommended;
      set({
        backends: data.backends,
        recommendedBackend: recommended,
        backendsLoaded: true,
        selectedBackend: nextSelected,
      });
      if (nextSelected && typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_KEY_BACKEND, nextSelected);
      }
    } catch {
      set({ backendsLoaded: true });
    }
  },

  openCopilot: (prefill) =>
    set((s) => ({
      copilotOpen: true,
      completionBadge: false,
      copilotPrefill: prefill !== undefined ? prefill : s.copilotPrefill,
    })),

  closeCopilot: () => set({ copilotOpen: false }),

  toggleCopilot: () =>
    set((s) => ({
      copilotOpen: !s.copilotOpen,
      completionBadge: !s.copilotOpen ? false : s.completionBadge,
    })),

  consumeCopilotPrefill: () => {
    const val = get().copilotPrefill;
    if (val !== null) {
      set({ copilotPrefill: null });
    }
    return val;
  },

  setCurrentRoute: (path) => set({ currentRoute: path }),

  clearCompletionBadge: () => set({ completionBadge: false }),

  loadSessions: async () => {
    set({ sessionsLoading: true });
    try {
      const sessions = await agentApi.getChatSessions();
      set({ sessions });
    } catch {
      // Ignore load errors
    } finally {
      set({ sessionsLoading: false });
    }
  },

  loadInitialSession: async () => {
    const { hasInitialLoad } = get();
    if (hasInitialLoad) return;
    set({ hasInitialLoad: true, sessionsLoading: true });

    try {
      const sessionList = await agentApi.getChatSessions();
      set({ sessions: sessionList });

      const savedId = localStorage.getItem(STORAGE_KEY_SESSION);
      if (savedId) {
        const sessionExists = sessionList.some((s) => s.session_id === savedId);
        if (sessionExists) {
          const detail = await agentApi.getChatSessionMessages(savedId);
          if (detail.messages.length > 0) {
            set({
              messages: detail.messages.map((m) => ({
                id: m.id,
                role: m.role,
                content: m.content,
              })),
              selectedSkillIds: detail.session_state.selected_skill_ids,
            });
          }
        } else {
          const newId = generateUUID();
          set({ sessionId: newId, selectedSkillIds: null });
          localStorage.setItem(STORAGE_KEY_SESSION, newId);
        }
      } else {
        localStorage.setItem(STORAGE_KEY_SESSION, get().sessionId);
      }
    } catch {
      // Ignore
    } finally {
      set({ sessionsLoading: false });
    }
  },

  switchSession: async (targetSessionId) => {
    const { sessionId, messages, abortController } = get();
    if (targetSessionId === sessionId && messages.length > 0) return;

    abortController?.abort();
    set({
      messages: [],
      selectedSkillIds: null,
      sessionId: targetSessionId,
      loading: false,
      progressSteps: [],
      chatError: null,
      abortController: null,
      activeRequestId: null,
      serverCancellation: false,
      stopping: false,
      terminalStatus: null,
      stopError: false,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, targetSessionId);

    try {
      const detail = await agentApi.getChatSessionMessages(targetSessionId);
      if (get().sessionId !== targetSessionId) {
        return;
      }
      set({
        messages: detail.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        })),
        selectedSkillIds: detail.session_state.selected_skill_ids,
      });
    } catch {
      // Ignore
    }
  },

  startNewChat: () => {
    // Abort any in-flight stream so the old request does not keep running
    get().abortController?.abort();
    const newId = generateUUID();
    set({
      sessionId: newId,
      messages: [],
      selectedSkillIds: null,
      loading: false,
      progressSteps: [],
      chatError: null,
      abortController: null,
      activeRequestId: null,
      serverCancellation: false,
      stopping: false,
      terminalStatus: null,
      stopError: false,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, newId);
  },

  stopStream: async () => {
    const state = get();
    if (!state.loading || state.stopping) return;
    if (!state.serverCancellation || !state.activeRequestId) {
      state.abortController?.abort();
      return;
    }

    set({ stopping: true, stopError: false });
    await deliverServerCancellation(state.activeRequestId);
  },

  startStream: async (payload, meta) => {
    if (get().loading) return;
    const { abortController: prevAc, sessionId: storeSessionId } = get();
    prevAc?.abort();

    const ac = new AbortController();
    const requestId = payload.request_id || generateUUID();
    set({
      abortController: ac,
      activeRequestId: requestId,
      serverCancellation: false,
      stopping: false,
      terminalStatus: null,
      stopError: false,
    });

    const streamSessionId = payload.session_id || storeSessionId;
    const ownsStream = () => {
      const state = get();
      return state.abortController === ac
        && state.activeRequestId === requestId
        && state.sessionId === streamSessionId;
    };
    const skillNames = meta?.skillNames?.length
      ? meta.skillNames
      : [meta?.skillName ?? 'Genel'];
    const skillName = skillNames.join(', ');

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: payload.message,
      skills: payload.skills,
      skill: payload.skills?.[0],
      skillNames,
      skillName,
    };

    set({
      loading: true,
      progressSteps: [],
      chatError: null,
    });

    try {
      const response = await agentApi.chatStream(
        {
          ...payload,
          ...(payload.backend ? {} : (get().selectedBackend ? { backend: get().selectedBackend ?? undefined } : {})),
          session_id: streamSessionId,
          request_id: requestId,
        },
        { signal: ac.signal },
      );
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let finalContent: string | null = null;
      let finalBackend: string | undefined;
      let receivedDoneEvent = false;
      let acceptedEvent: StreamAcceptedEvent | null = null;
      const currentProgressSteps: ProgressStep[] = [];
      const protocolError = (message: string) => createParsedApiError({
        title: 'İstek Kabul Edilmedi',
        message: 'Ajan bu soruyu onaylamadı; lütfen mesajınızı koruyup tekrar deneyin.',
        rawMessage: message,
        category: 'upstream_network',
      });
      const processLine = (line: string) => {
        if (!line.startsWith('data: ') || !ownsStream() || ac.signal.aborted) return;

        const event = JSON.parse(line.slice(6)) as ProgressStep;
        if (event.type === 'accepted') {
          if (acceptedEvent) {
            throw protocolError('Agent stream emitted accepted more than once.');
          }
          if (
            !event.backend
            || !ACCEPTED_STREAM_BACKENDS.has(event.backend)
            || event.request_id !== requestId
            || event.session_id !== streamSessionId
          ) {
            throw protocolError('Agent stream emitted an invalid accepted event.');
          }
          acceptedEvent = event as StreamAcceptedEvent;
          finalBackend = acceptedEvent.backend;
          set((s) => ({
            messages: [...s.messages, { ...userMessage, backend: acceptedEvent!.backend }],
            serverCancellation: SERVER_CANCELLABLE_BACKENDS.has(acceptedEvent!.backend),
            sessions: s.sessions.some((x) => x.session_id === streamSessionId)
              ? s.sessions
              : [
                  {
                    session_id: streamSessionId,
                    title: payload.message.slice(0, 60),
                    message_count: 1,
                    created_at: new Date().toISOString(),
                    last_active: new Date().toISOString(),
                  },
                  ...s.sessions,
                ],
          }));
          meta?.onAccepted?.(acceptedEvent);
          return;
        }
        if (!acceptedEvent) {
          throw protocolError(`Agent stream emitted ${event.type || 'an unknown event'} before accepted.`);
        }
        if (event.type === 'done') {
          set({ stopError: false });
          receivedDoneEvent = true;
          const doneEvent = event as unknown as StreamFailureEvent;
          if (doneEvent.error_code === 'cancelled') {
            set({ terminalStatus: 'cancelled' });
            return;
          }
          if (doneEvent.error_code === 'timeout') {
            set({ terminalStatus: 'timeout' });
            return;
          }
          if (doneEvent.success === false) {
            throw getStreamFailureError(
              doneEvent,
              streamFailureFallback(doneEvent, 'LLM çağrısı başarısız oldu, lütfen API anahtarı veya CLI yapılandırmasını kontrol edin'),
            );
          }
          finalContent = doneEvent.content ?? '';
          return;
        }

        if (event.type === 'error') {
          set({ stopError: false });
          const failureEvent = event as unknown as StreamFailureEvent;
          throw getStreamFailureError(
            failureEvent,
            streamFailureFallback(failureEvent, 'Analiz hatası'),
          );
        }

        currentProgressSteps.push(event);
        set((s) => ({ progressSteps: [...s.progressSteps, event] }));
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          try {
            processLine(line);
          } catch (parseErr: unknown) {
            if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
              throw parseErr;
            }
          }
        }
      }

      if (buf.trim().startsWith('data: ')) {
        try {
          processLine(buf.trim());
        } catch (parseErr: unknown) {
          if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
            throw parseErr;
          }
        }
      }

      if (!acceptedEvent && !ac.signal.aborted) {
        throw protocolError('Agent stream ended before accepted.');
      }

      if (!receivedDoneEvent && !ac.signal.aborted) {
        throw createParsedApiError({
          title: 'Yanıt Tamamlanamadı',
          message: 'Ajan akış yanıtı tamamlanmadan kesildi, lütfen tekrar deneyin.',
          rawMessage: 'Agent stream ended before a done event was received.',
          category: 'upstream_network',
        });
      }

      const { currentRoute } = get();
      const shouldAppend = ownsStream() && !ac.signal.aborted && finalContent !== null;

      if (shouldAppend) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: finalContent || '(İçerik yok)',
              skills: payload.skills,
              skill: payload.skills?.[0],
              skillNames,
              skillName,
              thinkingSteps: [...currentProgressSteps],
              backend: finalBackend,
            },
          ],
        }));
      }

      if (ownsStream() && !ac.signal.aborted && currentRoute !== '/chat') {
        set({ completionBadge: true });
      }
    } catch (error: unknown) {
      if (isAbortError(error) || !ownsStream() || ac.signal.aborted) {
        // Aborted or superseded requests must not affect the active chat.
      } else {
        set({ chatError: getParsedApiError(error) });
        const { currentRoute } = get();
        if (currentRoute !== '/chat') {
          set({ completionBadge: true });
        }
      }
    } finally {
      if (ownsStream()) {
        set({
          loading: false,
          progressSteps: [],
          abortController: null,
          activeRequestId: null,
          serverCancellation: false,
          stopping: false,
        });
        await get().loadSessions();
      }
    }
  },
  };
});
