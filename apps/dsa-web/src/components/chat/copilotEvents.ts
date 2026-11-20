import { useAgentChatStore } from '../../stores/agentChatStore';

export const OPEN_COPILOT_EVENT = 'dsa:open-copilot';

export function openCopilotDrawer(prefill?: string): void {
  useAgentChatStore.getState().openCopilot(prefill);
}
